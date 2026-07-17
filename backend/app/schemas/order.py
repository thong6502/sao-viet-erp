"""Đơn hàng bán (Order) API schemas — redesign-don-hang-ban.md (P1 khung đơn)."""
from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field


# --- Dòng đơn ------------------------------------------------------------------
class OrderLineIn(BaseModel):
    """Dòng nhập tay (nguồn nhap_tay). Đơn từ báo giá snapshot dòng từ báo giá, không nhận ở đây."""
    description: str = ""
    qty: int = Field(default=1, ge=1)
    don_vi_tinh: str | None = Field(default=None, max_length=30)   # ĐVT (text tự do); None → "cái"
    unit_price: int | None = None       # đơn giá (VND, trước VAT) sale gõ
    vat_pct: int = Field(default=0, ge=0, le=100)


class OrderLineOut(BaseModel):
    id: int
    description: str
    qty: int
    don_vi_tinh: str = "cái"
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


# --- Phiếu thu 01-TT cho cọc (production) — dùng chung quyển sổ PT kế toán ------
class OrderReceiptIn(BaseModel):
    receipt_method: str = "bank_transfer"    # cash | bank_transfer
    amount: int = Field(default=0, ge=0)     # số thực nhận (VND)
    receipt_date: date
    content: str | None = None               # nội dung thu (mặc định "Thu cọc đơn DH###")
    bank_reference: str | None = None        # mã giao dịch / số báo có (khi CK)
    company_bank_account_id: int | None = None
    note: str | None = None
    mark_received: bool = True               # True = đã thu ngay (Kế toán ghi khi tiền đã về)


class OrderReceiptCancelIn(BaseModel):
    reason: str


class OrderReceiptOut(BaseModel):
    id: int
    code: str
    doc_no: str | None
    receipt_method: str
    amount: int
    status: str                              # waiting_receipt | received | cancelled
    receipt_date: date | None
    content: str | None
    bank_reference: str | None
    payer_name: str | None = None            # người nộp = khách (in 01-TT)
    debit_account: str | None = None         # Nợ (1111/1121) — in 01-TT
    credit_account: str | None = None        # Có (131) — in 01-TT
    created_by_name: str | None = None
    attachments: list["AttachmentOut"] = []


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
    is_rush: bool = False               # đơn gấp / ưu tiên
    # nhập tay:
    customer_id: int | None = None
    lines: list[OrderLineIn] = Field(default_factory=list)
    vat_pct_estimate: int = 0
    # thông tin đặt hàng (tùy chọn lúc tạo, sửa sau khi nháp):
    customer_po_no: str | None = None
    delivery_committed_date: date | None = None
    delivery_address: str | None = None
    delivery_contact_name: str | None = None
    delivery_contact_phone: str | None = None
    delivery_note: str | None = None
    production_note: str | None = None
    invoice_entity_name: str | None = None
    invoice_entity_tax_code: str | None = None


class OrderUpdate(BaseModel):
    """Sửa thông tin ĐẶT HÀNG. Dòng + giá + VAT BẤT BIẾN (đổi = tạo nháp mới), KHÔNG sửa qua đây.
    Field None = giữ nguyên. Nhóm HẬU CẦN (ngày giao/địa chỉ/người nhận/lưu ý/gấp) sửa được CẢ SAU
    KHI CHỐT (có log); nhóm còn lại (bản chất/%cọc) chỉ sửa khi nháp — service tự chặn."""
    order_nature: str | None = None
    is_rush: bool | None = None
    # % cọc phải thu (0–100): thỏa thuận lúc chốt đơn, KHÔNG còn ghim từ báo giá. Khóa khỏi Sale —
    # chỉ người có quyền `record_deposit` (Kế toán) đặt được, router chặn.
    deposit_pct: float | None = None
    customer_po_no: str | None = None
    delivery_committed_date: date | None = None
    delivery_address: str | None = None
    # Người nhận hàng + 2 lưu ý tách đích (giao / sản xuất). Truyền "" để xóa nội dung.
    delivery_contact_name: str | None = None
    delivery_contact_phone: str | None = None
    delivery_note: str | None = None
    production_note: str | None = None
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
    is_rush: bool = False
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
    parent_order_no: str | None = None   # mã đơn gốc (DH###) cho đơn bổ sung — hiện link ở drawer
    customer_po_no: str | None
    delivery_address: str | None
    delivery_contact_name: str | None = None
    delivery_contact_phone: str | None = None
    delivery_note: str | None = None
    production_note: str | None = None
    invoice_entity_name: str | None
    invoice_entity_tax_code: str | None
    vat_pct_estimate: int
    lines: list[OrderLineOut]
    order_cost: int | None              # Σ cost_snapshot (None nếu cost_basis=none)
    margin_pct: int | None             # None ⇒ "biên không xác định" (nhập tay)
    cancel_reason: str | None
    cancel_fault: str | None
    cancel_by_name: str | None = None    # ai hủy — cột cancel_by đã ghi ở DB, giờ mới đọc ra
    cancel_at: datetime | None = None    # khi nào hủy
    deposits: list[OrderDepositOut] = []      # legacy (order_deposits) — rỗng ở production
    receipts: list[OrderReceiptOut] = []      # phiếu thu 01-TT của đơn (nguồn cọc thật)
    approvals: list[OrderApprovalOut] = []
    consent_attachments: list[AttachmentOut] = []
    # Cổng chốt (P4): checklist đọc-được cho FE.
    can_confirm: bool = False
    confirm_blockers: list[str] = []


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
