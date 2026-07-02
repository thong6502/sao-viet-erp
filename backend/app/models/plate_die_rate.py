"""Plate/Die Rate model — spec-12/Phase 1B.

Rates for plate-making, dies, and embossing clichés over time.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Index,
    Integer,
    String,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column
from ..db import Base

def _utcnow() -> datetime:
    return datetime.now(timezone.utc)

class PlateDieRate(Base):
    __tablename__ = "plate_die_rates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # plate_type: ban_kem_offset, khuon_be, khuon_ep_kim
    plate_type: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    # technology: offset, flexo, be, ep_kim
    technology: Mapped[str] = mapped_column(String(32), nullable=False)
    # unit: ban, bo, cm2
    unit: Mapped[str] = mapped_column(String(16), nullable=False)
    
    unit_price: Mapped[int] = mapped_column(
        BigInteger, CheckConstraint("unit_price >= 0"), nullable=False
    )
    setup_fee: Mapped[int] = mapped_column(
        BigInteger, CheckConstraint("setup_fee >= 0"), nullable=False, default=0
    )
    min_charge: Mapped[int] = mapped_column(
        BigInteger, CheckConstraint("min_charge >= 0"), nullable=False, default=0
    )
    reusable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    
    effective_from: Mapped[date] = mapped_column(Date, nullable=False)
    effective_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )

    __table_args__ = (
        CheckConstraint(
            "effective_to IS NULL OR effective_to > effective_from",
            name="chk_plate_die_rates_effective_dates"
        ),
        Index(
            "uix_plate_die_rates_current",
            "plate_type",
            "technology",
            "unit",
            unique=True,
            sqlite_where=text("effective_to IS NULL"),
            postgresql_where=text("effective_to IS NULL")
        )
    )
