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
    pass


class SupplierBankAccountIn(BankAccountBaseIn):
    supplier_id: int = Field(gt=0)


class CompanyBankAccountOut(BankAccountBaseIn):
    model_config = ConfigDict(from_attributes=True)

    id: int
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
    voucher_type: str = Field(min_length=1, max_length=24)
    payment_stage: str = Field(min_length=1, max_length=16)
    voucher_date: date
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
    bank_fee_bearer: str | None = Field(default=None, max_length=16)
    # Định khoản in trên mẫu 02-TT — nhập tay, không bắt buộc.
    debit_account: str | None = Field(default=None, max_length=64)
    credit_account: str | None = Field(default=None, max_length=64)
    note: str | None = Field(default=None, max_length=2000)


class PaymentVoucherIn(PaymentVoucherBaseIn):
    purchase_request_id: int = Field(gt=0)


class ApproveAndCreateVoucherIn(PaymentVoucherBaseIn):
    pass


class MarkPaymentVoucherPaidIn(BaseModel):
    bank_reference: str | None = Field(default=None, max_length=64)


class CancelPaymentVoucherIn(BaseModel):
    reason: str = Field(min_length=1, max_length=2000)


class PaymentVoucherOut(BaseModel):
    id: int
    code: str
    doc_no: str | None = None
    debit_account: str | None = None
    credit_account: str | None = None
    purchase_request_id: int
    purchase_request_code: str
    purchase_request_total: int | None = None
    purchase_paid_amount: int | None = None
    purchase_created_by_name: str | None = None
    receipt_received_amount: int = 0
    receipt_pending_amount: int = 0
    attachment_count: int = 0
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
    note: str | None = Field(default=None, max_length=2000)


class MarkPaymentReceiptReceivedIn(BaseModel):
    bank_reference: str | None = Field(default=None, max_length=64)


class CancelPaymentReceiptIn(BaseModel):
    reason: str = Field(min_length=1, max_length=2000)


class PaymentReceiptOut(BaseModel):
    id: int
    code: str
    doc_no: str | None = None
    # Nguồn (V5): 'phieu_chi' (hoàn ứng NCC/NV) | 'don_hang_ban' (thu cọc khách).
    source_type: str = "phieu_chi"
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
