"""Estimate, EstimateOption, and EstimateCostLine ORM models — spec-08 / Phase 2A.
"""
from __future__ import annotations

from datetime import datetime, timezone
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    JSON,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from ..db import Base

def _utcnow() -> datetime:
    return datetime.now(timezone.utc)

class Estimate(Base):
    __tablename__ = "estimates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    estimate_number: Mapped[str] = mapped_column(String(20), unique=True, index=True, nullable=False)
    customer_id: Mapped[int | None] = mapped_column(Integer, index=True, nullable=True)
    product_type: Mapped[str] = mapped_column(String(50), ForeignKey("product_types_catalog.product_type"), nullable=False)
    product_name: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft")
    input_spec_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    quantity_list_json: Mapped[list] = mapped_column(JSON, nullable=False)
    created_by: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False)

    options = relationship("EstimateOption", back_populates="estimate", cascade="all, delete-orphan", order_by="EstimateOption.quantity")

    __table_args__ = (
        CheckConstraint(
            "status IN ('draft', 'calculated', 'cancelled')",
            name="chk_estimates_status"
        ),
    )


class EstimateOption(Base):
    __tablename__ = "estimate_options"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    estimate_id: Mapped[int] = mapped_column(Integer, ForeignKey("estimates.id", ondelete="CASCADE"), index=True, nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    total_cost: Mapped[float] = mapped_column(Numeric(15, 2), nullable=False, default=0)
    warnings_json: Mapped[list | None] = mapped_column(JSON, nullable=True)

    # Pricing columns (reserved for Phase 2B / 2C)
    margin_percent: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False, default=0)
    selling_price: Mapped[float] = mapped_column(Numeric(15, 2), nullable=False, default=0)
    discount_amount: Mapped[float] = mapped_column(Numeric(15, 2), nullable=False, default=0)
    vat_percent: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False, default=0)
    vat_amount: Mapped[float] = mapped_column(Numeric(15, 2), nullable=False, default=0)
    final_price: Mapped[float] = mapped_column(Numeric(15, 2), nullable=False, default=0)
    unit_price: Mapped[float] = mapped_column(Numeric(15, 2), nullable=False, default=0)
    actual_margin: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False, default=0)
    included_in_quote: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    estimate = relationship("Estimate", back_populates="options")
    cost_lines = relationship("EstimateCostLine", back_populates="option", cascade="all, delete-orphan", order_by="EstimateCostLine.id")

    @property
    def blocking_error_count(self) -> int:
        if not self.warnings_json:
            return 0
        return sum(1 for w in self.warnings_json if w.get("severity") == "blocking_error")

    @property
    def warning_count(self) -> int:
        if not self.warnings_json:
            return 0
        return sum(1 for w in self.warnings_json if w.get("severity") == "warning")

    @property
    def can_create_quote(self) -> bool:
        return self.blocking_error_count == 0

    __table_args__ = (
        CheckConstraint("quantity > 0", name="chk_estimate_options_quantity"),
        CheckConstraint("total_cost >= 0", name="chk_estimate_options_total_cost"),
        CheckConstraint("margin_percent >= 0 AND margin_percent < 100", name="chk_estimate_options_margin_percent"),
        CheckConstraint("final_price >= 0", name="chk_estimate_options_final_price"),
        UniqueConstraint("estimate_id", "quantity", name="uix_estimate_options_estimate_qty")
    )


class EstimateCostLine(Base):
    __tablename__ = "estimate_cost_lines"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    estimate_option_id: Mapped[int] = mapped_column(Integer, ForeignKey("estimate_options.id", ondelete="CASCADE"), index=True, nullable=False)
    category: Mapped[str] = mapped_column(String(32), nullable=False)
    description: Mapped[str] = mapped_column(String(255), nullable=False)
    source_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    source_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_snapshot_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    calculation_snapshot_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    quantity: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    unit: Mapped[str] = mapped_column(String(16), nullable=False)
    unit_cost: Mapped[float] = mapped_column(Numeric(15, 2), nullable=False)
    setup_cost: Mapped[float] = mapped_column(Numeric(15, 2), nullable=False, default=0)
    min_charge_applied: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    total_cost: Mapped[float] = mapped_column(Numeric(15, 2), nullable=False)
    note: Mapped[str | None] = mapped_column(String(500), nullable=True)

    option = relationship("EstimateOption", back_populates="cost_lines")

    __table_args__ = (
        CheckConstraint("quantity >= 0", name="chk_estimate_cost_lines_quantity"),
        CheckConstraint("unit_cost >= 0", name="chk_estimate_cost_lines_unit_cost"),
        CheckConstraint("setup_cost >= 0", name="chk_estimate_cost_lines_setup_cost"),
        CheckConstraint("total_cost >= 0", name="chk_estimate_cost_lines_total_cost"),
        CheckConstraint(
            "category IN ('material', 'ink', 'click_ink', 'plate_die', 'machine', 'operation', 'outsource', 'delivery', 'packing', 'other')",
            name="chk_estimate_cost_lines_category"
        ),
    )
