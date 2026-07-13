"""Purchasing models — module `thu_mua`.

MVP scope: suppliers + purchase request header/lines. A user creates one purchase
request on the UI; the backend stores it as a header row plus many line rows in a
single transaction.
"""
from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import (
    BigInteger,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db import Base


SUPPLIER_ACTIVE = "active"
SUPPLIER_INACTIVE = "inactive"
SUPPLIER_STATUSES = (SUPPLIER_ACTIVE, SUPPLIER_INACTIVE)

PR_DRAFT = "draft"
PR_PENDING = "pending_approval"
PR_APPROVED = "approved"
PR_REJECTED = "rejected"
PR_PURCHASED = "purchased"
PR_RECEIVED = "received"
PR_CANCELLED = "cancelled"
PURCHASE_REQUEST_STATUSES = (
    PR_DRAFT,
    PR_PENDING,
    PR_APPROVED,
    PR_REJECTED,
    PR_PURCHASED,
    PR_RECEIVED,
    PR_CANCELLED,
)

DPR_OPEN = "open"
DPR_PENDING_APPROVAL = "pending_approval"
DPR_IN_PURCHASE = "in_purchase"
DPR_DONE = "done"
DPR_CANCELLED = "cancelled"
DEPARTMENT_PURCHASE_REQUEST_STATUSES = (
    DPR_OPEN,
    DPR_PENDING_APPROVAL,
    DPR_IN_PURCHASE,
    DPR_DONE,
    DPR_CANCELLED,
)

SOURCE_KINH_DOANH = "kinh_doanh"
SOURCE_KHO = "kho"
SOURCE_SAN_XUAT = "san_xuat"
SOURCE_CONG_NGHE = "cong_nghe"
SOURCE_GIA_CONG_NGOAI = "gia_cong_ngoai"
SOURCE_KHAC = "khac"
DEPARTMENT_PURCHASE_SOURCE_TYPES = (
    SOURCE_KINH_DOANH,
    SOURCE_KHO,
    SOURCE_SAN_XUAT,
    SOURCE_CONG_NGHE,
    SOURCE_GIA_CONG_NGOAI,
    SOURCE_KHAC,
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Supplier(Base):
    __tablename__ = "suppliers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    tax_code: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)
    phone: Mapped[str | None] = mapped_column(String(30), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    address: Mapped[str | None] = mapped_column(String(500), nullable=True)
    contact_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    supplier_group: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    payment_terms: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default=SUPPLIER_ACTIVE)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )

    bank_accounts: Mapped[list["SupplierBankAccount"]] = relationship(
        "SupplierBankAccount",
        back_populates="supplier",
        cascade="all, delete-orphan",
        order_by="SupplierBankAccount.id",
    )


class PurchaseRequest(Base):
    __tablename__ = "purchase_requests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(32), unique=True, index=True, nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default=PR_DRAFT, index=True)
    supplier_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("suppliers.id", ondelete="SET NULL"), index=True, nullable=True
    )
    purpose: Mapped[str | None] = mapped_column(String(500), nullable=True)
    needed_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    expected_receipt_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    created_by_user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), index=True, nullable=True
    )
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    approved_by_user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), index=True, nullable=True
    )
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )

    supplier: Mapped[Supplier | None] = relationship("Supplier")
    lines: Mapped[list["PurchaseRequestLine"]] = relationship(
        "PurchaseRequestLine",
        back_populates="request",
        cascade="all, delete-orphan",
        order_by="PurchaseRequestLine.id",
    )
    sources: Mapped[list["PurchaseRequestSource"]] = relationship(
        "PurchaseRequestSource",
        back_populates="purchase_request",
        cascade="all, delete-orphan",
        order_by="PurchaseRequestSource.id",
    )
    payment_vouchers: Mapped[list["PaymentVoucher"]] = relationship(
        "PaymentVoucher",
        back_populates="purchase_request",
        order_by="PaymentVoucher.id",
    )


class PurchaseRequestLine(Base):
    __tablename__ = "purchase_request_lines"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    purchase_request_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("purchase_requests.id", ondelete="CASCADE"), index=True, nullable=False
    )
    item_name: Mapped[str] = mapped_column(String(255), nullable=False)
    unit: Mapped[str] = mapped_column(String(32), nullable=False, default="cái")
    quantity: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False, default=0)
    expected_unit_price: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    discount_percent: Mapped[float] = mapped_column(Numeric(6, 2), nullable=False, default=0)
    vat_percent: Mapped[float] = mapped_column(Numeric(6, 2), nullable=False, default=0)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    request: Mapped[PurchaseRequest] = relationship("PurchaseRequest", back_populates="lines")


class DepartmentPurchaseRequest(Base):
    __tablename__ = "department_purchase_requests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(32), unique=True, index=True, nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default=DPR_OPEN, index=True)
    source_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    requesting_department_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("departments.id", ondelete="SET NULL"), index=True, nullable=True
    )
    requested_by_user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), index=True, nullable=True
    )
    related_document_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    related_document_code: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)
    purpose: Mapped[str] = mapped_column(String(500), nullable=False)
    needed_date: Mapped[date] = mapped_column(Date, nullable=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )

    requesting_department = relationship("Department")
    requested_by = relationship("User")
    lines: Mapped[list["DepartmentPurchaseRequestLine"]] = relationship(
        "DepartmentPurchaseRequestLine",
        back_populates="request",
        cascade="all, delete-orphan",
        order_by="DepartmentPurchaseRequestLine.id",
    )
    purchase_links: Mapped[list["PurchaseRequestSource"]] = relationship(
        "PurchaseRequestSource",
        back_populates="department_request",
        order_by="PurchaseRequestSource.id",
    )


class DepartmentPurchaseRequestLine(Base):
    __tablename__ = "department_purchase_request_lines"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    department_request_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("department_purchase_requests.id", ondelete="CASCADE"), index=True, nullable=False
    )
    item_name: Mapped[str] = mapped_column(String(255), nullable=False)
    unit: Mapped[str] = mapped_column(String(32), nullable=False)
    quantity: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False, default=0)
    expected_unit_price: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    request: Mapped[DepartmentPurchaseRequest] = relationship(
        "DepartmentPurchaseRequest", back_populates="lines"
    )


class PurchaseRequestSource(Base):
    __tablename__ = "purchase_request_sources"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    purchase_request_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("purchase_requests.id", ondelete="CASCADE"), index=True, nullable=False
    )
    department_request_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("department_purchase_requests.id", ondelete="RESTRICT"), index=True, nullable=False
    )
    source_code_snapshot: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)

    purchase_request: Mapped[PurchaseRequest] = relationship(
        "PurchaseRequest", back_populates="sources"
    )
    department_request: Mapped[DepartmentPurchaseRequest] = relationship(
        "DepartmentPurchaseRequest", back_populates="purchase_links"
    )
