"""Department ORM model (phòng ban).

One row per organizational department (Kinh doanh, Hành chính nhân sự, …). A
department groups its own Roles; a user belongs to exactly one department.
Portable across SQLite and Postgres.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Department(Base):
    __tablename__ = "departments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    # System-generated unique code (spec-05): "PB" + zero-padded sequence (PB001, PB002, …).
    # Read-only — users never type it; assigned by the repository on create.
    code: Mapped[str] = mapped_column(String(20), unique=True, index=True, nullable=False)
    # Optional free-text description (spec-05).
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # Parent department for the org tree (spec-05): self-FK, null = root unit. Children are
    # cascade-deleted with their parent's branch (handled in the service, not the DB).
    parent_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("departments.id"), index=True, nullable=True
    )
    # Logical reference to users.id (the trưởng phòng). Kept as a plain column to avoid a
    # users<->departments FK cycle under create_all; the DB-level FK can land with Alembic.
    head_user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
