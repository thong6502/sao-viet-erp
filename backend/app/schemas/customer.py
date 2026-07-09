"""Pydantic request/response models for the Khách hàng (CRM) API — spec-06.

Field-level constraints here are the first line of validation (400/422 shape); the
service enforces the domain rules (MST format, non-blank name, duplicate-check-soft).
"""
from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field


class _PaymentDiscountFields(BaseModel):
    """Điều khoản thanh toán riêng (#12, dữ liệu chờ Công nợ) + chiết khấu mặc định
    theo KH (#14 — chỉ nhận khi caller có quyền chi tiết `view_discount`, service bỏ
    qua nếu thiếu quyền)."""

    payment_term_type: str | None = Field(default=None, max_length=24)
    payment_term_days: int | None = Field(default=None, ge=0)
    prepay_pct: float | None = Field(default=None, ge=0, le=100)
    payment_term_note: str | None = Field(default=None, max_length=500)
    discount_trade_pct: float | None = Field(default=None, ge=0, le=100)
    discount_buyer_pct: float | None = Field(default=None, ge=0, le=100)


class CustomerCreate(_PaymentDiscountFields):
    name: str = Field(min_length=1, max_length=255)
    tax_code: str | None = Field(default=None, max_length=20)
    phone: str | None = Field(default=None, max_length=30)
    email: str | None = Field(default=None, max_length=255)
    address: str | None = Field(default=None, max_length=500)
    contact_name: str | None = Field(default=None, max_length=255)
    # ≥ 0 enforced here AND in the service (defense in depth).
    credit_limit: int = Field(default=0, ge=0)
    sale_user_id: int | None = None
    # lead = tiềm năng (khảo sát #22) — cho tạo thẳng khách tiềm năng.
    status: str = Field(default="active")


class CustomerUpdate(_PaymentDiscountFields):
    name: str = Field(min_length=1, max_length=255)
    tax_code: str | None = Field(default=None, max_length=20)
    phone: str | None = Field(default=None, max_length=30)
    email: str | None = Field(default=None, max_length=255)
    address: str | None = Field(default=None, max_length=500)
    contact_name: str | None = Field(default=None, max_length=255)
    credit_limit: int = Field(default=0, ge=0)
    sale_user_id: int | None = None
    # lead = tiềm năng, active = đang giao dịch, inactive = ngừng giao dịch.
    status: str = Field(default="active")


class DuplicateRef(BaseModel):
    """Points at an existing customer that already carries the submitted MST (soft warn)."""

    id: int
    code: str
    name: str


class DuplicateWarn(BaseModel):
    """Một cảnh báo trùng MỀM (khảo sát #8/#15: check theo MST + tên cty + email —
    cảnh báo, không chặn). `field` ∈ tax_code|name|email."""

    field: str
    id: int
    code: str
    name: str


class CustomerRow(BaseModel):
    """A row in the Danh bạ list. `receivable` stays None + `no_ar_module=True` until
    Công nợ (SEAM-16) is built — never a fabricated 0. The `tier` / `revenue_12m` /
    `orders_total` / `last_order_at` fields are DERIVED FROM REAL ORDERS (feat-CRM360),
    default to the honest zero/None when the customer has no history."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    name: str
    tax_code: str | None
    phone: str | None
    email: str | None = None
    address: str | None = None
    contact_name: str | None = None
    credit_limit: int
    sale_user_id: int | None
    sale_name: str | None = None
    status: str
    created_at: datetime | None = None
    # Công nợ (chỉ-đọc). None + no_ar_module → UI shows "—" / "Chưa có phân hệ Công nợ".
    receivable: int | None = None
    no_ar_module: bool = True
    # --- derived from real orders (CRM-360) ---
    tier: str = "regular"
    revenue_12m: int = 0
    orders_total: int = 0
    last_order_at: date | None = None
    # --- Điều khoản thanh toán (#12) — hiển thị cho mọi người có quyền read ---
    payment_term_type: str | None = None
    payment_term_days: int | None = None
    prepay_pct: float | None = None
    payment_term_note: str | None = None
    # --- Chiết khấu mặc định (#14) — router ẨN (None + discount_hidden=True) khi
    # caller thiếu quyền chi tiết `view_discount`; không bao giờ trả 0 giả ---
    discount_trade_pct: float | None = None
    discount_buyer_pct: float | None = None
    discount_hidden: bool = False


class CustomerKpis(BaseModel):
    """The list header KPI strip — rolled up over the whole scoped book, real orders."""

    total_customers: int
    loyal_count: int
    new_this_month: int
    avg_order_value: int


class CustomerListOut(BaseModel):
    items: list[CustomerRow]
    total: int
    page: int
    size: int
    kpis: CustomerKpis


class CustomerCreateOut(BaseModel):
    """Create/update response: the customer + soft duplicate warnings (không chặn).
    `duplicate` giữ lại cho chỗ gọi cũ (= cảnh báo MST đầu tiên); `duplicates` là danh
    sách đầy đủ theo MST + tên cty + email."""

    customer: CustomerRow
    duplicate: DuplicateRef | None = None
    duplicates: list[DuplicateWarn] = []


# --- Người liên hệ (#10–#11) -----------------------------------------------


class ContactIn(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    title: str | None = Field(default=None, max_length=120)
    duty: str | None = Field(default=None, max_length=255)
    phone: str | None = Field(default=None, max_length=30)
    email: str | None = Field(default=None, max_length=255)
    is_primary: bool = False


class ContactOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    title: str | None = None
    duty: str | None = None
    phone: str | None = None
    email: str | None = None
    is_primary: bool


class ContactsOut(BaseModel):
    items: list[ContactOut]


# --- Địa chỉ giao hàng (#9) --------------------------------------------------


class AddressIn(BaseModel):
    label: str = Field(min_length=1, max_length=120)
    address: str = Field(min_length=1, max_length=500)
    phone: str | None = Field(default=None, max_length=30)
    note: str | None = Field(default=None, max_length=500)
    is_default: bool = False


class AddressOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    label: str
    address: str
    phone: str | None = None
    note: str | None = None
    is_default: bool


class AddressesOut(BaseModel):
    items: list[AddressOut]


# --- Tài liệu đính kèm (#21) --------------------------------------------------


class CustomerAttachmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    doc_kind: str
    file_name: str
    file_url: str
    file_type: str | None = None
    uploaded_at: datetime


class CustomerAttachmentsOut(BaseModel):
    items: list[CustomerAttachmentOut]


# --- Chăm sóc khách hàng (#20/#27/#28) -----------------------------------------


class CareEventIn(BaseModel):
    kind: str = Field(default="khac", max_length=24)
    note: str = Field(min_length=1, max_length=1000)
    # Cho phép ghi bù (buổi gặp hôm qua); bỏ trống = bây giờ.
    happened_at: datetime | None = None


class CareEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    kind: str
    note: str
    happened_at: datetime
    actor_name: str | None = None


class CareEventsOut(BaseModel):
    items: list[CareEventOut]


class CareTaskIn(BaseModel):
    note: str = Field(min_length=1, max_length=500)
    due_date: datetime
    assignee_user_id: int | None = None


class CareTaskOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    note: str
    due_date: datetime
    status: str
    assignee_user_id: int | None = None
    assignee_name: str | None = None
    done_at: datetime | None = None
    # Mức nhắc TÍNH TỪ số ngày quá hạn (#28): 0 = chưa đến hạn, 1 = đến hạn/quá <2 ngày,
    # 2 = quá ≥2 ngày, 3 = quá ≥5 ngày. Chỉ có nghĩa với việc đang mở.
    remind_level: int = 0
    overdue_days: int = 0


class CareTasksOut(BaseModel):
    items: list[CareTaskOut]
    # Đánh giá chăm sóc (#28 — "nhắc lần 1,2,3 sẽ đánh giá tiêu chuẩn chăm sóc"):
    # đếm việc đã xong đúng hạn / xong trễ / đang quá hạn — số thật từ tasks.
    done_on_time: int = 0
    done_late: int = 0
    overdue_open: int = 0


class CareTaskStatusIn(BaseModel):
    """Đổi trạng thái việc chăm sóc: done | cancelled | open (mở lại)."""

    status: str
    # Khi hoàn thành có thể ghi luôn một dòng nhật ký chăm sóc (kind + note).
    log_kind: str | None = Field(default=None, max_length=24)
    log_note: str | None = Field(default=None, max_length=1000)


class FollowupRow(BaseModel):
    """Một việc đến hạn/quá hạn trong panel "Cần chăm sóc" trên danh bạ."""

    id: int
    customer_id: int
    customer_code: str
    customer_name: str
    note: str
    due_date: datetime
    remind_level: int
    overdue_days: int
    assignee_name: str | None = None


class FollowupsOut(BaseModel):
    items: list[FollowupRow]


# --- Import CSV (#23) ---------------------------------------------------------


class ImportRowResult(BaseModel):
    """Kết quả một dòng import: `row` là số dòng trong file (1-based, không tính header).
    status ∈ created|warning|error — warning = đã tạo nhưng có cảnh báo trùng."""

    row: int
    status: str
    message: str | None = None
    code: str | None = None
    name: str | None = None


class ImportResultOut(BaseModel):
    """Tổng kết import. `dry_run=True` → chưa ghi gì, chỉ xem trước."""

    dry_run: bool
    total: int
    created: int
    warnings: int
    errors: int
    rows: list[ImportRowResult]


class ReceivableCard(BaseModel):
    """The read-only Công nợ card on the detail screen (spec-06 KH-04).

    When Công nợ is not built (SEAM-16), `available=False` and every number is None —
    the UI renders "Chưa có phân hệ Công nợ", NOT a fake 0.
    """

    available: bool
    credit_limit: int
    balance: int | None = None
    usage_pct: int | None = None
    over_limit: bool | None = None
    message: str | None = None


class CustomerDetailOut(BaseModel):
    customer: CustomerRow
    receivable: ReceivableCard


class SaleOption(BaseModel):
    """A selectable Sale (owner) for the create/edit form filters."""

    id: int
    name: str


class CustomerReassignIn(BaseModel):
    """Điều chuyển khách hàng (trưởng phòng KD). Hai chế độ:
    - `customer_ids` (checkbox): chuyển các khách được chọn; hoặc
    - `from_sale_user_id`: chuyển TOÀN BỘ khách của một Sale.
    `to_sale_user_id` là nhân viên đích (bắt buộc)."""

    to_sale_user_id: int
    customer_ids: list[int] | None = None
    from_sale_user_id: int | None = None


class CustomerReassignOut(BaseModel):
    moved: int
    skipped: int = 0


# --- CRM-360 Object-page Dashboard (spec-06, computed from real orders/quotations) ---


class MonthPointOut(BaseModel):
    month: str
    label: str
    revenue: int
    orders: int


class ProductSliceOut(BaseModel):
    label: str
    revenue: int
    orders: int


class HeatCellOut(BaseModel):
    month_index: int
    weekday: int
    count: int


class CustomerDashboardOut(BaseModel):
    """The Dashboard tab: every figure computed from real orders/quotations. When the
    customer has no history `has_data=False` and the UI shows an honest empty state."""

    revenue_12m: int
    orders_12m: int
    avg_order_value: int | None
    orders_total: int
    quotes_total: int
    win_rate_pct: int | None
    first_order_at: date | None
    last_order_at: date | None
    tier: str
    months: list[MonthPointOut]
    product_mix: list[ProductSliceOut]
    heatmap: list[HeatCellOut]
    has_data: bool
    # Công nợ chỉ-đọc card reused from detail (SEAM-16 aware).
    receivable: ReceivableCard


class OrderHistoryRowOut(BaseModel):
    id: int
    order_no: str
    status: str
    order_kind: str
    summary: str
    total: int | None
    created_at: datetime


class OrderHistoryOut(BaseModel):
    items: list[OrderHistoryRowOut]


class QuoteHistoryRowOut(BaseModel):
    id: int
    code: str
    version: int
    status: str
    total: int | None
    valid_until: date | None
    created_at: datetime


class QuoteHistoryOut(BaseModel):
    items: list[QuoteHistoryRowOut]


# --- Nhật ký khách hàng (unified activity timeline, real events) ---------------


class CustomerAuditRowOut(BaseModel):
    """One entry in a customer's Nhật ký. Merges profile edits (from the audit log) with
    real document events (orders/quotations). `ref_type`/`ref_id` let the UI drill through
    to the source document; profile rows carry neither."""

    at: datetime
    kind: str  # "profile" | "order" | "quote"
    action: str
    title: str
    detail: str
    actor_name: str | None = None
    ref_type: str | None = None  # "order" | "quotation"
    ref_id: int | None = None


class CustomerAuditOut(BaseModel):
    items: list[CustomerAuditRowOut]


# Reuse for created_at exposure if needed later.
__all__ = [
    "CustomerCreate",
    "CustomerUpdate",
    "DuplicateWarn",
    "ContactIn",
    "ContactOut",
    "ContactsOut",
    "AddressIn",
    "AddressOut",
    "AddressesOut",
    "CustomerAttachmentOut",
    "CustomerAttachmentsOut",
    "ImportRowResult",
    "ImportResultOut",
    "CustomerRow",
    "CustomerKpis",
    "CustomerListOut",
    "CustomerCreateOut",
    "CustomerDetailOut",
    "ReceivableCard",
    "DuplicateRef",
    "SaleOption",
    "MonthPointOut",
    "ProductSliceOut",
    "HeatCellOut",
    "CustomerDashboardOut",
    "OrderHistoryRowOut",
    "OrderHistoryOut",
    "QuoteHistoryRowOut",
    "QuoteHistoryOut",
    "CustomerAuditRowOut",
    "CustomerAuditOut",
]
