"""Product Type Catalog model — spec-20/21 master data.

Configures dynamic fields, operations, materials, and calculation strategies for product types.
"""
from __future__ import annotations

from datetime import datetime, timezone
from sqlalchemy import DateTime, Integer, String, Boolean, JSON
from sqlalchemy.orm import Mapped, mapped_column
from ..db import Base

# Strategies for calculating prices, validated in service
STRATEGY_SHEET = "sheet_based"
STRATEGY_PAGE = "page_based"
STRATEGY_AREA = "area_based"
STRATEGY_ROLL = "roll_based"
STRATEGY_BOX = "box_based"
STRATEGY_BOOK = "book_based"

CALCULATION_STRATEGIES = (
    STRATEGY_SHEET,
    STRATEGY_PAGE,
    STRATEGY_AREA,
    STRATEGY_ROLL,
    STRATEGY_BOX,
    STRATEGY_BOOK,
)

def _utcnow() -> datetime:
    return datetime.now(timezone.utc)

class ProductTypeCatalog(Base):
    __tablename__ = "product_types_catalog"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # E.g. business_card, brochure, catalogue, book, sticker, label, paper_box, paper_bag, banner, standee
    product_type: Mapped[str] = mapped_column(String(32), unique=True, index=True, nullable=False)
    # #25 — unique ở DB để chặn đua tạo/sửa trùng tên (find_by_name chỉ là kiểm tra đọc-trước-ghi).
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    calculation_strategy: Mapped[str] = mapped_column(String(32), nullable=False)
    
    # JSON arrays of configuration elements
    required_fields: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    default_operations: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    allowed_materials: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    compatible_technologies: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )
