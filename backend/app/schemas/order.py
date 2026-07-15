"""Pydantic request/response models for the Đơn hàng bán (Order) API — spec-10.

Field constraints here are the first line of validation (422 shape); OrderService enforces
the domain rules (báo giá approved còn hạn, đơn bổ sung bắt buộc parent, gate ③→④, transition
legality). The physical layer (khổ giấy / số màu / số kẽm / imposition / PrintForm) is NEVER
part of any response shape here — ẩn khỏi Sale (§29 P0, §43 #1).
"""
from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field


# --- create (from an approved quotation) --------------------------------------

class OrderCreate(BaseModel):
    # F1: the approved quotation this order references (SEAM-04 quotation_ref, Báo giá LIVE).
    quotation_id: int
    # F2 loại đơn.
    order_type: str = Field(min_length=1, max_length=16)
    order_kind: str = Field(min_length=1, max_length=16)
    # Đơn bổ sung → BẮT BUỘC (service enforces). Đơn mới → bỏ qua.
    parent_order_id: int | None = None
    # F4 cờ ứng giấy khách (chi tiết lô sống ở Kho — SEAM-06, TREO).
    has_customer_paper: bool = False
    # VAT DỰ KIẾN để ước tổng (chân lý ở InvoiceLine ⑬).
    vat_pct_estimate: int = Field(default=0, ge=0, le=100)


class TransitionRequest(BaseModel):
    """Move an order to `to_status` (ordered/on_hold/change_order/cancelled)."""

    to_status: str = Field(min_length=1, max_length=16)
    cancel_reason: str | None = Field(default=None, max_length=500)


# --- outputs ------------------------------------------------------------------

class OrderLineOut(BaseModel):
    """One order-line — mô tả SP thương mại + snapshot giá. NEVER a physical field."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    description: str
    qty: int
    unit_price_snapshot: int | None
    norm_snapshot: dict | None
    vat_pct_estimate: int
    line_total: int | None


class ExceptionOut(BaseModel):
    """Một điều kiện 'đơn đặc thù' đang bật (A2) — nhãn ĐỊNH TÍNH, an toàn cho mọi vai."""

    key: str            # high_value | low_margin | below_cost
    label: str


class GateOut(BaseModel):
    """The ③→④ gate view (F3). deposit_paid=null + deposit_available=false while SEAM-04
    (Payment) is TREO — never a fabricated paid amount. A2: thêm khối 'đơn đặc thù' (GĐ duyệt)."""

    total: int
    total_payment: int = 0          # tổng GỒM VAT — base tính cọc (cọc là tiền thật khách đưa)
    min_deposit_pct: int
    deposit_required: int
    deposit_paid: int | None = None
    deposit_available: bool
    deposit_shortfall: int
    quotation_approved: bool
    all_lines_priced: bool = True   # còn dòng chưa định giá thì chặn chốt (cọc yêu cầu sẽ thiếu)
    # A2 — đơn đặc thù (Giám đốc duyệt mới chốt được).
    exception_required: bool = False
    exception_status: str = "none"  # none | pending | approved | rejected | stale
    exception_cleared: bool = True
    exceptions: list[ExceptionOut] = Field(default_factory=list)
    exception_note: str | None = None
    margin_pct: int | None = None   # số NHẠY CẢM — router strip nếu người xem không có quyền duyệt
    can_confirm: bool


class OrderRow(BaseModel):
    """A row in the Danh sách list: order_no, khách, loại đơn, trạng thái, tổng dự kiến,
    cờ 2 cổng (③→④ computed; ⑤→⑥ chỉ-báo qua SEAM-05 read-only)."""

    id: int
    order_no: str
    customer_id: int | None
    customer_name: str | None = None
    order_type: str
    order_kind: str
    status: str
    total_estimate: int | None
    has_customer_paper: bool
    gate_ordered_ok: bool           # ③→④ đã đạt (approved AND cọc ≥ ngưỡng)
    created_at: datetime


class OrderListOut(BaseModel):
    items: list[OrderRow]
    total: int
    page: int
    size: int


class CustomerDisplayOut(BaseModel):
    """Read-only customer display (kéo từ báo giá). NOT a block gate."""

    customer_id: int
    name: str
    tax_code: str | None = None
    credit_status_display: str


class OrderDetailOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    order_no: str
    customer_id: int | None
    customer: CustomerDisplayOut | None = None
    quotation_id: int | None
    quotation_version: int | None
    quotation_effective_from: date | None
    order_type: str
    order_kind: str
    parent_order_id: int | None
    status: str
    has_customer_paper: bool
    vat_pct_estimate: int
    cancel_reason: str | None
    cancelled_at_state: str | None
    created_at: datetime
    lines: list[OrderLineOut] = Field(default_factory=list)
    gate: GateOut | None = None
    allowed_transitions: list[str] = Field(default_factory=list)


class EnumOption(BaseModel):
    value: str
    label: str


class OrderEnumsOut(BaseModel):
    order_types: list[EnumOption]
    order_kinds: list[EnumOption]
    statuses: list[EnumOption]


class ApprovedQuotationRow(BaseModel):
    """A choosable báo giá đã duyệt còn hạn (F1 picker). Đối ngoại fields only — no buildup."""

    id: int
    code: str
    version: int
    customer_id: int | None
    customer_name: str | None = None
    total: int | None
    valid_until: date | None


class ApprovedQuotationListOut(BaseModel):
    items: list[ApprovedQuotationRow]


# --- payments (ghi cọc — SEAM-04 deposit, feat-048) ---------------------------

class PaymentIn(BaseModel):
    """Ghi một khoản CỌC cho đơn (mở khóa cổng chốt ③→④). customer_id LẤY TỪ ĐƠN (không nhận
    từ client). Cọc KHÔNG sinh hóa đơn (N5)."""

    amount: int = Field(gt=0, description="Số tiền cọc (VND), > 0")
    method: str = Field(default="bank", min_length=1, max_length=16)   # cash | bank
    note: str | None = Field(default=None, max_length=500)


class PaymentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    order_id: int
    customer_id: int | None
    kind: str
    direction: str
    amount: int
    method: str
    paid_at: datetime
    voucher_no: str | None
    note: str | None


class PaymentListOut(BaseModel):
    items: list[PaymentOut]
    deposit_total: int


# --- A2: duyệt "đơn đặc thù" (Giám đốc) ---------------------------------------

class ApprovalIn(BaseModel):
    """GĐ duyệt / từ chối đơn đặc thù. `note` = lý do (khuyến nghị khi từ chối)."""

    decision: str = Field(min_length=1, max_length=16)   # approved | rejected
    note: str | None = Field(default=None, max_length=1000)


class ApprovalOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    order_id: int
    decision: str
    triggers_json: list[str] | None = None
    order_total: int
    order_subtotal: int
    order_cost: int | None = None
    margin_pct_snapshot: int | None = None
    min_margin_pct: int | None = None
    high_value_threshold: int | None = None
    note: str | None = None
    decided_by: int | None = None
    decided_at: datetime


class ApprovalListOut(BaseModel):
    items: list[ApprovalOut]


__all__ = [
    "OrderCreate",
    "TransitionRequest",
    "OrderLineOut",
    "GateOut",
    "OrderRow",
    "OrderListOut",
    "CustomerDisplayOut",
    "OrderDetailOut",
    "EnumOption",
    "OrderEnumsOut",
    "ApprovedQuotationRow",
    "ApprovedQuotationListOut",
    "PaymentIn",
    "PaymentOut",
    "PaymentListOut",
    "ExceptionOut",
    "ApprovalIn",
    "ApprovalOut",
    "ApprovalListOut",
]
