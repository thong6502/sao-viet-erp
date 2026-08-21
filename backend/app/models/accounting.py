"""Operational accounting models for purchase payments.

The ERP keeps the business document and payment trail; legal journals and
financial statements remain in MISA per the project's hybrid-accounting scope.
"""
from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db import Base


VOUCHER_CASH = "cash"
VOUCHER_BANK_TRANSFER = "bank_transfer"
PAYMENT_VOUCHER_TYPES = (VOUCHER_CASH, VOUCHER_BANK_TRANSFER)

PAYMENT_STAGE_ADVANCE = "advance"
PAYMENT_STAGE_PARTIAL = "partial"
PAYMENT_STAGE_FINAL = "final"
PAYMENT_STAGE_OTHER = "other"
PAYMENT_STAGES = (
    PAYMENT_STAGE_ADVANCE,
    PAYMENT_STAGE_PARTIAL,
    PAYMENT_STAGE_FINAL,
    PAYMENT_STAGE_OTHER,
)

PAYMENT_VOUCHER_WAITING = "waiting_payment"
PAYMENT_VOUCHER_PAID = "paid"
PAYMENT_VOUCHER_CANCELLED = "cancelled"
PAYMENT_VOUCHER_STATUSES = (
    PAYMENT_VOUCHER_WAITING,
    PAYMENT_VOUCHER_PAID,
    PAYMENT_VOUCHER_CANCELLED,
)

VOUCHER_SOURCE_PURCHASE = "purchase_request"
VOUCHER_SOURCE_INTERNAL = "internal_expense"
VOUCHER_SOURCE_CUSTOMER_REFUND = "customer_refund"
VOUCHER_SOURCE_OTHER = "other"
# Phiếu chi lập TỪ MỘT PHIẾU TẠM ỨNG LƯƠNG đã duyệt (chủ chốt 18/08/2026). Một phiếu tạm ứng
# ⇄ một phiếu chi. Áp cho CẢ `tam_ung` lẫn `luong_dot_1` — cùng là tiền ra khỏi két.
VOUCHER_SOURCE_SALARY_ADVANCE = "salary_advance"
VOUCHER_SOURCES = (
    VOUCHER_SOURCE_SALARY_ADVANCE,
    VOUCHER_SOURCE_PURCHASE,
    VOUCHER_SOURCE_INTERNAL,
    VOUCHER_SOURCE_CUSTOMER_REFUND,
    VOUCHER_SOURCE_OTHER,
)

BANK_FEE_PAYER = "payer"
BANK_FEE_BENEFICIARY = "beneficiary"
BANK_FEE_SHARED = "shared"
BANK_FEE_BEARERS = (BANK_FEE_PAYER, BANK_FEE_BENEFICIARY, BANK_FEE_SHARED)

PAYMENT_RECEIPT_WAITING = "waiting_receipt"
PAYMENT_RECEIPT_RECEIVED = "received"
PAYMENT_RECEIPT_CANCELLED = "cancelled"
PAYMENT_RECEIPT_STATUSES = (
    PAYMENT_RECEIPT_WAITING,
    PAYMENT_RECEIPT_RECEIVED,
    PAYMENT_RECEIPT_CANCELLED,
)

# --- Nguồn phiếu thu (chung 1 quyển sổ PT, 1 dãy số 01-TT) ---------------------
# purchase_refund: tiền chi mua thừa NCC/nhân viên nộp trả (đường cũ, gắn phiếu chi).
# order_deposit:   khách đặt cọc đơn bán (đường mới, gắn đơn hàng) — không phiếu chi.
# sales_invoice:   khách thanh toán công nợ phát sinh từ hóa đơn bán đã phát hành.
RECEIPT_SOURCE_PURCHASE = "purchase_refund"
RECEIPT_SOURCE_ORDER = "order_deposit"
RECEIPT_SOURCE_SALES_INVOICE = "sales_invoice"
RECEIPT_SOURCE_OTHER = "other"
RECEIPT_SOURCES = (
    RECEIPT_SOURCE_PURCHASE,
    RECEIPT_SOURCE_ORDER,
    RECEIPT_SOURCE_SALES_INVOICE,
    RECEIPT_SOURCE_OTHER,
)

SALES_INVOICE_ISSUED = "issued"
SALES_INVOICE_CANCELLED = "cancelled"
SALES_INVOICE_STATUSES = (SALES_INVOICE_ISSUED, SALES_INVOICE_CANCELLED)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class CompanyBankAccount(Base):
    __tablename__ = "company_bank_accounts"
    __table_args__ = (
        UniqueConstraint("bank_name", "account_number", name="uq_company_bank_account"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    account_holder: Mapped[str] = mapped_column(String(255), nullable=False)
    account_number: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    bank_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    bank_branch: Mapped[str] = mapped_column(String(255), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="VND")
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    use_for_receipts: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    use_for_payments: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )


class SupplierBankAccount(Base):
    __tablename__ = "supplier_bank_accounts"
    __table_args__ = (
        UniqueConstraint(
            "supplier_id", "bank_name", "account_number", name="uq_supplier_bank_account"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    supplier_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("suppliers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    account_holder: Mapped[str] = mapped_column(String(255), nullable=False)
    account_number: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    bank_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    bank_branch: Mapped[str] = mapped_column(String(255), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="VND")
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )

    supplier = relationship("Supplier", back_populates="bank_accounts")


class PaymentVoucher(Base):
    __tablename__ = "payment_vouchers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(32), nullable=False, unique=True, index=True)
    # Số IN trên mẫu 02-TT (PC00445): thứ tự LẬP phiếu, KHÔNG phải thứ tự ngày chứng từ
    # (voucher_date sửa được sau khi đã cấp số). Phiếu hủy vẫn giữ số. Dùng chung một bộ
    # đếm cho tiền mặt lẫn UNC — cùng quyển phiếu chi.
    doc_no: Mapped[str | None] = mapped_column(String(16), nullable=True, unique=True, index=True)
    source_type: Mapped[str] = mapped_column(
        String(24), nullable=False, default=VOUCHER_SOURCE_PURCHASE, index=True
    )
    purchase_request_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("purchase_requests.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    # Phiếu này trả cho ĐỢT GIAO nào (chủ chốt 06/08/2026).
    #   NULL  = phiếu ĐẶT CỌC / ứng trước — chi khi hàng chưa về nên chưa có đợt nào để gắn.
    #   có id = phiếu THANH TOÁN cho đúng một đợt giao.
    # Soft ref (không FK) có chủ ý: xoá đợt giao đã bị chặn ở tầng service khi đợt còn phiếu chi,
    # nên FK RESTRICT chỉ thêm một chỗ vỡ ở DB mà không thêm an toàn nào.
    delivery_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    # Phiếu TẠM ỨNG LƯƠNG nguồn (chủ chốt 18/08/2026). Chỉ có giá trị khi
    # `source_type = salary_advance`. RESTRICT: còn phiếu chi thì không xoá được phiếu tạm ứng.
    # Một phiếu tạm ứng chỉ được lập ĐÚNG MỘT phiếu chi ⇒ UNIQUE.
    salary_advance_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("salary_advances.id", ondelete="RESTRICT"),
        nullable=True, unique=True, index=True,
    )
    supplier_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("suppliers.id", ondelete="SET NULL"), nullable=True, index=True
    )
    voucher_type: Mapped[str] = mapped_column(String(24), nullable=False, index=True)
    payment_stage: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(
        String(24), nullable=False, default=PAYMENT_VOUCHER_WAITING, index=True
    )
    voucher_date: Mapped[date] = mapped_column(Date, nullable=False)
    planned_payment_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    amount: Mapped[int] = mapped_column(BigInteger, nullable=False)
    amount_vnd: Mapped[int] = mapped_column(BigInteger, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="VND")
    exchange_rate: Mapped[float] = mapped_column(Numeric(18, 6), nullable=False, default=1)
    content: Mapped[str] = mapped_column(String(500), nullable=False)
    invoice_number: Mapped[str | None] = mapped_column(String(64), nullable=True)
    invoice_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    contract_number: Mapped[str | None] = mapped_column(String(64), nullable=True)
    company_bank_account_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("company_bank_accounts.id", ondelete="SET NULL"), nullable=True, index=True
    )
    supplier_bank_account_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("supplier_bank_accounts.id", ondelete="SET NULL"), nullable=True, index=True
    )
    cash_recipient_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    cash_recipient_address: Mapped[str | None] = mapped_column(String(500), nullable=True)
    cash_recipient_identity: Mapped[str | None] = mapped_column(String(64), nullable=True)
    bank_fee_bearer: Mapped[str | None] = mapped_column(String(16), nullable=True)
    bank_reference: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # Định khoản in trên mẫu ("Nợ: 242, 1331" / "Có: 1111") — nhập tay, hệ thống chưa
    # có danh mục tài khoản kế toán.
    debit_account: Mapped[str | None] = mapped_column(String(64), nullable=True)
    credit_account: Mapped[str | None] = mapped_column(String(64), nullable=True)

    source_code_snapshot: Mapped[str] = mapped_column(String(32), nullable=False)
    supplier_name_snapshot: Mapped[str] = mapped_column(String(255), nullable=False)
    supplier_tax_code_snapshot: Mapped[str | None] = mapped_column(String(20), nullable=True)
    supplier_address_snapshot: Mapped[str | None] = mapped_column(String(500), nullable=True)
    company_account_holder_snapshot: Mapped[str | None] = mapped_column(String(255), nullable=True)
    company_account_number_snapshot: Mapped[str | None] = mapped_column(String(64), nullable=True)
    company_bank_name_snapshot: Mapped[str | None] = mapped_column(String(255), nullable=True)
    company_bank_branch_snapshot: Mapped[str | None] = mapped_column(String(255), nullable=True)
    beneficiary_account_holder_snapshot: Mapped[str | None] = mapped_column(String(255), nullable=True)
    beneficiary_account_number_snapshot: Mapped[str | None] = mapped_column(String(64), nullable=True)
    beneficiary_bank_name_snapshot: Mapped[str | None] = mapped_column(String(255), nullable=True)
    beneficiary_bank_branch_snapshot: Mapped[str | None] = mapped_column(String(255), nullable=True)

    created_by_user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    paid_by_user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelled_by_user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancel_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )

    purchase_request = relationship("PurchaseRequest", back_populates="payment_vouchers")
    supplier = relationship("Supplier")
    company_bank_account = relationship("CompanyBankAccount")
    supplier_bank_account = relationship("SupplierBankAccount")
    receipts: Mapped[list["PaymentReceipt"]] = relationship(
        "PaymentReceipt", back_populates="payment_voucher", order_by="PaymentReceipt.id"
    )
    attachments: Mapped[list["PaymentVoucherAttachment"]] = relationship(
        "PaymentVoucherAttachment",
        back_populates="payment_voucher",
        order_by="PaymentVoucherAttachment.id",
        cascade="all, delete-orphan",
    )


class SalesInvoice(Base):
    """Hóa đơn bán đã phát hành — mốc làm phát sinh công nợ phải thu."""

    __tablename__ = "sales_invoices"
    __table_args__ = (
        UniqueConstraint(
            "invoice_symbol", "invoice_number", name="uq_sales_invoice_symbol_number"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    order_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("orders.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    customer_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("customers.id", ondelete="SET NULL"), nullable=True, index=True
    )
    invoice_symbol: Mapped[str] = mapped_column(String(64), nullable=False)
    invoice_number: Mapped[str] = mapped_column(String(64), nullable=False)
    invoice_date: Mapped[date] = mapped_column(Date, nullable=False)
    amount_vnd: Mapped[int] = mapped_column(BigInteger, nullable=False)
    payment_term_days_snapshot: Mapped[int | None] = mapped_column(Integer, nullable=True)
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    customer_name_snapshot: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default=SALES_INVOICE_ISSUED, index=True
    )
    created_by_user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )
    cancelled_by_user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancel_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    order = relationship("Order")
    customer = relationship("Customer")
    receipts: Mapped[list["PaymentReceipt"]] = relationship(
        "PaymentReceipt", back_populates="sales_invoice", order_by="PaymentReceipt.id"
    )


class PaymentReceipt(Base):
    """Phiếu thu đa nguồn: hoàn tiền chi mua, cọc đơn bán, thu hóa đơn hoặc thu khác.

    `source_type` quyết định khóa nguồn nào được dùng; riêng nhánh công nợ liên kết
    trực tiếp tới `SalesInvoice` để số tiền thu được truy về đúng hóa đơn phát sinh.
    """

    __tablename__ = "payment_receipts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(32), nullable=False, unique=True, index=True)
    # Số IN trên mẫu 01-TT (PT00027) — xem ghi chú doc_no ở PaymentVoucher.
    doc_no: Mapped[str | None] = mapped_column(String(16), nullable=True, unique=True, index=True)
    # Nguồn phiếu ∈ {purchase_refund, order_deposit, sales_invoice, other}.
    source_type: Mapped[str] = mapped_column(
        String(20), nullable=False, default=RECEIPT_SOURCE_PURCHASE, index=True
    )
    # Đường phiếu chi (purchase_refund) — nullable để đường đơn bán không cần.
    payment_voucher_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("payment_vouchers.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    # Denormalize từ phiếu chi gốc để SUM theo PMH không phải join.
    purchase_request_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("purchase_requests.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    # Đường đơn bán (order_deposit) — cọc khách nộp cho một đơn hàng.
    order_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("orders.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    sales_invoice_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("sales_invoices.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    order_no_snapshot: Mapped[str | None] = mapped_column(String(32), nullable=True)
    customer_name_snapshot: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Người nộp lại tiền — mặc định suy từ phiếu chi (người phụ trách mua / người nhận TM).
    payer_name: Mapped[str] = mapped_column(String(255), nullable=False)
    payer_address: Mapped[str | None] = mapped_column(String(500), nullable=True)
    receipt_method: Mapped[str] = mapped_column(String(24), nullable=False)
    status: Mapped[str] = mapped_column(
        String(24), nullable=False, default=PAYMENT_RECEIPT_WAITING, index=True
    )
    receipt_date: Mapped[date] = mapped_column(Date, nullable=False)
    amount: Mapped[int] = mapped_column(BigInteger, nullable=False)
    amount_vnd: Mapped[int] = mapped_column(BigInteger, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="VND")
    exchange_rate: Mapped[float] = mapped_column(Numeric(18, 6), nullable=False, default=1)
    content: Mapped[str] = mapped_column(String(500), nullable=False)
    company_bank_account_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("company_bank_accounts.id", ondelete="SET NULL"), nullable=True, index=True
    )
    bank_reference: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # Định khoản in trên mẫu ("Nợ: 1111" / "Có: 131") — nhập tay.
    debit_account: Mapped[str | None] = mapped_column(String(64), nullable=True)
    credit_account: Mapped[str | None] = mapped_column(String(64), nullable=True)

    # Snapshot đường phiếu chi (purchase_refund) — nullable vì đường đơn bán không có.
    voucher_code_snapshot: Mapped[str | None] = mapped_column(String(32), nullable=True)
    purchase_code_snapshot: Mapped[str | None] = mapped_column(String(32), nullable=True)
    supplier_name_snapshot: Mapped[str | None] = mapped_column(String(255), nullable=True)
    company_account_holder_snapshot: Mapped[str | None] = mapped_column(String(255), nullable=True)
    company_account_number_snapshot: Mapped[str | None] = mapped_column(String(64), nullable=True)
    company_bank_name_snapshot: Mapped[str | None] = mapped_column(String(255), nullable=True)
    company_bank_branch_snapshot: Mapped[str | None] = mapped_column(String(255), nullable=True)

    created_by_user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    received_by_user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    received_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelled_by_user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancel_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )

    payment_voucher = relationship("PaymentVoucher", back_populates="receipts")
    sales_invoice = relationship("SalesInvoice", back_populates="receipts")
    company_bank_account = relationship("CompanyBankAccount")
    attachments: Mapped[list["PaymentReceiptAttachment"]] = relationship(
        "PaymentReceiptAttachment",
        back_populates="payment_receipt",
        order_by="PaymentReceiptAttachment.id",
        cascade="all, delete-orphan",
    )


class PaymentVoucherAttachment(Base):
    """Chứng từ scan đính kèm Phiếu chi/UNC (hóa đơn/biên nhận/UNC ngân hàng).
    Bytes nằm trong kho file `ke-toan/<voucher_id>/` (app/storage.py), đọc lại qua
    /api/files — cần đăng nhập + quyền `ke_toan`; DB chỉ lưu metadata + path. Cho
    đính THÊM cả khi phiếu đã `paid` (hóa đơn về sau khi đi mua); chỉ chặn `cancelled`."""

    __tablename__ = "payment_voucher_attachments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    payment_voucher_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("payment_vouchers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    file_url: Mapped[str] = mapped_column(String(500), nullable=False)
    file_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    uploaded_by: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )

    payment_voucher = relationship("PaymentVoucher", back_populates="attachments")


class PaymentReceiptAttachment(Base):
    """Ảnh minh chứng đã thu đính kèm Phiếu thu (biên nhận/UNC báo có).
    Bytes nằm trong kho file `ke-toan-thu/<receipt_id>/`, đọc lại qua /api/files (cần
    quyền `ke_toan`); DB chỉ lưu metadata + path (mirror payment_voucher_attachments).
    Cho đính THÊM cả khi đã `received`; chỉ chặn `cancelled`."""

    __tablename__ = "payment_receipt_attachments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    payment_receipt_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("payment_receipts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    file_url: Mapped[str] = mapped_column(String(500), nullable=False)
    file_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    uploaded_by: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )

    payment_receipt = relationship("PaymentReceipt", back_populates="attachments")
