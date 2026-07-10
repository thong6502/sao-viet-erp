"""Pydantic schemas — phiếu kho + catalog hành vi (spec-13)."""
from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field


# --- Trạng thái hàng (catalog) ----------------------------------------------
class ItemStatusIn(BaseModel):
    code: str = Field(min_length=1, max_length=24)
    name: str = Field(min_length=1, max_length=120)
    count_on_hand: bool = True
    count_available: bool = True
    allow_issue: bool = True
    display_order: int = 100
    notes: str | None = None
    is_active: bool = True


class ItemStatusRow(ItemStatusIn):
    model_config = ConfigDict(from_attributes=True)
    id: int
    is_system: bool = False


class ItemStatusListOut(BaseModel):
    items: list[ItemStatusRow]
    total: int


# --- Loại phiếu (catalog) ---------------------------------------------------
class VoucherTypeIn(BaseModel):
    code: str = Field(min_length=1, max_length=24)
    name: str = Field(min_length=1, max_length=120)
    voucher_group: str = "nhap"
    stock_effect: str = "tang"
    require_src_wh: bool = False
    require_dst_wh: bool = False
    require_approval: bool = False
    sync_misa: bool = False
    notes: str | None = None
    is_active: bool = True


class VoucherTypeRow(VoucherTypeIn):
    model_config = ConfigDict(from_attributes=True)
    id: int


class VoucherTypeListOut(BaseModel):
    items: list[VoucherTypeRow]
    total: int


# --- Phiếu (Header + Lines) -------------------------------------------------
class VoucherLineIn(BaseModel):
    material_id: int
    quantity: float = Field(gt=0)
    uom: str | None = None
    lot_id: int | None = None
    location: str | None = None
    dest_location: str | None = None
    status_id: int | None = None
    unit_cost: int | None = None
    note: str | None = None


class VoucherLineRow(VoucherLineIn):
    model_config = ConfigDict(from_attributes=True)
    id: int


class VoucherIn(BaseModel):
    voucher_type_id: int
    doc_date: date | None = None
    partner_kind: str | None = None
    partner_ref: str | None = None
    src_warehouse_id: int | None = None
    dst_warehouse_id: int | None = None
    ref_type: str | None = None
    ref_id: int | None = None
    reason: str | None = None
    note: str | None = None
    lines: list[VoucherLineIn] = Field(default_factory=list)


class VoucherRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    code: str
    voucher_type_id: int
    doc_date: date | None = None
    partner_kind: str | None = None
    partner_ref: str | None = None
    src_warehouse_id: int | None = None
    dst_warehouse_id: int | None = None
    ref_type: str | None = None
    ref_id: int | None = None
    reason: str | None = None
    note: str | None = None
    status: str
    created_by_user_id: int | None = None
    created_by_name: str | None = None  # tên người tạo/nhập (resolve ở router)
    approved_by_user_id: int | None = None
    approved_at: datetime | None = None
    misa_ref: str | None = None
    created_at: datetime
    lines: list[VoucherLineRow] = Field(default_factory=list)


class VoucherListOut(BaseModel):
    items: list[VoucherRow]
    total: int
    page: int
    size: int


# --- File đính kèm phiếu ----------------------------------------------------
class VoucherAttachmentRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    file_name: str
    file_url: str
    file_type: str | None = None
    uploaded_by: int | None = None
    uploaded_at: datetime | None = None


class VoucherAttachmentListOut(BaseModel):
    items: list[VoucherAttachmentRow]
