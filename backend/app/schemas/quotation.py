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
    # Diễn giải quy cách in dưới tên sản phẩm (mỗi dòng = 1 gạch đầu dòng). FE echo giá trị cũ khi
    # không sửa — payload dump đủ field nên bỏ trống là XOÁ (cùng quy ước với `note`).
    dien_giai: str | None = None


# --- create / update ----------------------------------------------------------

class QuotationCreate(BaseModel):
    customer_id: int | None = None
    # BG-1: 1 Phiếu tính giá (PTG) → 1 báo giá. Nguồn DUY NHẤT từ Đợt 5 (đường Estimate đã gỡ).
    phieu_tinh_gia_id: int | None = None
    margin_percent: float | None = None  # gói biên áp chung khi tạo (per dòng chỉnh sau)
    valid_until: date | None = None
    # Bỏ trống → backend điền DEFAULT_TERMS (models.quotation).
    terms_text: str | None = None
    customer_note: str | None = None
    internal_note: str | None = None


class QuotationUpdate(BaseModel):
    customer_id: int | None = None
    valid_until: date | None = None
    terms_text: str | None = None         # điều khoản in ra phiếu (mỗi dòng = 1 điều khoản)
    customer_note: str | None = None
    internal_note: str | None = None
    # ĐC giao + người nhận — Sale chọn tay từ danh bạ/điểm giao của khách (redesign-bao-gia §4).
    # FE echo đủ 4 field mỗi lần lưu (cùng quy ước terms_text/customer_note): bỏ trống = xoá.
    delivery_address: str | None = None
    contact_name_snapshot: str | None = None
    contact_phone_snapshot: str | None = None
    contact_title_snapshot: str | None = None
    contact_email_snapshot: str | None = None
    items: list[QuoteItemUpdate] | None = None


class TransitionRequest(BaseModel):
    to_status: str = Field(min_length=1, max_length=20)
    cancel_reason: str | None = Field(default=None, max_length=500)
    # Khách chốt MỘT PHẦN (to_status="accepted"): id các dòng khách ƯNG. None = ưng TẤT CẢ (tương
    # thích luồng cũ / chốt nhanh). Danh sách rỗng bị chặn (phải chọn ≥1). Bỏ qua ở transition khác.
    accepted_item_ids: list[int] | None = None


class RequoteRequest(BaseModel):
    """Tạo phiên bản mới — BẮT BUỘC ghi chú/lý do (in vào Hoạt động + Lịch sử phiên bản)."""
    change_reason: str = Field(min_length=1, max_length=255)


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
    pending_approval: int = 0   # đang "Chờ duyệt" (đặc thù đã Trình duyệt)
    approved: int = 0           # "Đã duyệt" — GĐ duyệt xong, chờ sale gửi khách
    sent: int
    accepted: int
    rejected: int
    expired: int
    converted_to_order: int
    cancelled: int
    need_action: int  # draft + sent (cần tôi xử lý: soạn tiếp / chờ chốt)


class VersionRow(BaseModel):
    id: int
    version: int
    status: str
    total: int | None
    total_cost: int | None = None   # giá vốn khóa (so sánh phiên bản)
    subtotal: int | None = None     # giá bán chưa VAT
    discount: int | None = None     # chiết khấu
    created_at: datetime
    change_reason: str | None = None


class QuoteItemOut(BaseModel):
    id: int
    line_no: int
    po_code: str | None = None
    product_type: str
    product_name: str
    product_spec_text: str | None
    dien_giai: str | None = None   # diễn giải quy cách in dưới tên SP (bung từ tính giá, sửa được)
    nhom: str | None = None        # nhãn gộp dòng khi IN cho khách (ruột + bìa → 1 dòng)
    quantity: int
    unit: str                      # ĐVT thật của phần này ("cái" cho tấm bìa)
    dvt_nhom: str | None = None    # ĐVT của cụm khi bản in gộp ruột + bìa ("cuốn")
    total_cost_snapshot: float
    margin_percent: float
    selling_price: float
    unit_price: float
    discount_amount: float
    vat_percent: float
    vat_amount: float
    final_amount: float
    note: str | None
    # Khách chốt một phần: True = khách ưng (kéo lên đơn), False = không lấy. Chỉ có nghĩa khi báo
    # giá đã `accepted`; UI dùng để làm mờ/gạch dòng khách không lấy.
    accepted: bool = False


class QuotationDetailOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str  # maps to quote_number
    version: int  # maps to current version_number
    customer_id: int | None
    customer: CustomerDisplayOut | None = None
    phieu_tinh_gia_id: int | None = None
    phieu_tinh_gia_ma: str | None = None
    valid_until: date | None
    status: str
    cancel_reason: str | None
    terms_text: str | None = None         # điều khoản in ra phiếu (mỗi dòng = 1 điều khoản)
    # ĐC giao + người nhận: Sale chọn tay ở báo giá (dropdown từ danh bạ/điểm giao của khách);
    # đơn hàng KẾ THỪA nguyên các giá trị này khi chốt đơn, không sửa lại được ở Đơn hàng.
    delivery_address: str | None = None
    contact_name_snapshot: str | None = None
    contact_phone_snapshot: str | None = None
    contact_title_snapshot: str | None = None
    contact_email_snapshot: str | None = None
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
    # `markup_pct` = lợi nhuận / GIÁ VỐN (đúng ô "Markup %" Sale gõ), KHÔNG phải biên trên giá bán.
    exception_required: bool = False
    exception_status: str = "none"        # none|pending|approved|rejected|stale
    exception_cleared: bool = True
    exceptions: list[dict] = Field(default_factory=list)   # [{key,label}]
    exception_note: str | None = None
    markup_pct: int | None = None
    # Ai SOẠN (để người duyệt biết báo giá của NV nào) + ai ĐÃ DUYỆT/từ chối (để NV biết ai xử lý).
    salesperson_id: int | None = None
    salesperson_name: str | None = None
    exception_decision: str | None = None            # approved | rejected của lần quyết định gần nhất
    exception_decided_by_name: str | None = None     # tên người đã duyệt/từ chối
    exception_decided_at: datetime | None = None
    # Đơn hàng bán ĐÃ LẬP từ báo giá này (1 báo giá → 1 đơn; đơn đã hủy KHÔNG tính, nhả chỗ lập lại).
    # Có đơn → FE ẩn nút "Tạo đơn hàng", hiện "Xem đơn hàng" (liên kết sang màn Đơn hàng bán).
    order_id: int | None = None
    order_no: str | None = None


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
    markup_pct_snapshot: int | None = None   # GHIM số markup (%/giá vốn) lúc GĐ ký
    min_markup_pct: int | None = None        # sàn markup của khách đang hiệu lực lúc ký
    high_value_threshold: int | None = None
    note: str | None = None
    decided_by: int | None = None
    decided_at: datetime


class QuoteApprovalListOut(BaseModel):
    items: list[QuoteApprovalOut]


class QuoteActivityItem(BaseModel):
    """1 dòng nhật ký tương tác (feed Hoạt động) — ai làm gì, khi nào."""
    action: str
    actor_name: str | None = None
    detail: str
    at: datetime


class QuoteActivityOut(BaseModel):
    items: list[QuoteActivityItem]


class QuoteAttachmentOut(BaseModel):
    """1 tài liệu đính kèm NỘI BỘ của báo giá (file khách gửi, mẫu thiết kế, ảnh tham khảo).
    Không phân loại (doc_kind) — đính kèm tự do; không in ra bản gửi khách."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    file_name: str
    file_url: str
    file_type: str | None = None
    uploaded_at: datetime


class QuoteAttachmentsOut(BaseModel):
    items: list[QuoteAttachmentOut]


class EnumOption(BaseModel):
    value: str
    label: str


class QuotationEnumsOut(BaseModel):
    statuses: list[EnumOption]


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
    "QuoteAttachmentOut",
    "QuoteAttachmentsOut",
    "EnumOption",
    "QuotationEnumsOut",
]
