"""HTTP contracts for operational purchase accounting."""
from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field


class BankAccountBaseIn(BaseModel):
    account_holder: str = Field(min_length=1, max_length=255)
    account_number: str = Field(min_length=1, max_length=64)
    bank_name: str = Field(min_length=1, max_length=255)
    bank_branch: str = Field(min_length=1, max_length=255)
    currency: str = Field(default="VND", min_length=3, max_length=3)
    is_default: bool = False
    is_active: bool = True
    note: str | None = Field(default=None, max_length=2000)


class CompanyBankAccountIn(BankAccountBaseIn):
    use_for_receipts: bool = True
    use_for_payments: bool = True


class SupplierBankAccountIn(BankAccountBaseIn):
    supplier_id: int = Field(gt=0)


class CompanyBankAccountOut(BankAccountBaseIn):
    model_config = ConfigDict(from_attributes=True)

    id: int
    use_for_receipts: bool
    use_for_payments: bool
    created_at: datetime
    updated_at: datetime


class SupplierBankAccountOut(BankAccountBaseIn):
    model_config = ConfigDict(from_attributes=True)

    id: int
    supplier_id: int
    supplier_name: str | None = None
    created_at: datetime
    updated_at: datetime


class PaymentVoucherBaseIn(BaseModel):
    source_type: str | None = Field(default=None, max_length=24)
    voucher_type: str = Field(min_length=1, max_length=24)
    payment_stage: str = Field(min_length=1, max_length=16)
    # Đợt giao mà phiếu này trả cho. BẮT BUỘC với phiếu thanh toán; phải BỎ TRỐNG với phiếu đặt cọc
    # (cọc là tiền chi khi hàng chưa về nên chưa có đợt nào để gắn).
    delivery_id: int | None = Field(default=None, gt=0)
    voucher_date: date
    # DORMANT từ 06/08/2026: phiếu chi là tiền đã ra nên không có hạn trả. Hạn trả nay thuộc về
    # đợt giao (`purchase_deliveries.due_date`). Giữ khoá để client cũ không vỡ.
    planned_payment_date: date | None = None
    amount: int = Field(gt=0)
    currency: str = Field(default="VND", min_length=3, max_length=3)
    exchange_rate: float = Field(default=1, gt=0)
    content: str = Field(min_length=1, max_length=500)
    invoice_number: str | None = Field(default=None, max_length=64)
    invoice_date: date | None = None
    contract_number: str | None = Field(default=None, max_length=64)
    company_bank_account_id: int | None = Field(default=None, gt=0)
    supplier_bank_account_id: int | None = Field(default=None, gt=0)
    cash_recipient_name: str | None = Field(default=None, max_length=255)
    cash_recipient_address: str | None = Field(default=None, max_length=500)
    cash_recipient_identity: str | None = Field(default=None, max_length=64)
    beneficiary_account_holder: str | None = Field(default=None, max_length=255)
    beneficiary_account_number: str | None = Field(default=None, max_length=64)
    beneficiary_bank_name: str | None = Field(default=None, max_length=255)
    beneficiary_bank_branch: str | None = Field(default=None, max_length=255)
    bank_fee_bearer: str | None = Field(default=None, max_length=16)
    # Định khoản in trên mẫu 02-TT — nhập tay, không bắt buộc.
    debit_account: str | None = Field(default=None, max_length=64)
    credit_account: str | None = Field(default=None, max_length=64)
    note: str | None = Field(default=None, max_length=2000)


class PaymentVoucherIn(PaymentVoucherBaseIn):
    purchase_request_id: int | None = Field(default=None, gt=0)
    # Phiếu TẠM ỨNG LƯƠNG nguồn (18/08/2026). Truyền cái này thì `source_type` tự là
    # `salary_advance`, và SỐ TIỀN + NGƯỜI NHẬN lấy từ phiếu tạm ứng — payload gửi lên bị bỏ qua,
    # để phiếu chi không thể lệch số đã duyệt.
    salary_advance_id: int | None = Field(default=None, gt=0)


class ApproveAndCreateVoucherIn(PaymentVoucherBaseIn):
    pass


# ĐÃ GỠ 06/08/2026: `MarkPaymentVoucherPaidIn` — không còn bước "xác nhận đã chi" (Đ1).


class CancelPaymentVoucherIn(BaseModel):
    reason: str = Field(min_length=1, max_length=2000)


class PaymentVoucherOut(BaseModel):
    id: int
    code: str
    doc_no: str | None = None
    debit_account: str | None = None
    credit_account: str | None = None
    source_type: str = "purchase_request"
    purchase_request_id: int | None = None
    salary_advance_id: int | None = None
    purchase_request_code: str
    purchase_request_total: int | None = None
    purchase_paid_amount: int | None = None
    purchase_created_by_user_id: int | None = None
    purchase_created_by_name: str | None = None
    receipt_received_amount: int = 0
    receipt_pending_amount: int = 0
    attachment_count: int = 0
    # NULL = phiếu đặt cọc, hoặc phiếu cũ lập trước khi có khái niệm đợt giao.
    delivery_id: int | None = None
    delivery_seq_no: int | None = None
    source_request_codes: list[str]
    supplier_id: int | None = None
    supplier_name: str
    supplier_tax_code: str | None = None
    supplier_address: str | None = None
    voucher_type: str
    payment_stage: str
    status: str
    voucher_date: date
    planned_payment_date: date | None = None
    amount: int
    amount_vnd: int
    currency: str
    exchange_rate: float
    content: str
    invoice_number: str | None = None
    invoice_date: date | None = None
    contract_number: str | None = None
    company_bank_account_id: int | None = None
    supplier_bank_account_id: int | None = None
    cash_recipient_name: str | None = None
    cash_recipient_address: str | None = None
    cash_recipient_identity: str | None = None
    bank_fee_bearer: str | None = None
    bank_reference: str | None = None
    company_account_holder: str | None = None
    company_account_number: str | None = None
    company_bank_name: str | None = None
    company_bank_branch: str | None = None
    beneficiary_account_holder: str | None = None
    beneficiary_account_number: str | None = None
    beneficiary_bank_name: str | None = None
    beneficiary_bank_branch: str | None = None
    created_by_user_id: int | None = None
    created_by_name: str | None = None
    paid_by_user_id: int | None = None
    paid_by_name: str | None = None
    paid_at: datetime | None = None
    cancelled_by_user_id: int | None = None
    cancelled_by_name: str | None = None
    cancelled_at: datetime | None = None
    cancel_reason: str | None = None
    note: str | None = None
    created_at: datetime
    updated_at: datetime


class PaymentVoucherListOut(BaseModel):
    items: list[PaymentVoucherOut]
    total: int
    page: int
    size: int
    # Tổng tiền trên TOÀN BỘ kết quả khớp bộ lọc (mọi trang) — quy đổi VND.
    total_paid_amount: int = 0
    total_waiting_amount: int = 0
    total_receipt_received_amount: int = 0


class PaymentVoucherAttachmentOut(BaseModel):
    id: int
    payment_voucher_id: int
    file_name: str
    file_url: str
    file_type: str | None = None
    uploaded_by: int | None = None
    uploaded_at: datetime | None = None


class PaymentVoucherAttachmentListOut(BaseModel):
    items: list[PaymentVoucherAttachmentOut]


class PaymentReceiptIn(BaseModel):
    payer_name: str = Field(min_length=1, max_length=255)
    # Ô "Địa chỉ" của mẫu 01-TT — không bắt buộc.
    payer_address: str | None = Field(default=None, max_length=500)
    receipt_method: str = Field(min_length=1, max_length=24)
    receipt_date: date
    debit_account: str | None = Field(default=None, max_length=64)
    credit_account: str | None = Field(default=None, max_length=64)
    amount: int = Field(gt=0)
    # None → dùng tỷ giá của phiếu chi gốc.
    exchange_rate: float | None = Field(default=None, gt=0)
    content: str = Field(min_length=1, max_length=500)
    company_bank_account_id: int | None = Field(default=None, gt=0)
    bank_reference: str | None = Field(default=None, max_length=64)
    note: str | None = Field(default=None, max_length=2000)


class MarkPaymentReceiptReceivedIn(BaseModel):
    bank_reference: str | None = Field(default=None, max_length=64)


class CancelPaymentReceiptIn(BaseModel):
    reason: str = Field(min_length=1, max_length=2000)


class PaymentReceiptOut(BaseModel):
    id: int
    code: str
    doc_no: str | None = None
    # Nguồn: purchase_refund | order_deposit | sales_invoice | other.
    source_type: str = "purchase_refund"
    # Nhánh Phiếu chi — nullable từ V5 (phiếu thu cọc đơn không có phiếu chi/PMH/NCC).
    payment_voucher_id: int | None = None
    payment_voucher_code: str | None = None
    purchase_request_id: int | None = None
    purchase_request_code: str | None = None
    supplier_name: str | None = None
    # Nhánh Đơn hàng bán (V5) — None với phiếu thu nguồn Phiếu chi.
    order_id: int | None = None
    order_code: str | None = None
    customer_name: str | None = None
    sales_invoice_id: int | None = None
    sales_invoice_number: str | None = None
    payer_name: str
    payer_address: str | None = None
    debit_account: str | None = None
    credit_account: str | None = None
    receipt_method: str
    status: str
    receipt_date: date
    amount: int
    amount_vnd: int
    currency: str
    exchange_rate: float
    content: str
    company_bank_account_id: int | None = None
    company_account_holder: str | None = None
    company_account_number: str | None = None
    company_bank_name: str | None = None
    company_bank_branch: str | None = None
    bank_reference: str | None = None
    created_by_user_id: int | None = None
    created_by_name: str | None = None
    received_by_user_id: int | None = None
    received_by_name: str | None = None
    received_at: datetime | None = None
    cancelled_by_user_id: int | None = None
    cancelled_by_name: str | None = None
    cancelled_at: datetime | None = None
    cancel_reason: str | None = None
    note: str | None = None
    attachment_count: int = 0
    created_at: datetime
    updated_at: datetime


class PaymentReceiptListOut(BaseModel):
    items: list[PaymentReceiptOut]
    total: int
    page: int
    size: int


class PaymentReceiptAttachmentOut(BaseModel):
    id: int
    payment_receipt_id: int
    file_name: str
    file_url: str
    file_type: str | None = None
    uploaded_by: int | None = None
    uploaded_at: datetime | None = None


class PaymentReceiptAttachmentListOut(BaseModel):
    items: list[PaymentReceiptAttachmentOut]


# --- Hóa đơn bán ------------------------------------------------------------


class SalesInvoiceIn(BaseModel):
    order_id: int = Field(gt=0)
    invoice_symbol: str = Field(min_length=1, max_length=64)
    invoice_number: str = Field(min_length=1, max_length=64)
    invoice_date: date
    # Bỏ trống = xuất toàn bộ phần giá trị đơn chưa ghi hóa đơn.
    amount_vnd: int | None = Field(default=None, gt=0)


class CancelSalesInvoiceIn(BaseModel):
    reason: str = Field(min_length=1, max_length=2000)


class SalesInvoiceOut(BaseModel):
    id: int
    order_id: int
    order_code: str
    customer_id: int | None = None
    customer_name: str
    invoice_symbol: str | None = None
    invoice_number: str
    invoice_date: date
    amount_vnd: int
    payment_term_days_snapshot: int | None = None
    due_date: date | None = None
    status: str
    direct_received_amount: int = 0
    deposit_offset_amount: int = 0
    received_amount: int = 0
    remaining_amount: int = 0
    created_by_user_id: int | None = None
    created_by_name: str | None = None
    created_at: datetime
    cancelled_by_user_id: int | None = None
    cancelled_by_name: str | None = None
    cancelled_at: datetime | None = None
    cancel_reason: str | None = None


class SalesInvoiceListOut(BaseModel):
    order_id: int
    order_code: str
    order_total: int
    invoiced_amount: int
    uninvoiced_amount: int
    deposit_received: int
    items: list[SalesInvoiceOut]


# --- Công nợ phải trả ------------------------------------------------------
# Không có bảng công nợ: các số dưới đây SUY RA từ phiếu mua + phiếu chi lúc gọi API.


class AgingCellOut(BaseModel):
    """Một ô rổ tuổi: tiền + SỐ ĐỢT. Thiếu số đợt thì 20 triệu không phân biệt được là một đợt to
    hay mười đợt vụn — hai ca đó gọi điện đòi nợ khác hẳn nhau."""

    amount: int = 0
    count: int = 0


class AgingBucketOut(AgingCellOut):
    """Một RỔ TUỔI kèm NHÃN và biên ngày.

    Nhãn/biên do SERVER phát (`accounting_service.AGING_BUCKETS`) — giao diện in thẳng chứ không
    gõ lại "1–7". Hai nơi gõ tay là hai nơi lệch nhau ngay lần đầu đổi mốc."""

    key: str
    label: str
    # None = không có cận (dưới cho rổ "chưa tới hạn", trên cho rổ "> 60 ngày").
    min_days: int | None = None
    max_days: int | None = None


class PayableSupplierOut(BaseModel):
    supplier_id: int | None = None
    supplier_name: str
    order_count: int
    # Nợ đã QUÁ HẠN trả (theo hạn của từng đợt giao) và phần chưa tới hạn. Cộng lại = `total_due`.
    overdue_amount: int
    no_han_amount: int = 0
    # Rổ tuổi của RIÊNG NCC này (khoá → tiền + số đợt). Tổng 5 rổ trễ = `overdue_amount`, rổ
    # "chưa tới hạn" = `no_han_amount` — cùng một phép đếm, chỉ xé nhỏ ra.
    aging: dict[str, AgingCellOut] = Field(default_factory=dict)
    credit_limit: int = 0
    credit_days: int | None = None
    # Cảnh báo MỀM: chỉ gắn cờ, không chặn lập/duyệt phiếu ở đâu cả (Đ6).
    vuot_han_muc: bool = False
    vuot_bao_nhieu: int = 0
    # Tiền ĐÃ CHI trong kỳ. NCC trả hết vẫn giữ được dòng nhờ số này ⇒ "đã trả hết" là thứ NHÌN
    # THẤY, không phải suy ra từ việc không thấy gì.
    paid_in_period: int = 0
    total_due: int


class PayablesSummaryOut(BaseModel):
    items: list[PayableSupplierOut]
    total: int
    page: int
    size: int
    pages: int
    total_due: int
    overdue_amount: int
    # PHÂN TUỔI toàn màn — tính trên TOÀN BỘ NCC đang nợ, không đổi theo trang hay bộ lọc.
    # `overdue_amount` ở trên GIỮ NGUYÊN nghĩa cũ và luôn = tổng 5 rổ trễ trong này.
    aging: list[AgingBucketOut] = Field(default_factory=list)
    paid_in_period: int = 0
    vuot_han_muc_count: int = 0
    period_months: int = 3
    as_of: date


class PayableItemOut(BaseModel):
    """Một khoản CÒN NỢ — thường là một ĐỢT GIAO chưa trả hết.

    Phiếu cũ (lập trước 06/08/2026, không theo dõi theo đợt) hiện ở mức PHIẾU: `delivery_id` NULL,
    `chua_dat_han` True. Không có hạn trả nên không bao giờ vào cột Quá hạn — vì thế nó phải nổi
    lên đầu danh sách chứ không được chìm."""

    purchase_request_id: int
    code: str
    status: str
    delivery_id: int | None = None
    seq_no: int | None = None
    delivery_date: date | None = None
    due_date: date | None = None
    chua_dat_han: bool = False
    overdue_days: int = 0
    # Khoá rổ tuổi (`AGING_KEYS` ở accounting_service.py) — CHỈ có giá trị khi `overdue_days > 0`.
    # Chụp bằng đúng `ro_tuoi()` server dùng cho dải phân tuổi tổng, để một đợt KHÔNG BAO GIỜ hiện
    # hai mức khẩn khác nhau ở hai màn — đây là đúng bài học "hai chỗ nói hai kiểu tiền" đã trả giá.
    aging_bucket: str | None = None
    invoice_number: str | None = None
    invoice_date: date | None = None
    amount: int
    # Tiền trả ĐÍCH DANH đợt này (phiếu chi có `delivery_id` trỏ đúng đợt) — cột này phải khớp
    # sao kê NCC theo từng đợt.
    paid: int = 0
    # Phần CỌC của cả đơn chiếu xuống đợt này. Cố ý tách khỏi `paid`: không ai trả riêng cho đợt
    # này số đó. Nhưng `con_no` thì đã trừ CẢ HAI.
    coc_bu: int = 0
    con_no: int
    # True = đợt đã trả hết (thường do CỌC nuốt trọn, vì cọc bù giao-trước-bù-trước). Vẫn liệt kê
    # để dò được tiền cọc đi đâu, nhưng màn hình làm mờ và xếp xuống đáy đơn — nó KHÔNG phải việc
    # phải làm. Chỉ xuất hiện ở đơn còn ít nhất một đợt chưa trả hết.
    da_tat_toan: bool = False


class PayablePaidOut(BaseModel):
    """✅ Một LẦN CHI trong kỳ. Cộng lại đúng bằng cột "Đã trả"."""

    voucher_id: int
    code: str
    doc_no: str | None = None
    voucher_type: str
    payment_stage: str | None = None
    delivery_id: int | None = None
    # Số đợt (1, 2, 3…) để màn hình ghi "Đợt 2" thay vì "trả theo đợt" chung chung — cầm sao kê
    # NCC đối chiếu thì phải biết dòng nào là đợt mấy.
    delivery_seq_no: int | None = None
    purchase_request_id: int
    purchase_code: str
    amount: int
    invoice_number: str | None = None
    invoice_date: date | None = None
    has_attachment: bool = False
    paid_date: date
    # NGƯỜI LẬP phiếu chi — hỏi "ai duyệt cho tiền ra" thì phải trả lời được ngay tại dòng, không
    # bắt mở từng phiếu. Các màn Phiếu chi / Đơn mua hàng đã có cột này từ lâu; rổ "đã trả" ở màn
    # Công nợ phải trả là chỗ CUỐI CÙNG còn thiếu (chủ chốt 15/08/2026).
    created_by_user_id: int | None = None
    created_by_name: str | None = None


class PayableCocOut(BaseModel):
    """Một khoản ĐẶT CỌC / ứng trước cho cả đơn — không gắn đợt giao nào."""

    purchase_request_id: int
    code: str
    status: str
    amount: int
    # Phần cọc đã CHIẾU xuống các đợt của chính đơn này (giao trước bù trước) và phần còn dôi.
    # Không có hai số này thì màn hình chỉ nói "trừ 100.000" mà không nói trừ vào đâu.
    da_dung: int = 0
    con_du: int = 0


class PayablesDetailOut(BaseModel):
    supplier_id: int
    supplier_name: str
    credit_limit: int = 0
    credit_days: int | None = None
    vuot_han_muc: bool = False
    vuot_bao_nhieu: int = 0
    items: list[PayableItemOut]
    # CỌC / ứng trước của CẢ ĐƠN — không thuộc đợt nào nên hiện thành dòng riêng, KHÔNG nhét vào
    # cột "đã trả" của một đợt (chủ chốt 06/08/2026). Nhét vào là bảng nói dối: người đối chiếu
    # với NCC theo từng đợt sẽ không khớp được với sao kê.
    coc_chung: list[PayableCocOut] = Field(default_factory=list)
    coc_chung_amount: int = 0
    paid: list[PayablePaidOut]
    period_months: int
    # True = đã bỏ mốc kỳ, rổ "đã chi" đang hiện TOÀN BỘ lịch sử (nút "Xem lịch sử cũ hơn").
    all_history: bool = False
    total_due: int
    overdue_amount: int
    # Rổ tuổi của RIÊNG NCC này, đếm trên `items` ở trên — pill và bảng dưới nó luôn cùng một số.
    aging: list[AgingBucketOut] = Field(default_factory=list)
    paid_in_period: int
    as_of: date


# --- Công nợ phải thu ------------------------------------------------------


class ReceivableCustomerOut(BaseModel):
    customer_id: int | None = None
    customer_name: str
    invoice_count: int
    invoiced_amount: int = 0
    received_amount: int = 0
    total_due: int
    overdue_amount: int
    no_han_amount: int = 0
    credit_limit: int = 0
    payment_term_days: int | None = None
    vuot_han_muc: bool = False
    vuot_bao_nhieu: int = 0
    received_in_period: int = 0


class ReceivablesSummaryOut(BaseModel):
    items: list[ReceivableCustomerOut]
    total: int
    page: int
    size: int
    pages: int
    total_due: int
    overdue_amount: int
    received_in_period: int = 0
    vuot_han_muc_count: int = 0
    period_months: int = 3
    as_of: date


class ReceivableItemOut(BaseModel):
    invoice_id: int
    invoice_symbol: str | None = None
    invoice_number: str
    invoice_date: date
    order_id: int
    order_code: str
    customer_id: int | None = None
    customer_name: str
    due_date: date | None = None
    chua_dat_han: bool = False
    overdue_days: int = 0
    amount: int
    direct_received_amount: int = 0
    deposit_offset_amount: int = 0
    received_amount: int = 0
    remaining_amount: int


class ReceivableReceiptOut(BaseModel):
    receipt_id: int
    code: str
    doc_no: str | None = None
    order_id: int | None = None
    order_code: str | None = None
    source_type: str
    sales_invoice_id: int | None = None
    sales_invoice_number: str | None = None
    applied_to: str
    receipt_method: str
    amount: int
    receipt_date: date
    payer_name: str
    bank_reference: str | None = None
    created_by_name: str | None = None


class ReceivablesDetailOut(BaseModel):
    customer_id: int
    customer_name: str
    credit_limit: int = 0
    payment_term_days: int | None = None
    vuot_han_muc: bool = False
    vuot_bao_nhieu: int = 0
    items: list[ReceivableItemOut]
    paid: list[ReceivableReceiptOut]
    period_months: int
    all_history: bool = False
    total_due: int
    overdue_amount: int
    received_in_period: int
    as_of: date
