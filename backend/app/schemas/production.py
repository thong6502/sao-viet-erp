"""Pydantic schemas — Lệnh sản xuất (LSX), Sản xuất P1/MVP."""
from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field


class ProductionOrderIn(BaseModel):
    order_id: int | None = None
    contract_no: str | None = Field(default=None, max_length=60)
    customer_id: int | None = None
    customer_name: str | None = Field(default=None, max_length=255)
    product_id: int | None = None
    product_name: str | None = Field(default=None, max_length=255)
    quantity: float | None = None
    order_date: date | None = None
    delivery_request_date: date | None = None
    doc_date: date | None = None
    due_date: date | None = None
    # Loại lệnh: thuong / bu. Lệnh bù gắn LSX gốc + lý do bù.
    order_kind: str = "thuong"
    parent_order_id: int | None = None
    bu_reason: str | None = Field(default=None, max_length=255)
    tech_note_print: str | None = None
    tech_note_finishing: str | None = None
    note: str | None = None


class ProductionOrderRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    code: str
    order_id: int | None = None
    contract_no: str | None = None
    customer_id: int | None = None
    customer_name: str | None = None
    product_id: int | None = None
    product_name: str | None = None
    quantity: float | None = None
    order_date: date | None = None
    delivery_request_date: date | None = None
    doc_date: date | None = None
    due_date: date | None = None
    status: str
    order_kind: str = "thuong"
    parent_order_id: int | None = None
    parent_code: str | None = None  # mã LSX gốc (resolve ở router)
    bu_reason: str | None = None
    tech_note_print: str | None = None
    tech_note_finishing: str | None = None
    note: str | None = None
    created_by_user_id: int | None = None
    created_by_name: str | None = None  # resolve ở router
    updated_by_user_id: int | None = None
    updated_by_name: str | None = None  # resolve ở router
    created_at: datetime
    updated_at: datetime | None = None


class ProductionOrderListOut(BaseModel):
    items: list[ProductionOrderRow]
    total: int
    page: int
    size: int


class ProductionOrderOption(BaseModel):
    """Cho dropdown chọn LSX ở phiếu kho."""
    id: int
    code: str
    label: str  # "LSX-26-0001 · Sản phẩm A"


# --- Tập tin đính kèm LSX ---------------------------------------------------
class ProductionAttachmentRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    file_name: str
    file_url: str
    file_type: str | None = None
    uploaded_by: int | None = None
    uploaded_at: datetime | None = None


class ProductionAttachmentListOut(BaseModel):
    items: list[ProductionAttachmentRow]
