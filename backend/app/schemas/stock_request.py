"""Pydantic schemas — phiếu đề nghị nhập/xuất kho."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class RequestLineIn(BaseModel):
    material_id: int
    quantity: float = Field(gt=0)
    uom: str | None = None
    note: str | None = None


class RequestLineRow(RequestLineIn):
    model_config = ConfigDict(from_attributes=True)
    id: int
    material_code: str | None = None
    material_name: str | None = None


class RequestIn(BaseModel):
    request_type: str = Field(pattern="^(nhap|xuat)$")
    voucher_type_id: int | None = None  # loại phiếu cụ thể mong muốn (đủ case NK/XK)
    warehouse_id: int
    partner_ref: str | None = None
    reason: str | None = None
    note: str | None = None
    lines: list[RequestLineIn] = Field(default_factory=list)


class RequestRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    code: str
    request_type: str
    voucher_type_id: int | None = None
    voucher_type_name: str | None = None  # resolve ở router
    warehouse_id: int
    warehouse_code: str | None = None  # resolve ở router
    warehouse_name: str | None = None
    partner_ref: str | None = None
    reason: str | None = None
    note: str | None = None
    status: str
    requested_by_user_id: int | None = None
    requested_by_name: str | None = None  # resolve ở router
    approved_by_user_id: int | None = None
    approved_by_name: str | None = None
    approved_at: datetime | None = None
    rejected_reason: str | None = None
    voucher_id: int | None = None
    voucher_code: str | None = None  # resolve ở router
    created_at: datetime
    lines: list[RequestLineRow] = Field(default_factory=list)


class RequestListOut(BaseModel):
    items: list[RequestRow]
    total: int
    page: int
    size: int


class RejectIn(BaseModel):
    reason: str = Field(default="", max_length=300)


class FulfillIn(BaseModel):
    """Lập phiếu kho từ đề nghị đã duyệt — loại phiếu (nếu bỏ trống dùng loại đã chọn ở đề nghị)."""
    voucher_type_id: int | None = None
