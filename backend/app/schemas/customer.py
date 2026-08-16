"""Pydantic request/response models for the Khách hàng (CRM) API — spec-06.

Field-level constraints here are the first line of validation (400/422 shape); the
service enforces the domain rules (MST format, non-blank name, duplicate-check-soft).
"""
from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field


class _CustomerIdentity(BaseModel):
    """Thông tin ĐỊNH DANH khách (form Thêm/Sửa, redesign spec-06 v2). Không đụng chính sách
    tài chính (sửa qua endpoint /financial riêng, tránh PUT định-danh xóa nhầm hạn mức/rào)."""

    name: str = Field(min_length=1, max_length=255)
    # Loại KH: ca_nhan | cong_ty (service validate; default cong_ty).
    customer_kind: str = Field(default="cong_ty", max_length=12)
    tax_code: str | None = Field(default=None, max_length=20)
    phone: str | None = Field(default=None, max_length=30)
    email: str | None = Field(default=None, max_length=255)
    address: str | None = Field(default=None, max_length=500)
    contact_name: str | None = Field(default=None, max_length=255)
    sale_user_id: int | None = None


class CustomerCreate(_CustomerIdentity):
    """Khách MỚI = thông tin định danh; chính sách tài chính về default an toàn
    (credit_limit=0, chưa khai điều khoản, chưa đặt rào) — đặt sau qua /financial."""


class CustomerUpdate(_CustomerIdentity):
    pass


class CustomerFinancialIn(BaseModel):
    """Chính sách tài chính khách (redesign spec-06 v2) — endpoint /financial, gate
    `set_credit_terms`. Ghi ĐẦY ĐỦ nhóm này: hạn mức công nợ (tiền) + số ngày công nợ tối đa
    (net terms, kể từ ngày xuất HĐ) + rào chiết khấu/biên min–max. Lưu + hiển thị; chặn báo
    giá / cảnh báo quá hạn là SEAM."""

    credit_limit: int = Field(default=0, ge=0)
    # Số ngày công nợ tối đa kể từ ngày xuất hóa đơn. None = chưa đặt hạn ngày.
    payment_term_days: int | None = Field(default=None, ge=0)
    discount_min_pct: float | None = Field(default=None, ge=0, le=100)
    discount_max_pct: float | None = Field(default=None, ge=0, le=100)
    margin_min_pct: float | None = Field(default=None, ge=0, le=100)
    margin_max_pct: float | None = Field(default=None, ge=0, le=100)


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
    Công nợ (SEAM-16) is built — never a fabricated 0. `revenue_12m` / `orders_total` /
    `last_order_at` are DERIVED FROM REAL ORDERS, default to honest zero/None when the
    customer has no history. Redesign spec-06 v2: bỏ `tier` (tự phân loại) + `status` +
    chiết khấu mặc định cũ; thêm `customer_kind` + rào chiết khấu/biên. Chính sách tài
    chính AI CŨNG XEM (không ẩn); sửa gate `set_credit_terms` ở service."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    name: str
    customer_kind: str = "cong_ty"
    tax_code: str | None
    phone: str | None
    email: str | None = None
    address: str | None = None
    contact_name: str | None = None
    credit_limit: int
    # Số ngày công nợ tối đa (net terms, kể từ ngày xuất HĐ). None = chưa đặt hạn ngày.
    payment_term_days: int | None = None
    sale_user_id: int | None
    sale_name: str | None = None
    created_at: datetime | None = None
    # Công nợ (chỉ-đọc). None + no_ar_module → UI shows "—" / "Chưa có phân hệ Công nợ".
    receivable: int | None = None
    no_ar_module: bool = True
    # --- derived from real orders (số THẬT; bỏ tier) ---
    revenue_12m: int = 0
    orders_total: int = 0
    last_order_at: date | None = None
    # --- Rào chiết khấu / biên lợi nhuận (spec-06 v2) — hiển thị cho mọi người ---
    discount_min_pct: float | None = None
    discount_max_pct: float | None = None
    margin_min_pct: float | None = None
    margin_max_pct: float | None = None
    # --- Nhãn thủ công (#7) — sales gán tay, chips trên danh bạ ---
    tags: list[str] = []


class CustomerKpis(BaseModel):
    """The list header KPI strip — rolled up over the whole scoped book, real orders.
    Redesign spec-06 v2: bỏ tier (loyal/partner), chỉ còn số THẬT."""

    total_customers: int
    new_this_month: int
    avg_order_value: int
    total_revenue: int = 0


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


# --- Nhãn thủ công (#7: sales gán tay để phân loại chăm sóc) --------------------


class TagIn(BaseModel):
    label: str = Field(min_length=1, max_length=50)


class TagOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    label: str


class TagsOut(BaseModel):
    items: list[TagOut]


# --- Kho nhãn dùng chung (thêm / xoá nhãn — 16/08/2026) -------------------------


class KhoNhanRow(BaseModel):
    """Một nhãn trong kho + số khách đang mang nó.

    `so_khach` để màn hình hỏi có SỐ trước khi xoá ("3 khách đang mang nhãn này") thay vì một hộp
    thoại "bạn có chắc không" — đếm sẵn ở đây nên không phải gọi thêm vòng nào lúc bấm xoá."""

    id: int
    label: str
    so_khach: int = 0


class KhoNhanOut(BaseModel):
    items: list[KhoNhanRow]


class KhoNhanXoaOut(BaseModel):
    so_khach_da_go: int


# --- Ghi chú tự do (tab Ghi chú — lưu ý team về khách) --------------------------


class NoteIn(BaseModel):
    body: str = Field(min_length=1, max_length=4000)


class NoteUpdateIn(BaseModel):
    """Sửa ghi chú. Cả hai optional để PUT lo được RIÊNG LẺ: chỉ sửa nội dung, hoặc chỉ
    bật/tắt ghim. `body=None` → không đụng nội dung; `pinned=None` → không đụng ghim."""

    body: str | None = Field(default=None, max_length=4000)
    pinned: bool | None = None


class NoteOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    body: str
    pinned: bool
    created_at: datetime
    updated_at: datetime | None = None
    # `edited` = đã sửa nội dung (updated_at != None). `author_name` do router nạp.
    edited: bool = False
    author_name: str | None = None


class NotesOut(BaseModel):
    items: list[NoteOut]


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
    # Lịch lặp (redesign-lich-hen-cham-soc): none/day/week/month · mỗi N · đến ngày.
    repeat_freq: str = Field(default="none", max_length=8)
    repeat_interval: int = Field(default=1, ge=1)
    repeat_until: datetime | None = None


class CareTaskOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    note: str
    due_date: datetime
    status: str
    assignee_user_id: int | None = None
    assignee_name: str | None = None
    done_at: datetime | None = None
    repeat_freq: str = "none"
    repeat_interval: int = 1
    repeat_until: datetime | None = None
    series_id: int | None = None
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


class CareOccurrenceOut(BaseModel):
    """1 lần hẹn trên LỊCH (redesign-lich-hen-cham-soc). `task_id=None` ⇒ lần ẢO (tương lai chưa
    materialize). `series_id` = id hẹn-đầu-chuỗi để thao tác 1 lần."""

    task_id: int | None = None
    series_id: int | None = None
    note: str
    due_date: datetime
    status: str
    is_virtual: bool = False
    repeat_freq: str = "none"
    remind_level: int = 0
    overdue_days: int = 0
    assignee_user_id: int | None = None
    assignee_name: str | None = None
    is_event: bool = False        # True = tương tác ĐÃ GHI (CareEvent) hiện trên lịch
    kind: str | None = None       # hình thức khi is_event (goi_dien/nhan_tin/…)


class CareCalendarOut(BaseModel):
    items: list[CareOccurrenceOut]


class OccurrenceActionIn(BaseModel):
    """Thao tác 1 lần hẹn của chuỗi: complete | cancel | reschedule."""

    action: str
    occurrence_date: datetime | None = None   # lần nào của chuỗi (bắt buộc với hẹn lặp)
    new_due: datetime | None = None           # với reschedule
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
    """Một người trong hộp chọn "NV phụ trách" (hộp lọc, ô gán khi tạo/sửa, hộp điều chuyển).

    `co_the_gan=False` = người này KHÔNG đủ tư cách nhận khách mới (ngoài khối Kinh doanh / đã
    khoá tài khoản) nhưng vẫn đang giữ khách trong tầm nhìn ⇒ hộp LỌC hiện, ô GÁN ẩn."""

    id: int
    name: str
    # Vai trò + phòng để hộp chọn hiện 2 tầng ("Lê Sale Một" / "NV Sales · Kinh doanh") — cùng một
    # cái tên xuất hiện ở 3 chỗ, không có chức danh thì không biết ai là trưởng ai là nhân viên.
    vai_tro: str | None = None
    phong_ban: str | None = None
    co_the_gan: bool = True
    # Số khách người này đang phụ trách TRONG TẦM NHÌN của người xem (hộp Điều chuyển cần con số
    # này để biết chuyển bao nhiêu; 0 = chưa giữ khách nào).
    so_kh: int = 0


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


class PrintSpecOut(BaseModel):
    """1 dòng "Thông số in thường đặt" — đọc từ phiếu tính giá gắn báo giá của khách."""

    key: str
    label: str
    value: str
    pct: int


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
    months: list[MonthPointOut]
    product_mix: list[ProductSliceOut]
    heatmap: list[HeatCellOut]
    has_data: bool
    # Thông số in thường đặt (giấy · màu · gia công · khổ). Rỗng = khách chưa có phiếu tính giá
    # nào ⇒ frontend ẩn card, KHÔNG hiện số mẫu.
    print_specs: list[PrintSpecOut] = []
    print_specs_phieu: int = 0
    # Công nợ chỉ-đọc card reused from detail (SEAM-16 aware).
    receivable: ReceivableCard


class OrderLineBriefOut(BaseModel):
    description: str
    line_total: int


class OrderHistoryRowOut(BaseModel):
    id: int
    order_no: str
    status: str
    order_kind: str
    summary: str
    #: Từng dòng kèm TIỀN THẬT — khối "Sản phẩm mua nhiều nhất" cộng theo đây thay vì chia đều
    #: tổng đơn cho số dấu phẩy trong `summary`.
    lines: list[OrderLineBriefOut] = []
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
    "CustomerFinancialIn",
    "NoteIn",
    "NoteUpdateIn",
    "NoteOut",
    "NotesOut",
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
