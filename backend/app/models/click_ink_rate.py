"""Click/Ink Rate model — spec-12/Phase 1B.

Click and ink rates for digital and other printing technologies.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from ..db import Base

def _utcnow() -> datetime:
    return datetime.now(timezone.utc)

class ClickInkRate(Base):
    __tablename__ = "click_ink_rates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # technology: offset, digital, large_format, flexo
    technology: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    # color_type: cmyk, grayscale, spot, white
    color_type: Mapped[str] = mapped_column(String(32), nullable=False)
    # machine_id: specific machine or NULL for default technology rate
    machine_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("machines.id", ondelete="CASCADE"), index=True, nullable=True
    )
    # unit: trang, m2, ml, click
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
    
    effective_from: Mapped[date] = mapped_column(Date, nullable=False)
    effective_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )
    
    machine = relationship("Machine")

    __table_args__ = (
        CheckConstraint(
            "effective_to IS NULL OR effective_to > effective_from",
            name="chk_click_ink_rates_effective_dates"
        ),
        Index(
            "uix_click_ink_rates_current",
            "technology",
            "color_type",
            text("coalesce(machine_id, 0)"),
            "unit",
            unique=True,
            sqlite_where=text("effective_to IS NULL"),
            postgresql_where=text("effective_to IS NULL")
        )
    )
