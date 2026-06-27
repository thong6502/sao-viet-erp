"""Refresh-token store + rotation (feat-014, spec-03-auth-hardening).

Service + repository level (no HTTP). Proves issue/rotate/revoke, replay -> family revoke,
expiry rejection, and that tokens are stored hashed (plaintext never in the DB).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.db import SessionLocal, init_db
from app.models.refresh_token import RefreshToken
from app.repositories.refresh_token_repo import RefreshTokenRepository
from app.repositories.user_repo import UserRepository
from app.security import hash_refresh_token
from app.seed import seed_all
from app.services.refresh_service import RefreshError, RefreshTokenService


@pytest.fixture
def db():
    init_db()
    session = SessionLocal()
    try:
        seed_all(session)
        yield session
    finally:
        session.close()


def _service(session) -> RefreshTokenService:
    return RefreshTokenService(RefreshTokenRepository(session), UserRepository(session))


def _admin(session):
    return UserRepository(session).get_by_email("admin@example.com")


def test_issue_then_rotate_returns_new_token_and_revokes_old(db):
    svc = _service(db)
    admin = _admin(db)
    raw = svc.issue(admin)

    new_raw, user = svc.rotate(raw)
    assert new_raw != raw
    assert user.id == admin.id

    # Old token row is now revoked.
    old = RefreshTokenRepository(db).get_by_hash(hash_refresh_token(raw))
    assert old is not None and old.revoked_at is not None


def test_rotate_keeps_same_family(db):
    svc = _service(db)
    raw = svc.issue(_admin(db))
    repo = RefreshTokenRepository(db)
    fam = repo.get_by_hash(hash_refresh_token(raw)).family_id
    new_raw, _ = svc.rotate(raw)
    assert repo.get_by_hash(hash_refresh_token(new_raw)).family_id == fam


def test_replay_of_revoked_token_revokes_family(db):
    svc = _service(db)
    raw = svc.issue(_admin(db))
    new_raw, _ = svc.rotate(raw)  # raw is now revoked; new_raw is active

    # Reusing the old (revoked) token is a theft signal: raises AND kills the family.
    with pytest.raises(RefreshError):
        svc.rotate(raw)

    # The sibling minted by the first rotation is now revoked too.
    sibling = RefreshTokenRepository(db).get_by_hash(hash_refresh_token(new_raw))
    assert sibling is not None and sibling.revoked_at is not None
    with pytest.raises(RefreshError):
        svc.rotate(new_raw)


def test_unknown_token_raises(db):
    with pytest.raises(RefreshError):
        _service(db).rotate("not-a-real-token")


def test_expired_token_raises(db):
    repo = RefreshTokenRepository(db)
    admin = _admin(db)
    raw = "expired-raw-token"
    repo.create(
        user_id=admin.id,
        token_hash=hash_refresh_token(raw),
        family_id="fam-expired",
        expires_at=datetime.now(timezone.utc) - timedelta(seconds=1),
    )
    with pytest.raises(RefreshError):
        _service(db).rotate(raw)


def test_revoke_then_rotate_fails(db):
    svc = _service(db)
    raw = svc.issue(_admin(db))
    svc.revoke(raw)
    with pytest.raises(RefreshError):
        svc.rotate(raw)


def test_token_is_stored_hashed_not_plaintext(db):
    svc = _service(db)
    raw = svc.issue(_admin(db))
    rows = list(db.execute(select(RefreshToken)).scalars())
    assert rows, "expected a refresh-token row"
    for row in rows:
        assert row.token_hash != raw  # never the plaintext
        assert len(row.token_hash) == 64  # sha256 hex
    # The plaintext only matches via its hash.
    assert RefreshTokenRepository(db).get_by_hash(hash_refresh_token(raw)) is not None


def test_rotate_for_locked_user_raises(db):
    svc = _service(db)
    admin = _admin(db)
    raw = svc.issue(admin)
    UserRepository(db).set_active(admin, False)
    with pytest.raises(RefreshError):
        svc.rotate(raw)
