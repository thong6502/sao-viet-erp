"""Pydantic schemas for Thu mua MVP."""
from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field


class SupplierItemIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # Gắn về MẶT HÀNG GỐC (mg 0172). Để trống với thứ NCC bán ngoài danh mục vật tư (dịch vụ,
    # gia công) — dòng đó vẫn lưu được, chỉ không vào bảng so giá.
    hang_loai: str | None = Field(default=None, pattern="^(giay|vat_tu)$")
    hang_id: int | None = Field(default=None, gt=0)
    item_name: str = Field(min_length=1, max_length=255)
    unit: str = Field(min_length=1, max_length=32)
    unit_price: int = Field(gt=0)
    vat_percent: float = Field(default=0, ge=0, le=100)
    note: str | None = Field(default=None, max_length=2000)


class SupplierItemImportRow(BaseModel):
    """Một mặt hàng ĐỌC ĐƯỢC từ file — chưa vào DB, mới chỉ nạp vào form."""

    item_name: str
    unit: str
    unit_price: int
    vat_percent: float
    note: str | None = None


class SupplierItemImportError(BaseModel):
    #: Số dòng trong file EXCEL (đã tính cả dòng tiêu đề) — người dùng mở file là nhảy đúng chỗ.
    row: int
    message: str


class SupplierItemImportOut(BaseModel):
    """Kết quả ĐỌC file. Dòng hỏng không huỷ dòng lành: `items` và `errors` cùng có mặt."""

    items: list[SupplierItemImportRow] = Field(default_factory=list)
    errors: list[SupplierItemImportError] = Field(default_factory=list)
    total_rows: int = 0


class SupplierIn(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    tax_code: str = Field(min_length=1, max_length=20)
    phone: str = Field(min_length=1, max_length=30)
    email: str = Field(min_length=1, max_length=255)
    address: str = Field(min_length=1, max_length=500)
    contact_name: str = Field(min_length=1, max_length=255)
    supplier_group: str = Field(min_length=1, max_length=32)
    payment_terms: str | None = Field(default=None, max_length=255)
    # HẠN MỨC công nợ (VNĐ). 0 = không đặt hạn mức ⇒ không bao giờ báo vượt.
    credit_limit: int = Field(default=0, ge=0)
    # ĐỊNH MỨC = số NGÀY cho nợ kể từ ngày giao. 0 = trả ngay · None = CHƯA ĐẶT hạn (đợt giao của
    # NCC này không vào cột Quá hạn). Hai thứ khác nhau, đừng ép None thành 0.
    credit_days: int | None = Field(default=None, ge=0)
    status: str = Field(default="active", max_length=16)
    note: str | None = Field(default=None, max_length=2000)
    items: list[SupplierItemIn] = Field(default_factory=list)


class SupplierItemRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    supplier_id: int
    # Mặt hàng gốc dòng này bán. None = thứ ngoài danh mục vật tư (dịch vụ, gia công).
    hang_loai: str | None = None
    hang_id: int | None = None
    item_name: str
    unit: str
    unit_price: int
    vat_percent: float
    # Phải phơi ra: ô chọn NCC ở form phiếu mua lọc theo cờ này. Không có nó thì giao diện mời một
    # NCC đã ngưng bán mặt hàng đó, người dùng chọn xong mới bị backend từ chối — bẫy.
    is_active: bool = True
    note: str | None = None
    created_at: datetime
    updated_at: datetime


class SupplierRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    tax_code: str | None = None
    phone: str | None = None
    email: str | None = None
    address: str | None = None
    contact_name: str | None = None
    supplier_group: str | None = None
    payment_terms: str | None = None
    credit_limit: int = 0
    credit_days: int | None = None
    status: str
    note: str | None = None
    created_at: datetime
    updated_at: datetime
    items: list[SupplierItemRow] = Field(default_factory=list)

    # --- SAO ĐÁNH GIÁ: máy tự tính từ phiếu mua hàng, không ai chấm tay ------------------------
    # Luật đầy đủ ở `services/danh_gia_ncc.py`. Ở đây chỉ nhắc một điều dễ làm sai nhất:
    # ⚠️ `rating = null` nghĩa là CHƯA ĐÁNH GIÁ (chưa có đơn nào đủ điều kiện), KHÔNG phải 0 sao.
    # Giao diện phải hiện "Chưa đánh giá", đừng vẽ 0 ngôi sao — đó là vu oan cho NCC mới.
    # Thang sao thấp nhất là 1, nên 0 không bao giờ là một giá trị hợp lệ ở đây.
    rating: float | None = None
    #: Số đơn ĐƯỢC TÍNH vào trung bình (không phải tổng số đơn của NCC).
    rating_count: int = 0
    on_time_count: int = 0
    late_count: int = 0
    #: Trễ trung bình tính TRÊN CÁC ĐƠN TRỄ. `null` = chưa trễ đơn nào.
    avg_late_days: float | None = None


class SupplierListOut(BaseModel):
    items: list[SupplierRow]
    total: int
    page: int
    size: int


class SupplierItemCatalogRow(BaseModel):
    item_name: str
    unit: str
    supplier_count: int
    min_unit_price: int


class SupplierItemCatalogOut(BaseModel):
    items: list[SupplierItemCatalogRow]


# --- So giá NCC theo MẶT HÀNG GỐC (mg 0172) ----------------------------------

class SoGiaRow(BaseModel):
    """1 NCC bán mặt hàng đang xét, giá đã QUY VỀ ĐƠN VỊ GỐC để so ngang."""

    supplier_id: int
    supplier_name: str
    supplier_item_id: int
    unit: str                 # MÃ đơn vị NCC bán (ram, thung, cai…)
    unit_ten: str | None = None  # TÊN có dấu để hiển thị ("thùng", "cái"); None = trùng mã / không tra được
    unit_price: int           # giá theo đơn vị đó
    vat_percent: float
    # Giá quy về ĐƠN VỊ GỐC của mặt hàng — cột duy nhất so được giữa các NCC. None = không quy
    # đổi được (đơn vị NCC nằm ngoài tập đổi được); UI phải hiện lý do chứ đừng xếp hạng bừa.
    gia_quy_doi: int | None = None
    gia_quy_doi_vat: int | None = None
    dien_giai: str | None = None
    ly_do: str | None = None


class SoGiaOut(BaseModel):
    hang_loai: str
    hang_id: int
    hang_ma: str | None = None
    hang_ten: str | None = None
    don_vi_goc: str | None = None
    don_vi_goc_ten: str | None = None
    # Sắp xếp tăng dần theo `gia_quy_doi`; dòng không quy đổi được xếp cuối.
    items: list[SoGiaRow] = []


class PurchaseRequestLineIn(BaseModel):
    # Mặt hàng gốc (mg 0174). Client thường KHÔNG gửi — server tự kế thừa từ dòng YCMH nguồn
    # (`_chot_noi_dong`). Gửi thì thắng, vì thu mua đổi mặt hàng khi lập phiếu là hợp lệ.
    hang_loai: str | None = Field(default=None, pattern="^(giay|vat_tu)$")
    hang_id: int | None = Field(default=None, gt=0)
    item_name: str = Field(min_length=1, max_length=255)
    unit: str = Field(min_length=1, max_length=32)
    quantity: float = Field(gt=0)
    expected_unit_price: int = Field(gt=0)
    discount_percent: float = Field(default=0, ge=0, le=100)
    vat_percent: float = Field(default=0, ge=0, le=100)
    note: str | None = Field(default=None, max_length=2000)
    # Dòng YCMH đẻ ra dòng này. Không bắt buộc — thu mua vẫn được thêm dòng ngoài yêu cầu, và
    # phiếu lập trước 05/08/2026 không có. Server chốt id phải thuộc đúng yêu cầu nguồn.
    department_request_line_id: int | None = Field(default=None, gt=0)


class DepartmentPurchaseRequestLineIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # Mặt hàng gốc (mg 0174) — bảng cân đối vật tư gửi kèm khi bấm "Đề nghị mua", nhờ đó phiếu mua
    # sinh ra sau đó biết mình đang mua đúng lô giấy nào mà không phải ghép bằng tên.
    hang_loai: str | None = Field(default=None, pattern="^(giay|vat_tu)$")
    hang_id: int | None = Field(default=None, gt=0)
    item_name: str = Field(min_length=1, max_length=255)
    unit: str = Field(min_length=1, max_length=32)
    quantity: float = Field(gt=0)
    note: str | None = Field(default=None, max_length=2000)


class DepartmentPurchaseRequestIn(BaseModel):
    source_type: str | None = Field(default=None, max_length=32)
    # Ô GỘP "Nội dung / mục đích" (07/08/2026). Client cũ còn gửi `purpose` + `note`, server nối
    # lại — bắt mọi nơi gọi API đổi cùng lúc với giao diện là chuyện không xảy ra được.
    content: str | None = Field(default=None, max_length=4000)
    related_document_type: str | None = Field(default=None, max_length=64)
    related_document_code: str | None = Field(default=None, max_length=64)
    purpose: str | None = Field(default=None, max_length=500)
    needed_date: date
    note: str | None = Field(default=None, max_length=2000)
    lines: list[DepartmentPurchaseRequestLineIn] = Field(min_length=1)


class PurchaseRequestIn(BaseModel):
    supplier_id: int = Field(gt=0)
    content: str | None = Field(default=None, max_length=4000)
    source_request_ids: list[int] = Field(min_length=1)
    purpose: str | None = Field(default=None, max_length=500)
    needed_date: date
    expected_receipt_date: date | None = None
    note: str | None = Field(default=None, max_length=2000)
    lines: list[PurchaseRequestLineIn] = Field(min_length=1)


class PurchaseRequestBatchLineIn(PurchaseRequestLineIn):
    """Dòng hàng ĐÃ GÁN nhà cung cấp — dùng cho đường tạo cả mẻ.

    Một phiếu mua là thoả thuận với MỘT nhà cung cấp, nên khi yêu cầu chứa hàng của nhiều nơi thì
    phải tách thành nhiều phiếu. Gán NCC ở đây, backend nhóm lại rồi đẻ phiếu."""

    supplier_id: int = Field(gt=0)


class PurchaseRequestBatchIn(BaseModel):
    """Tạo NHIỀU phiếu mua trong MỘT lần, nhóm theo nhà cung cấp của từng dòng.

    Vì sao không để giao diện gọi API tạo phiếu nhiều lần: tạo phiếu đầu là yêu cầu nguồn bị GIỮ
    CHỖ ngay, lần gọi thứ hai cho NCC khác sẽ bị chặn. Gộp một lần cũng để hỏng thì hỏng cả mẻ,
    không để lại phiếu mồ côi."""

    source_request_ids: list[int] = Field(min_length=1)
    content: str | None = Field(default=None, max_length=4000)
    purpose: str | None = Field(default=None, max_length=500)
    needed_date: date
    expected_receipt_date: date | None = None
    note: str | None = Field(default=None, max_length=2000)
    lines: list[PurchaseRequestBatchLineIn] = Field(min_length=1)


class StatusHistoryOut(BaseModel):
    """Một lần đổi trạng thái. `source='may'` ⇒ hệ TỰ SUY, `changed_by_name` để trống."""

    id: int
    from_status: str | None = None
    to_status: str
    source: str
    changed_by_name: str | None = None
    reason: str | None = None
    created_at: datetime


class PurchaseActivityOut(BaseModel):
    """Một mốc trong lịch sử ĐƠN MUA.

    Lịch sử trạng thái chỉ trả lời đơn đã đi từ trạng thái nào sang trạng thái nào. Đợt giao là
    sự kiện nghiệp vụ riêng: giao thêm một đợt có thể vẫn giữ trạng thái ``Giao một phần`` nhưng
    người dùng vẫn cần thấy nó trong chi tiết đơn.
    """

    id: str
    event_type: str
    title: str
    detail: str | None = None
    actor_name: str | None = None
    source: str | None = None
    from_status: str | None = None
    to_status: str | None = None
    reason: str | None = None
    created_at: datetime


class PurchaseRequestLineOut(BaseModel):
    id: int
    item_name: str
    unit: str
    quantity: float
    # None = chưa khai lúc nhận hàng ⇒ hiểu là nhận đủ `quantity`.
    received_quantity: float | None = None
    expected_unit_price: int
    discount_percent: float
    discount_amount: int
    vat_percent: float
    vat_amount: int
    line_total: int
    note: str | None = None
    # Dòng YCMH đẻ ra dòng này (mg 0174b) — client cần lại để chi tiết yêu cầu hiện đúng tình
    # trạng từng sản phẩm, và để form SỬA gửi lại đúng liên kết thay vì làm rỗng nó. Phải khai ở
    # ĐÂY nữa: service trả dict + `response_model` ⇒ field không có trong schema Out bị Pydantic bỏ
    # IM LẶNG, API trả 201 mà người gọi nhận `undefined`, và test sửa đơn mua đứt-liên-kết đỏ.
    department_request_line_id: int | None = None
    # Liên kết MẶT HÀNG GỐC (mg 0174) — để Nhập kho từ đợt giao TỰ ĐIỀN vật tư thay vì bỏ trống.
    # None khi dòng mua chỉ có tên chữ (không link danh mục) → kho phải chọn tay.
    hang_loai: str | None = None
    hang_id: int | None = None
    hang_ma: str | None = None
    hang_ten: str | None = None
    # Dòng YCMH đẻ ra dòng này. Form SỬA đơn dựng lại payload từ chính bản trả về, nên thiếu nó ở
    # đây là sửa đơn một cái làm ĐỨT liên kết mặt hàng (server hết đường kế thừa lại).
    department_request_line_id: int | None = None


class LineFulfilmentOut(BaseModel):
    """Một dòng yêu cầu đã vào phiếu nào, của NCC nào, tới đâu rồi."""

    purchase_request_id: int
    purchase_code: str
    purchase_status: str
    supplier_name: str | None = None
    ordered_quantity: float
    ordered_unit: str
    # None = chưa khai lúc nhận hàng ⇒ hiểu là nhận đủ `ordered_quantity`.
    received_quantity: float | None = None


class DepartmentPurchaseRequestLineOut(BaseModel):
    id: int
    # Form sửa YCMH cần đúng cặp này để nạp lại dropdown ĐVT của chính mặt hàng đã chọn.
    # Chỉ trả tên + ĐVT sẽ làm ô ĐVT bị khóa dù bản ghi vẫn có đơn vị.
    hang_loai: str | None = None
    hang_id: int | None = None
    item_name: str
    unit: str
    quantity: float
    expected_unit_price: int
    line_total: int
    note: str | None = None
    # None = dòng chưa vào phiếu nào, HOẶC phiếu lập trước 05/08/2026 (chưa có nối dòng ↔ dòng).
    # Giao diện phải phân biệt hai ca, đừng hiện như nhau.
    fulfilment: LineFulfilmentOut | None = None
    # HUỶ TỪNG MÓN (mg 0233). `cancelled_at` khác None = món này đã bị bỏ khỏi yêu cầu; nó vẫn
    # nằm trong danh sách (gạch ngang + lý do) chứ không biến mất — biến mất là người xem tưởng
    # mình nhớ nhầm.
    cancelled_at: datetime | None = None
    cancelled_by_name: str | None = None
    cancel_reason: str | None = None
    # Luật "món này bỏ được không" tính ở máy chủ. `can_cancel=False` kèm `cancel_block_reason`
    # ⇒ giao diện vẫn BÀY nút, chỉ khoá lại và in đúng câu này (đừng ẩn nút — khoá và nói lý do).
    can_cancel: bool = False
    cancel_block_reason: str | None = None


class DepartmentRequestPurchaseOut(BaseModel):
    id: int
    code: str
    status: str
    supplier_name: str | None = None


class DepartmentPurchaseRequestOut(BaseModel):
    id: int
    code: str
    status: str
    # Trạng thái nghiệp vụ dùng để HIỂN THỊ/LỌC, suy từ các đơn mua con.
    # Không ghi đè `status`: `status` vẫn là trạng thái tổng hợp được lưu để khóa luồng.
    # Từ mg 0233 nó còn nhận giá trị `partially_cancelled` — ĐÈ lên nhãn tiến độ khi có món bị bỏ.
    workflow_status: str
    # Nhãn tiến độ THUẦN, không bị "Huỷ một phần" che. Giao diện in nó thành dòng chữ nhỏ dưới huy
    # hiệu để không mất thông tin "phần còn lại đang tới đâu".
    progress_status: str
    cancelled_line_count: int = 0
    active_line_count: int = 0
    source_type: str
    requesting_department_id: int | None = None
    requesting_department_name: str | None = None
    requested_by_user_id: int | None = None
    requested_by_name: str | None = None
    related_document_type: str | None = None
    related_document_code: str | None = None
    purpose: str
    content: str | None = None
    reject_reason: str | None = None
    status_history: list[StatusHistoryOut] = Field(default_factory=list)
    needed_date: date
    note: str | None = None
    created_at: datetime
    updated_at: datetime
    total_estimate: int
    lines: list[DepartmentPurchaseRequestLineOut]
    # Các phiếu mua sinh ra từ yêu cầu này — luôn có, kể cả khi `fulfilment` theo dòng còn rỗng.
    purchase_requests: list[DepartmentRequestPurchaseOut] = []


class DepartmentPurchaseRequestListOut(BaseModel):
    items: list[DepartmentPurchaseRequestOut]
    total: int
    page: int
    size: int


class PurchaseRequestSourceOut(BaseModel):
    id: int
    department_request_id: int
    code: str
    status: str | None = None
    source_type: str | None = None
    content: str | None = None
    purpose: str | None = None
    needed_date: date | None = None
    requesting_department_name: str | None = None
    requested_by_name: str | None = None


class PurchaseDeliveryLineOut(BaseModel):
    id: int
    purchase_request_line_id: int
    item_name: str
    unit: str
    #: SL thực nhận của đợt. Từ 28/08/2026 ĐƯỢC PHÉP vượt số đặt.
    quantity: float
    #: Phần sinh tiền của `quantity` (máy chia luỹ kế — xem `phan_bo_du_dot`).
    quantity_tinh_tien: float = 0
    #: Phần DƯ, giá 0đ. `quantity_tinh_tien + quantity_du == quantity`.
    quantity_du: float = 0
    note: str | None = None


class PurchaseDeliveryOut(BaseModel):
    id: int
    seq_no: int
    # Liên thông Kho: đợt đã sinh yêu cầu NHẬP (chưa hủy) chưa → nút "Nhập kho" đổi "Đã nhập kho".
    da_nhap_kho: bool = False
    stock_request_id: int | None = None
    stock_request_ma: str | None = None
    delivery_date: date
    due_date: date | None = None
    # True = NCC chưa khai số ngày cho nợ ⇒ đợt này không bao giờ vào cột Quá hạn. Màn hình phải
    # đẩy nó lên đầu kèm badge, không để chìm — im lặng ở đây là một món nợ không ai canh.
    chua_dat_han: bool = False
    invoice_number: str | None = None
    invoice_date: date | None = None
    note: str | None = None
    # Thành tiền của đợt — MÁY TÍNH từ số lượng × đơn giá/CK/VAT đã chốt trên phiếu, không ai gõ
    # tay (chủ chốt 07/08/2026, đảo lại quyết định 06/08).
    amount: int
    paid_amount: int = 0
    # Cọc của cả đơn chiếu xuống đợt này, và phần CÒN NỢ sau khi trừ cả hai.
    # `con_no` là TRẦN lập phiếu chi thanh toán cho đợt — form phải bám nó, KHÔNG bám công nợ cả
    # đơn (lỗi 07/08/2026: trả thừa cho đợt 2 xoá sổ luôn nợ của đợt 1).
    coc_bu: int = 0
    con_no: int = 0
    # Đợt giao đẻ ra công nợ ⇒ phải truy được ai khai, lúc nào.
    created_by_name: str | None = None
    created_at: datetime | None = None
    lines: list[PurchaseDeliveryLineOut] = Field(default_factory=list)


class PurchaseAttachmentOut(BaseModel):
    id: int
    delivery_id: int | None = None
    kind: str
    file_name: str
    file_url: str
    file_type: str | None = None
    uploaded_by_name: str | None = None
    uploaded_at: datetime


class PurchaseDeliveryLineIn(BaseModel):
    purchase_request_line_id: int
    quantity: float = Field(gt=0)
    note: str | None = Field(default=None, max_length=2000)


class PurchaseDeliveryIn(BaseModel):
    delivery_date: date
    due_date: date | None = None
    invoice_number: str | None = Field(default=None, max_length=64)
    invoice_date: date | None = None
    note: str | None = Field(default=None, max_length=2000)
    # None khi SỬA = giữ nguyên các dòng hàng, chỉ đổi phần đầu đợt (ngày, hạn, hoá đơn).
    lines: list[PurchaseDeliveryLineIn] | None = None


class PurchaseInvoiceAssignIn(BaseModel):
    """Gán MỘT hoá đơn cho NHIỀU đợt giao — ca NCC giao 3 đợt rồi mới xuất một hoá đơn chung."""

    delivery_ids: list[int] = Field(min_length=1)
    invoice_number: str | None = Field(default=None, max_length=64)
    invoice_date: date | None = None


class PurchaseContractIn(BaseModel):
    contract_number: str | None = Field(default=None, max_length=64)
    # NGÀY CHỐT CÔNG NỢ do NCC báo cho ĐƠN. Bỏ trống = chưa báo ⇒ hạn trả lùi về luật cũ
    # (ngày hoá đơn + số ngày cho nợ), không đơn nào đổi hạn ngoài ý muốn.
    debt_cutoff_date: date | None = None
    # Cọc DỰ KIẾN — chỉ để đối chiếu, KHÔNG vào công thức công nợ (cọc thật là phiếu chi).
    deposit_expected: int = Field(default=0, ge=0)


class SupplierCreditOut(BaseModel):
    #: Điều khoản thanh toán khai ở danh mục NCC — chữ tự do ("Công nợ 30 ngày", "Thanh toán ngay").
    payment_terms: str | None = None
    credit_limit: int = 0
    credit_days: int | None = None
    no_hien_tai: int = 0
    vuot_han_muc: bool = False
    vuot_bao_nhieu: int = 0


class PurchaseDepositVoucherOut(BaseModel):
    """Một phiếu ĐẶT CỌC đã lập cho phiếu mua — chỉ để form phiếu chi cảnh báo trùng."""

    code: str
    doc_no: str | None = None
    amount: int
    voucher_date: date


class PurchaseRequestOut(BaseModel):
    id: int
    code: str
    status: str
    supplier_id: int | None = None
    supplier_name: str | None = None
    purpose: str | None = None
    needed_date: date | None = None
    expected_receipt_date: date | None = None
    #: Ngày chốt công nợ NCC báo cho đơn — hạn trả MỌI đợt = ngày này + `suppliers.credit_days`.
    debt_cutoff_date: date | None = None
    #: Chụp `suppliers.credit_days` để màn hình suy hạn trả ngay tại chỗ gõ ngày chốt.
    supplier_credit_days: int | None = None
    created_by_user_id: int | None = None
    created_by_name: str | None = None
    submitted_at: datetime | None = None
    approved_by_user_id: int | None = None
    approved_by_name: str | None = None
    approved_at: datetime | None = None
    note: str | None = None
    created_at: datetime
    updated_at: datetime
    content: str | None = None
    reject_reason: str | None = None
    status_history: list[StatusHistoryOut] = Field(default_factory=list)
    # Timeline này gồm đổi trạng thái VÀ các lần ghi/sửa/xóa đợt giao.
    activity_history: list[PurchaseActivityOut] = Field(default_factory=list)
    contract_number: str | None = None
    deposit_expected: int = 0
    total_estimate: int
    # Giá trị hàng THỰC NHẬN (theo số đã khai / Σ đợt giao).
    received_total: int = 0
    # Giá trị hàng ĐÃ VỀ — số đẻ ra công nợ. Đơn chưa giao đợt nào thì = 0 dù đơn to bao nhiêu.
    gia_tri_da_giao: int = 0
    paid_amount: int
    receipt_received_amount: int = 0
    net_paid: int = 0
    # = CÔNG NỢ của phiếu, và cũng là trần lập phiếu chi THANH TOÁN.
    outstanding_amount: int
    # Trần lập phiếu ĐẶT CỌC — theo giá trị đơn đặt, vì cọc là chi khi hàng chưa về.
    tran_dat_coc: int = 0
    # Phiếu đặt cọc ĐÃ lập cho đơn này. Dùng để CẢNH BÁO khi lập phiếu cọc thứ hai — không chặn:
    # ứng thêm là ca có thật, và mỗi lần tiền rời két phải có chứng từ riêng.
    coc_da_lap: list[PurchaseDepositVoucherOut] = Field(default_factory=list)
    coc_da_chi: int = 0
    payment_status: str
    payment_voucher_count: int
    sources: list[PurchaseRequestSourceOut]
    lines: list[PurchaseRequestLineOut]
    deliveries: list[PurchaseDeliveryOut] = Field(default_factory=list)
    attachments: list[PurchaseAttachmentOut] = Field(default_factory=list)


class PurchaseRequestListOut(BaseModel):
    items: list[PurchaseRequestOut]
    total: int
    page: int
    size: int


class PurchaseNotifySummaryOut(BaseModel):
    """Badge Thu mua (sidebar `mua-hang`). FE cộng thẳng ba số — nên mọi con số người gọi KHÔNG
    được thấy phải là 0, đừng để FE tự nhớ luật che."""

    # YCMH đang *Chờ mua* — việc đang nằm trên bàn thu mua.
    ycmh_cho_lap_phieu: int = 0
    # PMH bị từ chối đang chờ Thu mua sửa và gửi lại chính phiếu đó. Dễ bị bỏ quên nhất.
    pmh_bi_tu_choi: int = 0
    # Đợt giao quá hạn trả mà còn nợ. 0 với người KHÔNG có `ke_toan:read` — không rò công nợ.
    dot_giao_qua_han: int = 0


class ReasonIn(BaseModel):
    reason: str | None = Field(default=None, max_length=2000)


class ReceivedLineIn(BaseModel):
    line_id: int
    # None = xoá khai báo, quay về "nhận đủ".
    received_quantity: float | None = Field(default=None, ge=0)


class ReceivedLinesIn(BaseModel):
    """Số thực nhận từng dòng. Bỏ trống `lines` = nhận đủ như đã đặt (đường gọi cũ vẫn chạy)."""

    lines: list[ReceivedLineIn] = Field(default_factory=list)
