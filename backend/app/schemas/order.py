"""Đơn hàng bán (Order) API schemas — redesign-don-hang-ban.md (P1 khung đơn)."""
from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field


# --- Dòng đơn ------------------------------------------------------------------
class OrderLineIn(BaseModel):
    """Dòng nhập tay (nguồn nhap_tay). Đơn từ báo giá snapshot dòng từ báo giá, không nhận ở đây."""
    description: str = ""
    qty: int = Field(default=1, ge=1)
    unit_price: int | None = None       # đơn giá (VND, trước VAT) sale gõ
    vat_pct: int = Field(default=0, ge=0, le=100)


class OrderLineOut(BaseModel):
    id: int
    description: str
    qty: int
    unit_price_snapshot: int | None
    vat_pct_estimate: int
    line_total: int | None
    cost_snapshot: int | None
    model_config = ConfigDict(from_attributes=True)


# --- Đính kèm (chung cho consent + minh chứng cọc) ---------------------------
class AttachmentOut(BaseModel):
    id: int
    url: str
    file_name: str | None
    content_type: str | None
    uploaded_at: datetime


# --- Cọc (P2) -----------------------------------------------------------------
class OrderDepositIn(BaseModel):
    deposit_kind: str = "ck"                 # ck | tien_mat | vat_tu_ung | can_tru_cong_no
    amount_expected: int = Field(default=0, ge=0)
    amount_received: int = Field(default=0, ge=0)
    reconciled: bool = False                 # chỉ có nghĩa với CK
    note: str | None = None
    received_at: date | None = None


class ApprovalActionIn(BaseModel):
    note: str | None = None


class OrderCancelIn(BaseModel):
    reason: str
    fault: str | None = None   # khach | xuong — BẮT BUỘC khi hủy đơn đã chốt


class OrderApprovalOut(BaseModel):
    id: int
    decision: str
    triggers_json: list | None = None
    note: str | None
    decided_by: int | None
    decided_by_name: str | None = None
    decided_at: datetime
    order_total: int
    order_subtotal: int
    order_cost: int | None
    margin_pct_snapshot: int | None
    model_config = ConfigDict(from_attributes=True)


class OrderDepositOut(BaseModel):
    id: int
    deposit_kind: str
    amount_expected: int
    amount_received: int
    reconciled: bool
    reconciled_by: int | None
    reconciled_at: datetime | None
    note: str | None
    received_at: date | None
    recorded_by: int | None
    recorded_by_name: str | None = None
    created_at: datetime
    attachments: list[AttachmentOut] = []
    model_config = ConfigDict(from_attributes=True)


# --- Tạo / sửa -----------------------------------------------------------------
class OrderCreate(BaseModel):
    # source_type ∈ {bao_gia, nhap_tay}
    source_type: str = "bao_gia"
    # bao_gia: báo giá đã duyệt (accepted). nhap_tay: bỏ qua.
    quotation_id: int | None = None
    # đơn bổ sung: order_kind=bo_sung + parent_order_id (đơn gốc giữ kẽm)
    order_kind: str = "moi"
    parent_order_id: int | None = None
    order_nature: str = "hang_hoa"      # hang_hoa | gia_cong
    # nhập tay:
    customer_id: int | None = None
    lines: list[OrderLineIn] = Field(default_factory=list)
    vat_pct_estimate: int = 0
    # % cọc do sale nhập TRÊN ĐƠN (0–100). None: đơn báo giá ghim từ báo giá; đơn nhập tay = chưa đặt.
    deposit_pct: float | None = None
    # thông tin đặt hàng (tùy chọn lúc tạo, sửa sau khi nháp):
    customer_po_no: str | None = None
    delivery_committed_date: date | None = None
    delivery_address: str | None = None
    invoice_entity_name: str | None = None
    invoice_entity_tax_code: str | None = None


class OrderUpdate(BaseModel):
    """Chỉ sửa khi đơn còn NHÁP — chỉ thông tin ĐẶT HÀNG. Dòng + giá + VAT BẤT BIẾN (đổi = tạo
    nháp mới), KHÔNG sửa qua đây. Field None = giữ nguyên."""
    order_nature: str | None = None
    deposit_pct: float | None = None   # % cọc — sale sửa trên đơn khi còn nháp
    customer_po_no: str | None = None
    delivery_committed_date: date | None = None
    delivery_address: str | None = None
    invoice_entity_name: str | None = None
    invoice_entity_tax_code: str | None = None


# --- Đọc -----------------------------------------------------------------------
class OrderRow(BaseModel):
    id: int
    order_no: str
    customer_id: int | None
    customer_name: str | None
    quotation_id: int | None
    quotation_code: str | None = None   # mã báo giá (BG26-xxxx) để hiển thị, None nếu nhập tay
    source_type: str
    order_kind: str
    order_nature: str
    status: str
    approval_state: str
    needs_approval: bool
    cost_basis: str
    total: int | None                   # Σ line_total (trước VAT)
    total_with_vat: int
    deposit_pct: float | None
    deposit_required: int               # deposit_pct% × total_with_vat
    deposit_received: int               # Σ amount_received
    deposit_ok: bool
    delivery_committed_date: date | None
    sale_user_id: int | None
    sale_name: str | None
    created_at: datetime
    ordered_at: datetime | None


class OrderListOut(BaseModel):
    items: list[OrderRow]
    total: int
    page: int
    size: int


class OrderStatsOut(BaseModel):
    all: int
    draft: int
    ordered: int
    cancelled: int
    pending_approval: int


class OrderDetailOut(OrderRow):
    quotation_version: int | None
    quotation_effective_from: date | None
    parent_order_id: int | None
    customer_po_no: str | None
    delivery_address: str | None
    invoice_entity_name: str | None
    invoice_entity_tax_code: str | None
    vat_pct_estimate: int
    lines: list[OrderLineOut]
    order_cost: int | None              # Σ cost_snapshot (None nếu cost_basis=none)
    margin_pct: int | None             # None ⇒ "biên không xác định" (nhập tay)
    cancel_reason: str | None
    cancel_fault: str | None
    deposits: list[OrderDepositOut] = []
    approvals: list[OrderApprovalOut] = []
    consent_attachments: list[AttachmentOut] = []
    # Cổng chốt (P4): checklist đọc-được cho FE.
    can_confirm: bool = False
    confirm_blockers: list[str] = []
    quote_expired: bool = False   # Việc 4: báo giá nguồn accepted đã hết hạn → FE bật nút "Gia hạn"


class OrderActivityItem(BaseModel):
    at: datetime
    actor_id: int | None
    actor_name: str | None
    action: str
    detail: str


class OrderActivityOut(BaseModel):
    items: list[OrderActivityItem]


class EnumOption(BaseModel):
    value: str
    label: str


class OrderEnumsOut(BaseModel):
    source_types: list[EnumOption]
    order_natures: list[EnumOption]
    statuses: list[EnumOption]
