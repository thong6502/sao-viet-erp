"""Pydantic request/response models for the Báo giá (Quotation / Quote) API — spec-09.
"""
from __future__ import annotations

from datetime import date, datetime
from pydantic import BaseModel, ConfigDict, Field


class QuoteItemUpdate(BaseModel):
    id: int
    margin_percent: float = Field(default=20.0)
    manual_selling_price: float | None = None
    manual_unit_price: float | None = None
    discount_amount: float = Field(default=0.0)
    discount_percent: float = Field(default=0.0)
    vat_percent: float = Field(default=10.0)
    rounding: str = Field(default="no_rounding")
    note: str | None = None
    po_code: str | None = None


# --- create / update ----------------------------------------------------------

class QuotePick(BaseModel):
    """1 phiếu tính giá + các mức số lượng (option) được chọn vào báo giá."""
    estimate_id: int
    option_ids: list[int] = Field(min_length=1)


class QuotationCreate(BaseModel):
    customer_id: int | None = None
    # BG-1 (nguồn MỚI): 1 Phiếu tính giá (PTG) → 1 báo giá. Ưu tiên nếu có.
    phieu_tinh_gia_id: int | None = None
    # Đường cũ (1 phiếu): estimate_id + selected_option_ids — giữ tương thích (gỡ ở BG-4).
    estimate_id: int | None = None
    selected_option_ids: list[int] | None = None
    # Đường cũ (đa phiếu): mỗi pick = 1 phiếu tính giá + option đã tick.
    picks: list[QuotePick] | None = None
    margin_percent: float | None = None  # gói biên áp chung khi tạo (per dòng chỉnh sau)
    valid_until: date | None = None
    payment_terms: str | None = None
    delivery_terms: str | None = None
    delivery_address: str | None = None
    customer_note: str | None = None
    internal_note: str | None = None


class QuotationUpdate(BaseModel):
    customer_id: int | None = None
    valid_until: date | None = None
    payment_terms: str | None = None
    delivery_terms: str | None = None
    delivery_address: str | None = None
    customer_note: str | None = None
    internal_note: str | None = None
    items: list[QuoteItemUpdate] | None = None


class TransitionRequest(BaseModel):
    to_status: str = Field(min_length=1, max_length=20)
    cancel_reason: str | None = Field(default=None, max_length=500)


# --- outputs ------------------------------------------------------------------

class CustomerDisplayOut(BaseModel):
    customer_id: int
    name: str
    tax_code: str | None = None
    credit_status_display: str


class QuotationRow(BaseModel):
    id: int
    code: str
    version: int
    customer_id: int | None
    customer_name: str | None = None
    total: int | None
    status: str
    valid_until: date | None
    # Field hiển thị list 2 tầng (đều optional — client cũ không vỡ)
    version_count: int = 1
    sent_at: datetime | None = None          # tính tuổi phiếu "đã gửi N ngày"
    margin_percent: float | None = None      # % biên dòng đầu (hiển thị markup)
    estimate_refs: list[str] = []            # các mã phiếu tính giá tham chiếu (↳ TG26-xxxx)
    product_summary: str | None = None       # "Catalogue A4 + 2 SP khác"
    updated_at: datetime | None = None
    salesperson_name: str | None = None


class QuotationListOut(BaseModel):
    items: list[QuotationRow]
    total: int
    page: int
    size: int


class QuotationStatsOut(BaseModel):
    """Số đếm cho thanh tab list Báo giá."""
    total: int
    draft: int
    sent: int
    accepted: int
    rejected: int
    expired: int
    converted_to_order: int
    cancelled: int
    need_action: int  # draft + sent (cần tôi xử lý: soạn tiếp / follow-up)


class VersionRow(BaseModel):
    id: int
    version: int
    status: str
    total: int | None
    created_at: datetime
    change_reason: str | None = None


class QuoteItemOut(BaseModel):
    id: int
    estimate_id: int | None = None
    estimate_number: str | None = None   # mã phiếu tính giá gốc của dòng (↳ link)
    estimate_option_id: int | None
    line_no: int
    po_code: str | None = None
    product_type: str
    product_name: str
    product_spec_text: str | None
    quantity: int
    unit: str
    total_cost_snapshot: float
    margin_percent: float
    selling_price: float
    unit_price: float
    discount_amount: float
    vat_percent: float
    vat_amount: float
    final_amount: float
    note: str | None


class QuotationDetailOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str  # maps to quote_number
    version: int  # maps to current version_number
    customer_id: int | None
    customer: CustomerDisplayOut | None = None
    estimate_id: int | None
    phieu_tinh_gia_id: int | None = None
    phieu_tinh_gia_ma: str | None = None
    valid_until: date | None
    status: str
    cancel_reason: str | None
    payment_terms: str | None
    delivery_terms: str | None
    delivery_address: str | None
    contact_name_snapshot: str | None = None
    contact_phone_snapshot: str | None = None
    contact_title_snapshot: str | None = None
    customer_note: str | None
    internal_note: str | None
    
    # Financial snapshot totals from active version
    total_cost: float
    subtotal_amount: float
    discount_amount: float
    vat_amount: float
    total: float  # maps to final_amount
    
    versions: list[VersionRow] = Field(default_factory=list)
    items: list[QuoteItemOut] = Field(default_factory=list)
    allowed_transitions: list[str] = Field(default_factory=list)
    can_approve: bool = False
    # BG-2 — báo giá đặc thù (GĐ duyệt trước khi gửi khách). `exceptions` = nhãn định tính (an toàn);
    # `margin_pct` nhạy cảm (router STRIP nếu người xem không có quyền duyệt đặc thù).
    exception_required: bool = False
    exception_status: str = "none"        # none|pending|approved|rejected|stale
    exception_cleared: bool = True
    exceptions: list[dict] = Field(default_factory=list)   # [{key,label}]
    exception_note: str | None = None
    margin_pct: int | None = None
    # Ai SOẠN (để người duyệt biết báo giá của NV nào) + ai ĐÃ DUYỆT/từ chối (để NV biết ai xử lý).
    salesperson_id: int | None = None
    salesperson_name: str | None = None
    exception_decision: str | None = None            # approved | rejected của lần quyết định gần nhất
    exception_decided_by_name: str | None = None     # tên người đã duyệt/từ chối
    exception_decided_at: datetime | None = None


class QuoteApprovalIn(BaseModel):
    """GĐ duyệt / từ chối báo giá đặc thù. `note` = lý do (khuyến nghị khi từ chối)."""

    decision: str = Field(min_length=1, max_length=16)   # approved | rejected
    note: str | None = Field(default=None, max_length=1000)


class QuoteApprovalOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    quote_id: int
    decision: str
    triggers_json: list[str] | None = None
    total: int
    subtotal: int
    cost: int | None = None
    margin_pct_snapshot: int | None = None
    min_margin_pct: int | None = None
    high_value_threshold: int | None = None
    note: str | None = None
    decided_by: int | None = None
    decided_at: datetime


class QuoteApprovalListOut(BaseModel):
    items: list[QuoteApprovalOut]


class EnumOption(BaseModel):
    value: str
    label: str


class QuotationEnumsOut(BaseModel):
    statuses: list[EnumOption]


class CostingQtyOption(BaseModel):
    id: int
    quantity: int
    total_cost: int
    margin_percent: float
    selling_price: float
    discount_amount: float
    vat_percent: float
    final_price: float
    unit_price: float
    actual_margin: float


class CostingPickerOut(BaseModel):
    available: bool
    message: str | None = None
    options: list[CostingQtyOption] | None = None


__all__ = [
    "QuotationCreate",
    "QuotationUpdate",
    "TransitionRequest",
    "CustomerDisplayOut",
    "QuotationRow",
    "QuotationListOut",
    "VersionRow",
    "QuoteItemOut",
    "QuotationDetailOut",
    "EnumOption",
    "QuotationEnumsOut",
    "CostingQtyOption",
    "CostingPickerOut",
]
