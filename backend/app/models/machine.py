"""Machine models — spec-20/21 master data.

Catalog of printing and processing machinery and their associated operating rates.
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
    Numeric,
    String,
    JSON,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from ..db import Base

def _utcnow() -> datetime:
    return datetime.now(timezone.utc)

class Machine(Base):
    __tablename__ = "machines"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(20), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    # offset, digital, large_format, flexo...
    machine_type: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    # in, can_mang, be, gap...
    process_type: Mapped[str] = mapped_column(String(32), nullable=False)
    
    max_width_cm: Mapped[float | None] = mapped_column(
        Numeric(10, 2), CheckConstraint("max_width_cm >= 0"), nullable=True
    )
    max_height_cm: Mapped[float | None] = mapped_column(
        Numeric(10, 2), CheckConstraint("max_height_cm >= 0"), nullable=True
    )
    min_width_cm: Mapped[float | None] = mapped_column(
        Numeric(10, 2), CheckConstraint("min_width_cm >= 0"), nullable=True
    )
    min_height_cm: Mapped[float | None] = mapped_column(
        Numeric(10, 2), CheckConstraint("min_height_cm >= 0"), nullable=True
    )
    
    speed: Mapped[float] = mapped_column(
        Numeric(10, 2), CheckConstraint("speed > 0"), nullable=False
    )
    speed_unit: Mapped[str] = mapped_column(String(32), nullable=False) # trang/phut, to/gio, m2/gio
    
    setup_time_mins: Mapped[int] = mapped_column(
        Integer, CheckConstraint("setup_time_mins >= 0"), nullable=False, default=0
    )
    changeover_time_mins: Mapped[int] = mapped_column(
        Integer, CheckConstraint("changeover_time_mins >= 0"), nullable=False, default=0
    )
    setup_waste_sheets: Mapped[float] = mapped_column(
        Numeric(10, 2), CheckConstraint("setup_waste_sheets >= 0"), nullable=False, default=0.0
    )
    
    supported_materials: Mapped[list[str] | None] = mapped_column(JSON, nullable=True) # list material_type
    
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )
    
    rates: Mapped[list[MachineRate]] = relationship(
        "MachineRate",
        back_populates="machine",
        cascade="all, delete-orphan",
        order_by="MachineRate.effective_from.desc()",
    )

class MachineRate(Base):
    __tablename__ = "machine_rates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    machine_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("machines.id", ondelete="CASCADE"), index=True, nullable=False
    )
    hourly_rate: Mapped[int] = mapped_column(
        BigInteger, CheckConstraint("hourly_rate >= 0"), nullable=False
    )
    min_charge: Mapped[int] = mapped_column(
        BigInteger, CheckConstraint("min_charge >= 0"), nullable=False, default=0
    )
    min_run_time_mins: Mapped[int] = mapped_column(
        Integer, CheckConstraint("min_run_time_mins >= 0"), nullable=False, default=0
    )
    
    effective_from: Mapped[date] = mapped_column(Date, nullable=False)
    effective_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )
    
    machine: Mapped[Machine] = relationship("Machine", back_populates="rates")
    
    __table_args__ = (
        CheckConstraint(
            "effective_to IS NULL OR effective_to > effective_from",
            name="chk_machine_effective_dates"
        ),
        Index(
            "uix_machine_rates_current",
            "machine_id",
            unique=True,
            sqlite_where=text("effective_to IS NULL"),
            postgresql_where=text("effective_to IS NULL")
        )
    )
