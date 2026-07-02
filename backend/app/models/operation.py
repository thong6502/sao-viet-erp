"""Operation models — spec-20/21 master data.

Catalog of post-press finishing steps and operations (folding, binding, packing, etc.)
and their associated processing cost rates.
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
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from ..db import Base

def _utcnow() -> datetime:
    return datetime.now(timezone.utc)

class Operation(Base):
    __tablename__ = "operations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(20), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    # in, can_mang, be, gap, dong_cuon, dong_goi...
    operation_type: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    unit: Mapped[str] = mapped_column(String(16), nullable=False) # m2, luot, to, cuon...
    allow_outsource: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )
    
    rates: Mapped[list[OperationRate]] = relationship(
        "OperationRate",
        back_populates="operation",
        cascade="all, delete-orphan",
        order_by="OperationRate.effective_from.desc()",
    )

class OperationRate(Base):
    __tablename__ = "operation_rates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    operation_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("operations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    setup_fee: Mapped[int] = mapped_column(
        BigInteger, CheckConstraint("setup_fee >= 0"), nullable=False, default=0
    )
    run_rate: Mapped[int] = mapped_column(
        BigInteger, CheckConstraint("run_rate >= 0"), nullable=False, default=0
    )
    labor_rate: Mapped[int] = mapped_column(
        BigInteger, CheckConstraint("labor_rate >= 0"), nullable=False, default=0
    )
    min_charge: Mapped[int] = mapped_column(
        BigInteger, CheckConstraint("min_charge >= 0"), nullable=False, default=0
    )
    speed: Mapped[float] = mapped_column(
        Numeric(10, 2), CheckConstraint("speed >= 0"), nullable=False, default=0.0
    )
    
    effective_from: Mapped[date] = mapped_column(Date, nullable=False)
    effective_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )
    
    operation: Mapped[Operation] = relationship("Operation", back_populates="rates")
    
    __table_args__ = (
        CheckConstraint(
            "effective_to IS NULL OR effective_to > effective_from",
            name="chk_operation_effective_dates"
        ),
        Index(
            "uix_operation_rates_current",
            "operation_id",
            unique=True,
            sqlite_where=text("effective_to IS NULL"),
            postgresql_where=text("effective_to IS NULL")
        )
    )
