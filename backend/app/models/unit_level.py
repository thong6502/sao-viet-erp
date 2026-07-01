"""UnitLevel ORM model (cấp đơn vị / tier of the org tree).

One row per organizational tier (Khối, Phòng, Tổ, …). Each level carries a display
`rank` (cao→thấp, 1 = highest) and the title of whoever heads a unit at that level
(Trưởng khối, Trưởng phòng, Tổ trưởng). A department may be tagged with a level via
`departments.level_id` (spec-06 / PBI-4009). Portable across SQLite and Postgres.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class UnitLevel(Base):
    __tablename__ = "unit_levels"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # Tier name (e.g. "Khối", "Phòng", "Tổ"); unique so the catalog has no duplicates.
    name: Mapped[str] = mapped_column(String(100), unique=True, index=True, nullable=False)
    # Display order, high→low (1 = highest tier); unique so two tiers never share a rank.
    rank: Mapped[int] = mapped_column(Integer, unique=True, index=True, nullable=False)
    # Title of the person heading a unit at this level (e.g. "Trưởng khối", "Tổ trưởng").
    head_title: Mapped[str] = mapped_column(String(100), nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
