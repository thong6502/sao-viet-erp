"""Department ORM model (phòng ban).

One row per organizational department (Kinh doanh, Hành chính nhân sự, …). A
department groups its own Roles; a user belongs to exactly one department.
Portable across SQLite and Postgres.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Department(Base):
    __tablename__ = "departments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    # Logical reference to users.id (the trưởng phòng). Kept as a plain column to avoid a
    # users<->departments FK cycle under create_all; the DB-level FK can land with Alembic.
    head_user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
