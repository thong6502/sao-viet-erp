"""Refresh-token ORM model (spec-03).

One row per issued refresh token. Only a hash of the opaque token is stored — the
plaintext lives solely in the client's httpOnly cookie. Rotation revokes the old row and
issues a new one in the SAME `family_id`; reuse of a revoked token revokes the whole family
(theft signal). Portable across SQLite and Postgres.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id"), index=True, nullable=False
    )
    # SHA-256 hex digest (64 chars) of the opaque token. The plaintext is never stored.
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    # Groups a rotation chain so reuse of a revoked token can kill all siblings.
    family_id: Mapped[str] = mapped_column(String(36), index=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # Non-null once the token is rotated away or logged out.
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # User-Agent captured when the token was issued (spec-08) — shown as the "device" of a
    # session in the admin user-detail view. Nullable; never used for auth decisions.
    user_agent: Mapped[str | None] = mapped_column(String(400), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
