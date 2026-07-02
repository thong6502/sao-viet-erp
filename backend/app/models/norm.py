"""Norm/Loss/Waste model — spec-12/Phase 1B.

Configures loss and makeup norms, waste percentages, and setup wastes.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from sqlalchemy import (
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

class Norm(Base):
    __tablename__ = "norms"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # yield_rate, running_waste_pct, makeready_per_color_side
    norm_key: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    # value is Numeric(10, 4) since yields can be e.g. 0.9950 or waste can be e.g. 0.0500
    value: Mapped[float] = mapped_column(
        Numeric(10, 4), CheckConstraint("value >= 0"), nullable=False
    )
    
    # Specificity dimensions
    product_type: Mapped[str | None] = mapped_column(
        String(32),
        ForeignKey("product_types_catalog.product_type", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )
    machine_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("machines.id", ondelete="SET NULL"), index=True, nullable=True
    )
    operation_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("operations.id", ondelete="SET NULL"), index=True, nullable=True
    )
    operation_key: Mapped[str | None] = mapped_column(String(32), index=True, nullable=True)
    
    qty_min: Mapped[int | None] = mapped_column(
        Integer, CheckConstraint("qty_min IS NULL OR qty_min >= 0"), nullable=True
    )
    qty_max: Mapped[int | None] = mapped_column(
        Integer, CheckConstraint("qty_max IS NULL OR qty_max >= 0"), nullable=True
    )
    
    # context is a JSON object storing attributes like colors, sides, etc.
    context: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # context_key is generated canonical representation of context
    context_key: Mapped[str] = mapped_column(String(160), nullable=False, default="{}")
    
    effective_from: Mapped[date] = mapped_column(Date, nullable=False)
    effective_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    note: Mapped[str | None] = mapped_column(String(500), nullable=True)
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )
    
    product_type_rel = relationship("ProductTypeCatalog")
    machine = relationship("Machine")
    operation = relationship("Operation")

    __table_args__ = (
        CheckConstraint(
            "effective_to IS NULL OR effective_to > effective_from",
            name="chk_norms_effective_dates"
        ),
        CheckConstraint(
            "qty_max IS NULL OR qty_min IS NULL OR qty_max >= qty_min",
            name="chk_norms_qty_range"
        ),
        CheckConstraint(
            "operation_id IS NULL OR operation_key IS NULL",
            name="chk_norms_operation_exclusivity"
        ),
        Index(
            "uix_norms_current",
            "norm_key",
            text("coalesce(product_type, '')"),
            text("coalesce(machine_id, 0)"),
            text("coalesce(operation_id, 0)"),
            text("coalesce(operation_key, '')"),
            text("coalesce(qty_min, -1)"),
            text("coalesce(qty_max, -1)"),
            "context_key",
            unique=True,
            sqlite_where=text("effective_to IS NULL"),
            postgresql_where=text("effective_to IS NULL")
        )
    )
