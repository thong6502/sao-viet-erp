"""Refresh-token business logic (spec-03).

Issues, rotates, and revokes refresh tokens against the store. Framework-agnostic — the
router owns the httpOnly cookie; this service only deals in raw token strings and users.

Rotation: each refresh revokes the presented token and mints a new one in the SAME family.
Reusing an already-revoked token is treated as theft and revokes the whole family.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

from ..config import settings
from ..models.refresh_token import RefreshToken
from ..models.user import User
from ..repositories.refresh_token_repo import RefreshTokenRepository
from ..repositories.user_repo import UserRepository
from ..security import generate_refresh_token, hash_refresh_token


class RefreshError(Exception):
    """Raised when a refresh token is missing, expired, revoked, or its user is gone/locked.
    The route maps this to 401."""


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(dt: datetime) -> datetime:
    # SQLite returns naive datetimes; treat stored values as UTC for comparison.
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)


class RefreshTokenService:
    def __init__(self, tokens: RefreshTokenRepository, users: UserRepository) -> None:
        self.tokens = tokens
        self.users = users

    def _expiry(self) -> datetime:
        return _utcnow() + timedelta(days=settings.refresh_token_expire_days)

    def _is_expired(self, row: RefreshToken) -> bool:
        return _as_utc(row.expires_at) <= _utcnow()

    def issue(self, user: User, *, family_id: str | None = None) -> str:
        """Mint a new refresh token for the user; return the raw (un-hashed) value."""
        raw = generate_refresh_token()
        self.tokens.create(
            user_id=user.id,
            token_hash=hash_refresh_token(raw),
            family_id=family_id or uuid4().hex,
            expires_at=self._expiry(),
        )
        return raw

    def rotate(self, raw: str) -> tuple[str, User]:
        """Validate + rotate a refresh token. Returns (new_raw_token, user) or raises.

        On reuse of an already-revoked token, revoke the whole family (theft signal).
        """
        row = self.tokens.get_by_hash(hash_refresh_token(raw))
        if row is None:
            raise RefreshError("Unknown refresh token")
        if row.revoked_at is not None:
            # Replay of a rotated/revoked token -> kill the family.
            self.tokens.revoke_family(row.family_id)
            raise RefreshError("Refresh token reuse detected")
        if self._is_expired(row):
            raise RefreshError("Refresh token expired")

        user = self.users.get_by_id(row.user_id)
        if user is None or not user.is_active:
            raise RefreshError("User missing or locked")

        # Rotate: revoke the presented token, issue a new one in the same family.
        self.tokens.revoke(row)
        new_raw = self.issue(user, family_id=row.family_id)
        return new_raw, user

    def revoke(self, raw: str) -> None:
        """Revoke a refresh token (logout). No-op if it is unknown/already revoked."""
        row = self.tokens.get_by_hash(hash_refresh_token(raw))
        if row is not None:
            self.tokens.revoke(row)
