"""Pydantic schemas for the Product Type Catalog API — spec-20/21 + spec page #1.
"""
from __future__ import annotations

from datetime import date, datetime
from pydantic import BaseModel, ConfigDict, Field


class _ProductTypeConfig(BaseModel):
    """Các field cấu hình chung của Create/Update (spec §A–§H)."""
    calculation_strategy: str = Field(min_length=1, max_length=32)
    # §A
    product_group: str = Field(default="an_pham", max_length=24)
    technology: str = Field(default="offset", max_length=20)
    description: str | None = Field(default=None, max_length=2000)
    display_order: int = Field(default=100, ge=0)
    # §B
    required_fields: list[str] | None = None
    shown_fields: list[str] | None = None
    # §C
    dimension_rule_type: str = Field(default="finished", max_length=16)
    default_bleed_mm: float = Field(default=0, ge=0)
    default_gutter_mm: float = Field(default=0, ge=0)
    default_trim_mm: float = Field(default=0, ge=0)
    allow_rotation: bool = True
    allow_custom_size: bool = True
    # §D
    has_page_count: bool = False
    page_multiple: int = Field(default=0, ge=0)
    pages_per_signature: int = Field(default=0, ge=0)
    has_cover_body_split: bool = False
    # §E
    allowed_materials: list[str] | None = None
    has_packaging: bool = False
    default_pack_qty: int = Field(default=0, ge=0)
    # §F
    default_operations: list[str] | None = None
    required_operations: list[str] | None = None
    allow_extra_operations: bool = True
    # §H
    compatible_technologies: list[str] | None = None
    sheet_count_mode: str = Field(default="by_pieces", max_length=16)
    ink_cost_mode: str = Field(default="per_1000", max_length=20)
    has_tooling: bool = False
    default_tooling_type: str | None = Field(default=None, max_length=20)
    allow_manual_override: bool = False
    # Bù hao: % áp thẳng vào số tờ sản xuất (đội giấy/mực/máy, không đội kẽm).
    waste_pct: float = Field(default=0, ge=0, le=100)
    is_active: bool = True


class ProductTypeCatalogCreate(_ProductTypeConfig):
    product_type: str = Field(min_length=1, max_length=32)
    name: str = Field(min_length=1, max_length=100)


class ProductTypeCatalogUpdate(_ProductTypeConfig):
    name: str = Field(min_length=1, max_length=100)
    is_active: bool | None = Field(default=None)


class ProductTypeCatalogRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    product_type: str
    name: str
    calculation_strategy: str
    product_group: str
    technology: str
    display_order: int
    version: int
    required_fields: list[str] | None = None
    shown_fields: list[str] | None = None
    default_operations: list[str] | None = None
    required_operations: list[str] | None = None
    allowed_materials: list[str] | None = None
    compatible_technologies: list[str] | None = None
    dimension_rule_type: str
    default_bleed_mm: float
    default_gutter_mm: float
    default_trim_mm: float
    has_page_count: bool
    has_cover_body_split: bool
    has_tooling: bool
    has_packaging: bool
    sheet_count_mode: str
    ink_cost_mode: str
    is_active: bool
    created_at: datetime


class ProductTypeCatalogListOut(BaseModel):
    items: list[ProductTypeCatalogRow]
    total: int
    page: int
    size: int


class ProductTypeCatalogDetailOut(ProductTypeCatalogRow):
    description: str | None = None
    effective_from: date | None = None
    effective_to: date | None = None
    used_count: int = 0
    allow_rotation: bool = True
    allow_custom_size: bool = True
    page_multiple: int = 0
    pages_per_signature: int = 0
    default_pack_qty: int = 0
    allow_extra_operations: bool = True
    default_tooling_type: str | None = None
    allow_manual_override: bool = False
    waste_pct: float = 0
    updated_at: datetime


# --- Test nhanh form tính giá (spec §5.7 / §9) ---------------------------
class ProductTypePreviewOut(BaseModel):
    """Mô phỏng: khi chọn loại SP này, màn Tính giá bật field nào, routing gì, quy tắc gì."""
    product_type: str
    name: str
    shown_fields: list[str]
    required_fields: list[str]
    routing: list[str]
    required_operations: list[str]
    dimension_rule_type: str
    default_bleed_mm: float
    default_gutter_mm: float
    default_trim_mm: float
    sheet_count_mode: str
    ink_cost_mode: str
    has_tooling: bool
    has_packaging: bool
    has_cover_body_split: bool
    rules: list[str]  # diễn giải dạng câu cho box "Quy tắc áp dụng"
    warnings: list[str] = Field(default_factory=list)
