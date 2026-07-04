"""Pydantic schemas for the Materials API — tái thiết kế danh mục #2."""
from __future__ import annotations

from datetime import date, datetime
from pydantic import BaseModel, ConfigDict, Field


class MaterialCostCreate(BaseModel):
    price_unit: str = Field(min_length=1, max_length=16)
    unit_price: int = Field(ge=0)
    effective_from: date
    # Tái thiết kế #2 — NCC + khổ + loại giá + bậc SL + phí.
    supplier: str | None = Field(default=None, max_length=150)
    paper_size_id: int | None = None
    price_type: str = Field(default="standard", max_length=20)
    vat_included: bool = False
    transport_fee: int = Field(default=0, ge=0)
    moq: float = Field(default=0.0, ge=0)
    lead_time_days: int = Field(default=0, ge=0)
    quantity_from: float | None = Field(default=None, ge=0)
    quantity_to: float | None = Field(default=None, ge=0)


class MaterialCostOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    price_unit: str
    unit_price: int
    supplier: str | None = None
    paper_size_id: int | None = None
    price_type: str = "standard"
    vat_included: bool = False
    transport_fee: int = 0
    moq: float = 0.0
    lead_time_days: int = 0
    quantity_from: float | None = None
    quantity_to: float | None = None
    version: int = 1
    effective_from: date
    effective_to: date | None
    created_at: datetime


# Field vật tư dùng chung cho create/row/detail.
class _MaterialFields(BaseModel):
    material_group: str | None = Field(default=None, max_length=20)
    default_supplier: str | None = Field(default=None, max_length=150)
    base_uom: str | None = Field(default=None, max_length=16)
    purchase_uom: str | None = Field(default=None, max_length=16)
    consumption_uom: str | None = Field(default=None, max_length=16)
    conversion_method: str | None = Field(default=None, max_length=24)
    conversion_factor: float | None = Field(default=None, ge=0)
    ink_type: str | None = Field(default=None, max_length=32)
    ink_color_system: str | None = Field(default=None, max_length=32)
    ink_color_code: str | None = Field(default=None, max_length=32)
    film_type: str | None = Field(default=None, max_length=32)


class MaterialCreate(_MaterialFields):
    name: str = Field(min_length=1, max_length=255)
    material_type: str = Field(min_length=1, max_length=32)
    unit: str = Field(min_length=1, max_length=16)
    min_fee: int = Field(default=0, ge=0)

    width_cm: float | None = Field(default=None, ge=0)
    height_cm: float | None = Field(default=None, ge=0)
    gsm: int | None = Field(default=None, ge=0)
    thickness_mm: float | None = Field(default=None, ge=0)
    default_waste_pct: float = Field(default=0.0, ge=0)
    min_purchase_qty: float = Field(default=0.0, ge=0)

    paper_family: str | None = Field(default=None, max_length=32)
    surface: str | None = Field(default=None, max_length=32)
    is_active: bool = True


class MaterialUpdate(MaterialCreate):
    """Same as create; code is read-only and is not sent."""


class MaterialRow(_MaterialFields):
    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    name: str
    material_type: str
    unit: str
    # List phải trả đủ field mà form Sửa dùng để prefill.
    min_fee: int = 0
    thickness_mm: float | None = None
    default_waste_pct: float = 0.0
    min_purchase_qty: float = 0.0
    version: int = 1
    is_active: bool
    width_cm: float | None
    height_cm: float | None
    gsm: int | None
    paper_family: str | None
    surface: str | None
    costs: list[MaterialCostOut] = Field(default_factory=list)


class MaterialListStats(BaseModel):
    total_materials: int
    total_papers: int
    total_consumables: int
    no_price_count: int
    price_updates_this_month: int


class MaterialListOut(BaseModel):
    items: list[MaterialRow]
    total: int
    page: int
    size: int
    stats: MaterialListStats


class MaterialDetailOut(_MaterialFields):
    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    name: str
    material_type: str
    unit: str
    min_fee: int
    width_cm: float | None
    height_cm: float | None
    gsm: int | None
    thickness_mm: float | None
    default_waste_pct: float
    min_purchase_qty: float
    paper_family: str | None
    surface: str | None
    version: int = 1
    is_active: bool
    created_at: datetime
    updated_at: datetime
    costs: list[MaterialCostOut] = Field(default_factory=list)


# --- Test quy đổi / tính tiền (§9) — không cần material trong DB ------------

class MaterialConvertInput(BaseModel):
    gsm: int = Field(ge=0)
    width_cm: float = Field(gt=0)
    height_cm: float = Field(gt=0)


class MaterialConvertOut(BaseModel):
    area_m2: float
    kg_per_sheet: float
    detail: str


class MaterialPriceTestInput(BaseModel):
    price_unit: str = Field(min_length=1, max_length=16)
    unit_price: float = Field(ge=0)
    # Cho giấy (to/ram/kg) & m²:
    sheets: float = Field(default=0, ge=0)
    gsm: int | None = Field(default=None, ge=0)
    width_cm: float | None = Field(default=None, ge=0)
    height_cm: float | None = Field(default=None, ge=0)
    # Cho mực:
    impressions: float = Field(default=0, ge=0)
    # Cho bao bì/phụ liệu đếm cái:
    quantity: float = Field(default=0, ge=0)
    transport_fee: float = Field(default=0, ge=0)


class MaterialPriceTestOut(BaseModel):
    total: float
    steps: list[str]
