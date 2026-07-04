"""Pydantic schemas for the Operations API — spec-20/21 + spec §A–§G (Công đoạn & Đơn giá gia công).
"""
from __future__ import annotations

from datetime import date, datetime
from pydantic import BaseModel, ConfigDict, Field

class OperationRateCreate(BaseModel):
    setup_fee: int = Field(default=0, ge=0)
    run_rate: int = Field(default=0, ge=0)
    labor_rate: int = Field(default=0, ge=0)
    min_charge: int = Field(default=0, ge=0)
    speed: float = Field(default=0.0, ge=0)
    setup_time_mins: float = Field(default=0.0, ge=0)
    # §C — đơn giá giờ máy nội bộ
    hourly_rate: int = Field(default=0, ge=0)
    # §D — nhân công đa hình thức
    labor_shift_rate: int = Field(default=0, ge=0)
    labor_fixed: int = Field(default=0, ge=0)
    labor_min: int = Field(default=0, ge=0)
    # §F — khuôn
    tooling_unit_price: int = Field(default=0, ge=0)
    # §E — thuê ngoài
    outsource_supplier: str | None = Field(default=None, max_length=255)
    outsource_unit_price: int = Field(default=0, ge=0)
    outsource_setup_fee: int = Field(default=0, ge=0)
    outsource_min_charge: int = Field(default=0, ge=0)
    outsource_transport_fee: int = Field(default=0, ge=0)
    outsource_moq: int = Field(default=0, ge=0)
    outsource_lead_time_days: int = Field(default=0, ge=0)
    effective_from: date

class OperationRateOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    setup_fee: int
    run_rate: int
    labor_rate: int
    min_charge: int
    speed: float
    setup_time_mins: float
    hourly_rate: int
    labor_shift_rate: int
    labor_fixed: int
    labor_min: int
    tooling_unit_price: int
    outsource_supplier: str | None
    outsource_unit_price: int
    outsource_setup_fee: int
    outsource_min_charge: int
    outsource_transport_fee: int
    outsource_moq: int
    outsource_lead_time_days: int
    effective_from: date
    effective_to: date | None
    created_at: datetime

class OperationCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    # in, can_mang, be, gap, dong_cuon, dong_goi...
    operation_type: str = Field(min_length=1, max_length=32)
    unit: str = Field(min_length=1, max_length=16) # m2, luot, to, cuon, san_pham...
    basis_quantity: str = Field(default="to", max_length=16)  # đại lượng engine nhân run_rate
    pricing_method: str = Field(default="theo_sp", max_length=16)  # none/theo_gio/theo_ca/theo_sp/khoan
    # §A
    process_group: str = Field(default="sau_in", max_length=20)  # sau_in/dong_goi/dac_biet
    process_type: str = Field(default="internal", max_length=16)  # internal/outsource/both
    default_sequence: int = Field(default=0, ge=0)
    # §B
    quantity_formula_type: str = Field(default="print_sheet_qty", max_length=20)
    allow_manual_quantity: bool = False
    # §C
    internal_pricing_method: str = Field(default="per_qty", max_length=16)  # per_qty/per_hour/combined
    labor_people_count: float = Field(default=1.0, ge=0)
    # §F
    has_tooling: bool = False
    tooling_type: str | None = Field(default=None, max_length=20)
    # Link tới bảng giá khuôn ở DM Đơn giá kẽm & khuôn (#5). NULL = dùng tooling_unit_price cũ.
    tooling_rate_id: int | None = None
    # §G
    has_yield_loss: bool = False
    default_yield_rate: float | None = Field(default=None, ge=0, le=100)
    default_yield_rule: str | None = Field(default=None, max_length=40)
    # kept for backward compatibility (derived from process_type when omitted)
    allow_outsource: bool = False
    is_active: bool = True

class OperationUpdate(OperationCreate):
    """Same as create; code is read-only and is not sent."""

class OperationRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    name: str
    operation_type: str
    unit: str
    basis_quantity: str
    pricing_method: str
    process_group: str
    process_type: str
    default_sequence: int
    quantity_formula_type: str
    allow_manual_quantity: bool
    internal_pricing_method: str
    labor_people_count: float
    has_tooling: bool
    tooling_type: str | None
    tooling_rate_id: int | None = None
    has_yield_loss: bool
    default_yield_rate: float | None
    default_yield_rule: str | None
    allow_outsource: bool
    is_active: bool
    rates: list[OperationRateOut] = Field(default_factory=list)

class OperationListOut(BaseModel):
    items: list[OperationRow]
    total: int
    page: int
    size: int

class OperationDetailOut(OperationRow):
    created_at: datetime
    updated_at: datetime


# --- Test nhanh công thức (spec §4.7 Tab Test) ---------------------------
class OperationPreviewIn(BaseModel):
    """Input test cho tab 'Test nhanh' — mô phỏng lượng & cách làm rồi trả breakdown chi phí."""
    sheet_qty: float = Field(default=0.0, ge=0)       # số tờ sản xuất
    finished_qty: float = Field(default=0.0, ge=0)    # số thành phẩm
    area_m2: float = Field(default=0.0, ge=0)         # diện tích 1 tờ (m²)
    book_qty: float = Field(default=0.0, ge=0)        # số cuốn
    manual_qty: float = Field(default=0.0, ge=0)      # nhập tay
    execution_mode: str = Field(default="internal")   # internal / outsourced

class OperationPreviewComponent(BaseModel):
    label: str
    formula: str
    amount: float

class OperationPreviewOut(BaseModel):
    operation_name: str
    execution_mode: str
    quantity: float
    unit: str
    components: list[OperationPreviewComponent]
    total: float
    warnings: list[str] = Field(default_factory=list)
