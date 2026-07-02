"""Pydantic request/response models for the Khách hàng (CRM) API — spec-06.

Field-level constraints here are the first line of validation (400/422 shape); the
service enforces the domain rules (MST format, non-blank name, duplicate-check-soft).
"""
from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field


class CustomerCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    tax_code: str | None = Field(default=None, max_length=20)
    phone: str | None = Field(default=None, max_length=30)
    email: str | None = Field(default=None, max_length=255)
    address: str | None = Field(default=None, max_length=500)
    contact_name: str | None = Field(default=None, max_length=255)
    # ≥ 0 enforced here AND in the service (defense in depth).
    credit_limit: int = Field(default=0, ge=0)
    sale_user_id: int | None = None


class CustomerUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    tax_code: str | None = Field(default=None, max_length=20)
    phone: str | None = Field(default=None, max_length=30)
    email: str | None = Field(default=None, max_length=255)
    address: str | None = Field(default=None, max_length=500)
    contact_name: str | None = Field(default=None, max_length=255)
    credit_limit: int = Field(default=0, ge=0)
    sale_user_id: int | None = None
    # active = đang giao dịch, inactive = ngừng giao dịch.
    status: str = Field(default="active")


class DuplicateRef(BaseModel):
    """Points at an existing customer that already carries the submitted MST (soft warn)."""

    id: int
    code: str
    name: str


class CustomerRow(BaseModel):
    """A row in the Danh bạ list. `receivable` stays None + `no_ar_module=True` until
    Công nợ (SEAM-16) is built — never a fabricated 0. The `tier` / `revenue_12m` /
    `orders_total` / `last_order_at` fields are DERIVED FROM REAL ORDERS (feat-CRM360),
    default to the honest zero/None when the customer has no history."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    name: str
    tax_code: str | None
    phone: str | None
    email: str | None = None
    address: str | None = None
    contact_name: str | None = None
    credit_limit: int
    sale_user_id: int | None
    sale_name: str | None = None
    status: str
    created_at: datetime | None = None
    # Công nợ (chỉ-đọc). None + no_ar_module → UI shows "—" / "Chưa có phân hệ Công nợ".
    receivable: int | None = None
    no_ar_module: bool = True
    # --- derived from real orders (CRM-360) ---
    tier: str = "regular"
    revenue_12m: int = 0
    orders_total: int = 0
    last_order_at: date | None = None


class CustomerKpis(BaseModel):
    """The list header KPI strip — rolled up over the whole scoped book, real orders."""

    total_customers: int
    loyal_count: int
    new_this_month: int
    avg_order_value: int


class CustomerListOut(BaseModel):
    items: list[CustomerRow]
    total: int
    page: int
    size: int
    kpis: CustomerKpis


class CustomerCreateOut(BaseModel):
    """Create response: the new customer + an optional soft duplicate-MST warning."""

    customer: CustomerRow
    duplicate: DuplicateRef | None = None


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
    """A selectable Sale (owner) for the create/edit form filters."""

    id: int
    name: str


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
    tier: str
    months: list[MonthPointOut]
    product_mix: list[ProductSliceOut]
    heatmap: list[HeatCellOut]
    has_data: bool
    # Công nợ chỉ-đọc card reused from detail (SEAM-16 aware).
    receivable: ReceivableCard


class OrderHistoryRowOut(BaseModel):
    id: int
    order_no: str
    status: str
    order_kind: str
    summary: str
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
