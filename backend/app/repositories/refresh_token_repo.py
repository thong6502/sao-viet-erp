"""Refresh-token data access (spec-03). The only layer that touches the DB for refresh
tokens. Stores hashes only — callers pass an already-hashed token_hash."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from ..models.refresh_token import RefreshToken


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class RefreshTokenRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def create(
        self,
        *,
        user_id: int,
        token_hash: str,
        family_id: str,
        expires_at: datetime,
        user_agent: str | None = None,
    ) -> RefreshToken:
        row = RefreshToken(
            user_id=user_id,
            token_hash=token_hash,
            family_id=family_id,
            expires_at=expires_at,
            user_agent=user_agent,
        )
        self.db.add(row)
        self.db.commit()
        self.db.refresh(row)
        return row

    def list_active_for_user(self, user_id: int) -> list[RefreshToken]:
        """Non-revoked, non-expired refresh tokens for a user = its live sessions (spec-08),
        newest first."""
        stmt = (
            select(RefreshToken)
            .where(
                RefreshToken.user_id == user_id,
                RefreshToken.revoked_at.is_(None),
                RefreshToken.expires_at > _utcnow(),
            )
            .order_by(RefreshToken.created_at.desc())
        )
        return list(self.db.execute(stmt).scalars())

    def get_by_hash(self, token_hash: str) -> RefreshToken | None:
        stmt = select(RefreshToken).where(RefreshToken.token_hash == token_hash)
        return self.db.execute(stmt).scalar_one_or_none()

    def revoke(self, row: RefreshToken) -> RefreshToken:
        if row.revoked_at is None:
            row.revoked_at = _utcnow()
            self.db.commit()
            self.db.refresh(row)
        return row

    def revoke_family(self, family_id: str) -> int:
        """Revoke every still-active token in a rotation family (theft response)."""
        stmt = (
            update(RefreshToken)
            .where(RefreshToken.family_id == family_id, RefreshToken.revoked_at.is_(None))
            .values(revoked_at=_utcnow())
        )
        result = self.db.execute(stmt)
        self.db.commit()
        return result.rowcount or 0

    def revoke_all_for_user(self, user_id: int) -> int:
        """Revoke every active refresh token for a user (logout-all / lock)."""
        stmt = (
            update(RefreshToken)
            .where(RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None))
            .values(revoked_at=_utcnow())
        )
        result = self.db.execute(stmt)
        self.db.commit()
        return result.rowcount or 0

    def purge_expired(self) -> int:
        """Delete rows past their expiry (housekeeping)."""
        rows = list(
            self.db.execute(
                select(RefreshToken).where(RefreshToken.expires_at <= _utcnow())
            ).scalars()
        )
        for row in rows:
            self.db.delete(row)
        self.db.commit()
        return len(rows)
