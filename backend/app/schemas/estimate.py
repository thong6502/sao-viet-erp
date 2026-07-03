"""Pydantic schemas for the Estimate API — spec-08 / Phase 2A.
"""
from __future__ import annotations

from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field

class EstimateCostLineOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    category: str
    description: str
    source_type: str | None = None
    source_id: int | None = None
    source_snapshot_json: dict | None = None
    calculation_snapshot_json: dict | None = None
    quantity: float
    unit: str
    unit_cost: float
    setup_cost: float
    min_charge_applied: bool
    total_cost: float
    note: str | None = None

class EstimateOptionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    quantity: int
    total_cost: float
    warnings_json: list[dict] | None = None
    margin_percent: float
    selling_price: float
    discount_amount: float
    vat_percent: float
    vat_amount: float
    final_price: float
    unit_price: float
    actual_margin: float
    included_in_quote: bool
    can_create_quote: bool = True
    blocking_error_count: int = 0
    warning_count: int = 0
    cost_lines: list[EstimateCostLineOut]

class EstimateCreate(BaseModel):
    product_type: str = Field(..., min_length=1, max_length=50)
    product_name: str = Field(..., min_length=1, max_length=255)
    quantity_list: list[int] = Field(..., min_length=1)
    input_spec: dict
    customer_id: int | None = None
    status: str = "draft"


class EstimatePreviewIn(BaseModel):
    """Live preview (KHÔNG lưu): chạy engine với spec đang gõ trên form để sidebar hiện
    giá vốn tức thời. Cùng shape input_spec như EstimateCreate."""

    input_spec: dict
    quantity: int = Field(..., gt=0)


class EstimatePreviewLineOut(BaseModel):
    category: str
    description: str
    total_cost: float


class EstimatePreviewOut(BaseModel):
    total_cost: float
    cost_lines: list[EstimatePreviewLineOut]
    warnings: list[dict]

class EstimateUpdate(EstimateCreate):
    pass

class EstimateOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    estimate_number: str
    customer_id: int | None
    product_type: str
    product_name: str
    status: str
    input_spec_json: dict
    quantity_list_json: list[int]
    created_by: int | None
    created_at: datetime
    updated_at: datetime
    options: list[EstimateOptionOut]

class EstimateRow(BaseModel):
    id: int
    estimate_number: str
    product_type: str
    product_name: str
    status: str
    quantity_list_json: list[int]
    total_cost_min: float | None = None
    total_cost_max: float | None = None
    warnings_count: int = 0
    blocking_error_count: int = 0
    created_at: datetime
    updated_at: datetime | None = None
    # Field hiển thị cho list 2 tầng (đều optional — client cũ không vỡ)
    customer_id: int | None = None
    customer_name: str | None = None
    spec_summary: str | None = None          # "21×29,7 cm · Couche 150gsm · 4 màu/2 mặt"
    machine_type: str | None = None          # offset | digital — chip công nghệ
    unit_cost_min: float | None = None       # giá vốn/đơn thấp nhất giữa các mức SL
    created_by_name: str | None = None

class EstimateListOut(BaseModel):
    items: list[EstimateRow]
    total: int
    page: int
    size: int


class EstimateStatsOut(BaseModel):
    """Số đếm cho thanh tab trang list."""
    total: int
    draft: int
    calculated: int
    blocking: int
