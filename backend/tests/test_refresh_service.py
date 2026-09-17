"""Refresh-token store + rotation (feat-014, spec-03-auth-hardening).

Service + repository level (no HTTP). Proves issue/rotate/revoke, replay -> family revoke,
expiry rejection, and that tokens are stored hashed (plaintext never in the DB).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from tests.conftest import phien_da_seed

from app.models.refresh_token import RefreshToken
from app.repositories.refresh_token_repo import RefreshTokenRepository
from app.repositories.user_repo import UserRepository
from app.security import hash_refresh_token
from app.services.refresh_service import REUSE_GRACE, RefreshError, RefreshTokenService


@pytest.fixture
def db():
    yield from phien_da_seed()


def _service(session) -> RefreshTokenService:
    return RefreshTokenService(RefreshTokenRepository(session), UserRepository(session))


def _admin(session):
    return UserRepository(session).get_by_username("admin")


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


def _lui_luc_thu_hoi(db, raw, giay):
    """Đẩy mốc thu hồi của token về quá khứ — giả lập replay đến SAU `giay` giây."""
    row = RefreshTokenRepository(db).get_by_hash(hash_refresh_token(raw))
    row.revoked_at = datetime.now(timezone.utc) - timedelta(seconds=giay)
    db.commit()


def test_replay_of_revoked_token_revokes_family(db):
    svc = _service(db)
    raw = svc.issue(_admin(db))
    new_raw, _ = svc.rotate(raw)  # raw is now revoked; new_raw is active
    _lui_luc_thu_hoi(db, raw, REUSE_GRACE.total_seconds() + 1)

    # Reusing the old (revoked) token is a theft signal: raises AND kills the family.
    with pytest.raises(RefreshError):
        svc.rotate(raw)

    # The sibling minted by the first rotation is now revoked too.
    sibling = RefreshTokenRepository(db).get_by_hash(hash_refresh_token(new_raw))
    assert sibling is not None and sibling.revoked_at is not None
    with pytest.raises(RefreshError):
        svc.rotate(new_raw)


def test_replay_ngay_sau_khi_xoay_la_tai_lai_trang_khong_phai_trom(db):
    """Tải lại trang cắt ngang /refresh: máy chủ đã xoay raw→new_raw nhưng trình duyệt không kịp
    nhận cookie mới, trang mới gửi lại raw. Trong khoảng ân hạn ⇒ cấp token mới CÙNG họ và thu hồi
    new_raw bị bỏ rơi (mỗi họ chỉ một token sống), KHÔNG giết cả họ."""
    svc = _service(db)
    repo = RefreshTokenRepository(db)
    admin = _admin(db)
    raw = svc.issue(admin)
    fam = repo.get_by_hash(hash_refresh_token(raw)).family_id
    new_raw, _ = svc.rotate(raw)

    lai_raw, user = svc.rotate(raw)
    assert user.id == admin.id
    assert lai_raw not in (raw, new_raw)
    assert repo.get_by_hash(hash_refresh_token(lai_raw)).family_id == fam
    assert repo.get_by_hash(hash_refresh_token(new_raw)).revoked_at is not None
    assert [t.token_hash for t in repo.list_active_for_user(admin.id)] == [hash_refresh_token(lai_raw)]
    # Phiên tiếp tục xoay bình thường.
    svc.rotate(lai_raw)


def test_replay_trong_an_han_nhung_ho_da_dang_xuat_van_401(db):
    """Ân hạn chỉ cứu khi họ còn token sống. Đăng xuất (hoặc khoá) rồi gửi lại token cũ ⇒ 401."""
    svc = _service(db)
    raw = svc.issue(_admin(db))
    new_raw, _ = svc.rotate(raw)
    svc.revoke(new_raw)  # đăng xuất
    with pytest.raises(RefreshError):
        svc.rotate(raw)


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


def test_login_purges_expired_rows_but_rotation_does_not(db):
    """Mỗi lần xoay (access 15 phút) để lại một dòng đã thu hồi; không ai xoá thì bảng phình mãi.
    Đăng nhập mới dọn các dòng quá hạn; xoay thì không (quá dày để quét)."""
    repo = RefreshTokenRepository(db)
    svc = _service(db)
    admin = _admin(db)
    past = datetime.now(timezone.utc) - timedelta(seconds=1)
    repo.create(user_id=admin.id, token_hash=hash_refresh_token("old-1"), family_id="f1", expires_at=past)

    raw = svc.issue(admin)
    assert repo.get_by_hash(hash_refresh_token("old-1")) is None

    repo.create(user_id=admin.id, token_hash=hash_refresh_token("old-2"), family_id="f2", expires_at=past)
    svc.rotate(raw)
    assert repo.get_by_hash(hash_refresh_token("old-2")) is not None
    # Phiên vừa đăng nhập (đã xoay) vẫn là phiên sống duy nhất của nhánh này.
    assert len(repo.list_active_for_user(admin.id)) == 1


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
