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

BANK_FEE_PAYER = "payer"
BANK_FEE_BENEFICIARY = "beneficiary"
BANK_FEE_SHARED = "shared"
BANK_FEE_BEARERS = (BANK_FEE_PAYER, BANK_FEE_BENEFICIARY, BANK_FEE_SHARED)


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
    purchase_request_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("purchase_requests.id", ondelete="RESTRICT"), nullable=False, index=True
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
