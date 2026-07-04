"""Norm/Loss/Waste model — spec-12/Phase 1B.

Configures loss and makeup norms, waste percentages, and setup wastes.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from sqlalchemy import (
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
    true as sa_true,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from ..db import Base

def _utcnow() -> datetime:
    return datetime.now(timezone.utc)

# 4 nhóm định mức (waste_group). Mực (ink_cost) KHÔNG thuộc nhóm nào → waste_group NULL.
WASTE_GROUPS = ("YIELD_RATE", "SETUP_WASTE", "RUNNING_WASTE", "PAPER_EXTRA_WASTE")

# waste_group → norm_key (khóa tra cứu nội bộ engine, giữ nguyên để không phá lookup/version cũ).
GROUP_TO_KEY = {
    "YIELD_RATE": "yield_rate",
    "SETUP_WASTE": "makeready_per_color_side",
    "RUNNING_WASTE": "running_waste_pct",
    "PAPER_EXTRA_WASTE": "paper_extra_waste",
}
KEY_TO_GROUP = {v: k for k, v in GROUP_TO_KEY.items()}

# Cách tính hợp lệ theo nhóm (UI đổi field theo đây).
METHODS_BY_GROUP = {
    "YIELD_RATE": ("PERCENT",),
    "SETUP_WASTE": ("FIXED", "PER_COLOR", "PER_SIDE", "COMBINED", "PER_COLOR_SIDE"),
    "RUNNING_WASTE": ("PERCENT",),
    "PAPER_EXTRA_WASTE": ("PERCENT", "FIXED", "PER_REAM"),
}

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

    # ---- Tái thiết kế danh mục #7: nhóm + cách tính + field theo nhóm ----
    code: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)
    name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    # 1 trong WASTE_GROUPS; NULL = rule đơn-giá cũ (mực). Suy được từ norm_key.
    waste_group: Mapped[str | None] = mapped_column(String(24), index=True, nullable=True)
    calculation_method: Mapped[str | None] = mapped_column(String(24), nullable=True)

    # Phạm vi áp dụng multi-select (mirror imposition_types). NULL/[] = tất cả.
    applicable_product_types: Mapped[list | None] = mapped_column(JSON, nullable=True)
    applicable_machine_ids: Mapped[list | None] = mapped_column(JSON, nullable=True)

    # SETUP_WASTE: makeready = clamp(qty + per_color×màu + per_side×mặt, min, max)
    setup_waste_qty: Mapped[float | None] = mapped_column(Numeric(12, 3), nullable=True)
    setup_waste_per_color: Mapped[float | None] = mapped_column(Numeric(12, 3), nullable=True)
    setup_waste_per_side: Mapped[float | None] = mapped_column(Numeric(12, 3), nullable=True)
    # Clamp chung cho SETUP / RUNNING / PAPER.
    min_waste_qty: Mapped[float | None] = mapped_column(Numeric(12, 3), nullable=True)
    max_waste_qty: Mapped[float | None] = mapped_column(Numeric(12, 3), nullable=True)
    # PAPER_EXTRA_WASTE: có cộng vào số tờ mua giấy không.
    paper_add_to_purchase: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=sa_true(), default=True
    )

    priority: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="100", default=100
    )
    version: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="1", default=1
    )
    used_count: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0", default=0
    )
    created_by: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    updated_by: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

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
