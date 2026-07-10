"""Pydantic schemas for Thu mua MVP."""
from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field


class SupplierIn(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    tax_code: str = Field(min_length=1, max_length=20)
    phone: str = Field(min_length=1, max_length=30)
    email: str = Field(min_length=1, max_length=255)
    address: str = Field(min_length=1, max_length=500)
    contact_name: str = Field(min_length=1, max_length=255)
    supplier_group: str = Field(min_length=1, max_length=32)
    payment_terms: str | None = Field(default=None, max_length=255)
    status: str = Field(default="active", max_length=16)
    note: str | None = Field(default=None, max_length=2000)


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
    status: str
    note: str | None = None
    created_at: datetime
    updated_at: datetime


class SupplierListOut(BaseModel):
    items: list[SupplierRow]
    total: int
    page: int
    size: int


class PurchaseRequestLineIn(BaseModel):
    item_name: str = Field(min_length=1, max_length=255)
    unit: str = Field(min_length=1, max_length=32)
    quantity: float = Field(gt=0)
    expected_unit_price: int = Field(gt=0)
    discount_percent: float = Field(default=0, ge=0, le=100)
    vat_percent: float = Field(default=0, ge=0, le=100)
    note: str | None = Field(default=None, max_length=2000)


class DepartmentPurchaseRequestLineIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    item_name: str = Field(min_length=1, max_length=255)
    unit: str = Field(min_length=1, max_length=32)
    quantity: float = Field(gt=0)
    note: str | None = Field(default=None, max_length=2000)


class DepartmentPurchaseRequestIn(BaseModel):
    source_type: str = Field(min_length=1, max_length=32)
    related_document_type: str | None = Field(default=None, max_length=64)
    related_document_code: str | None = Field(default=None, max_length=64)
    purpose: str = Field(min_length=1, max_length=500)
    needed_date: date
    note: str | None = Field(default=None, max_length=2000)
    lines: list[DepartmentPurchaseRequestLineIn] = Field(min_length=1)


class PurchaseRequestIn(BaseModel):
    supplier_id: int = Field(gt=0)
    source_request_ids: list[int] = Field(min_length=1)
    purpose: str = Field(min_length=1, max_length=500)
    needed_date: date
    note: str | None = Field(default=None, max_length=2000)
    lines: list[PurchaseRequestLineIn] = Field(min_length=1)


class PurchaseRequestLineOut(BaseModel):
    id: int
    item_name: str
    unit: str
    quantity: float
    expected_unit_price: int
    discount_percent: float
    discount_amount: int
    vat_percent: float
    vat_amount: int
    line_total: int
    note: str | None = None


class DepartmentPurchaseRequestLineOut(BaseModel):
    id: int
    item_name: str
    unit: str
    quantity: float
    expected_unit_price: int
    line_total: int
    note: str | None = None


class DepartmentPurchaseRequestOut(BaseModel):
    id: int
    code: str
    status: str
    source_type: str
    requesting_department_id: int | None = None
    requesting_department_name: str | None = None
    requested_by_user_id: int | None = None
    requested_by_name: str | None = None
    related_document_type: str | None = None
    related_document_code: str | None = None
    purpose: str
    needed_date: date
    note: str | None = None
    created_at: datetime
    updated_at: datetime
    total_estimate: int
    lines: list[DepartmentPurchaseRequestLineOut]


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
    purpose: str | None = None
    needed_date: date | None = None
    requesting_department_name: str | None = None
    requested_by_name: str | None = None


class PurchaseRequestOut(BaseModel):
    id: int
    code: str
    status: str
    supplier_id: int | None = None
    supplier_name: str | None = None
    purpose: str | None = None
    needed_date: date | None = None
    created_by_user_id: int | None = None
    created_by_name: str | None = None
    submitted_at: datetime | None = None
    approved_by_user_id: int | None = None
    approved_by_name: str | None = None
    approved_at: datetime | None = None
    note: str | None = None
    created_at: datetime
    updated_at: datetime
    total_estimate: int
    pending_amount: int
    paid_amount: int
    outstanding_amount: int
    available_amount: int
    payment_status: str
    payment_voucher_count: int
    sources: list[PurchaseRequestSourceOut]
    lines: list[PurchaseRequestLineOut]


class PurchaseRequestListOut(BaseModel):
    items: list[PurchaseRequestOut]
    total: int
    page: int
    size: int


class ReasonIn(BaseModel):
    reason: str | None = Field(default=None, max_length=2000)
