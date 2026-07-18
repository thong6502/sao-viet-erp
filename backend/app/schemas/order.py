"""Đơn hàng bán (Order) API schemas — redesign-don-hang-ban.md (P1 khung đơn)."""
from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field


# --- Dòng đơn ------------------------------------------------------------------
class OrderLineIn(BaseModel):
    """Dòng nhập tay (nguồn nhap_tay). Đơn từ báo giá snapshot dòng từ báo giá, không nhận ở đây."""
    description: str = ""
    qty: int = Field(default=1, ge=1)
    don_vi_tinh: str = "cái"            # ĐVT dòng (gõ tay; đơn từ báo giá kéo từ QuoteItem.unit)
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
    phieu_thanh_phan_id: int | None = None   # pin truy vết ấn phẩm (từ dòng báo giá nguồn)
    model_config = ConfigDict(from_attributes=True)


# --- Đính kèm (chung cho consent + minh chứng cọc) ---------------------------
class AttachmentOut(BaseModel):
    id: int
    url: str
    file_name: str | None
    content_type: str | None
    uploaded_at: datetime


# --- Cọc (V5) — Kế toán lập PHIẾU THU THẬT (PaymentReceipt) từ drawer đơn ------
class OrderDepositReceiptIn(BaseModel):
    """Body lập phiếu thu cọc từ đơn. `receipt_method` ∈ bộ PAYMENT_VOUCHER_TYPES của Kế toán
    (`cash` | `bank_transfer`). Kế toán bấm = đã thu → phiếu tạo thẳng status='received'."""
    receipt_method: str                      # cash | bank_transfer
    amount: int = Field(gt=0)                # tiền thực thu (VND)
    receipt_date: date | None = None         # None → hôm nay
    note: str | None = None
    company_bank_account_id: int | None = None  # chỉ dùng khi bank_transfer (cho phép NULL)


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


class OrderDepositReceiptOut(BaseModel):
    """Phiếu thu cọc (PaymentReceipt nguồn 'don_hang_ban') của đơn — FE hiện danh sách + link sang
    màn Phiếu thu Kế toán. status='received' được cộng vào cổng đủ cọc."""
    id: int
    code: str
    doc_no: str | None = None
    amount: int
    receipt_method: str
    status: str
    receipt_date: date | None = None
    created_at: datetime
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
    # graft đơn V4 (DB_SCHEMA.md): người nhận + SĐT (Sale xổ từ danh bạ KH) · lưu ý giao/SX · hàng gấp.
    delivery_contact_name: str | None = None
    delivery_contact_phone: str | None = None
    delivery_note: str | None = None
    production_note: str | None = None
    is_rush: bool = False


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
    delivery_contact_name: str | None = None
    delivery_contact_phone: str | None = None
    delivery_note: str | None = None
    production_note: str | None = None
    is_rush: bool | None = None


class OrderProductionHintIn(BaseModel):
    """Sale đổi 'hint sản xuất' (gấp / lưu ý SX) SAU khi đơn đã CHỐT — đường hẹp DUY NHẤT được sửa khi
    status=ordered (`OrderUpdate` khóa nháp). Field None = giữ nguyên; production_note="" = xoá lưu ý."""
    is_rush: bool | None = None
    production_note: str | None = None


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
    is_rush: bool = False
    total: int | None                   # Σ line_total (trước VAT)
    total_with_vat: int
    deposit_pct: float | None
    deposit_required: int               # deposit_pct% × total_with_vat
    deposit_received: int               # Σ phiếu thu cọc received (V5)
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
    # KPI tiền (aggregate read-only, không đổi schema DB): số đơn chờ cọc, Σ cần-thu-còn-thiếu,
    # Σ giá trị (gồm VAT) đơn đã chốt. Default 0 để an toàn khi thiếu.
    awaiting_deposit: int = 0
    deposit_shortfall: int = 0
    ordered_value: int = 0


class OrderDetailOut(OrderRow):
    quotation_version: int | None
    quotation_effective_from: date | None
    parent_order_id: int | None
    customer_po_no: str | None
    delivery_address: str | None
    invoice_entity_name: str | None
    invoice_entity_tax_code: str | None
    delivery_contact_name: str | None
    delivery_contact_phone: str | None
    delivery_note: str | None
    production_note: str | None
    vat_pct_estimate: int
    lines: list[OrderLineOut]
    order_cost: int | None              # Σ cost_snapshot (None nếu cost_basis=none)
    margin_pct: int | None             # None ⇒ "biên không xác định" (nhập tay)
    cancel_reason: str | None
    cancel_fault: str | None
    # V5: danh sách PHIẾU THU CỌC (PaymentReceipt nguồn đơn). Giữ tên field `deposits` để giảm thay
    # đổi FE; mỗi phần tử là OrderDepositReceiptOut.
    deposits: list[OrderDepositReceiptOut] = []
    approvals: list[OrderApprovalOut] = []
    consent_attachments: list[AttachmentOut] = []
    # Cổng chốt (P4): checklist đọc-được cho FE.
    can_confirm: bool = False
    confirm_blockers: list[str] = []
    quote_expired: bool = False   # Việc 4: báo giá nguồn accepted đã hết hạn → FE bật nút "Gia hạn"
    # Handoff Đơn→Kế hoạch: mốc Sale "Chuyển xuống sản xuất" (NULL = chưa chuyển).
    san_xuat_released_at: datetime | None = None


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
