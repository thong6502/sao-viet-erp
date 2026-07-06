"""Pydantic schemas for the Paper Size API — standard paper sizes master data.

Server-managed fields (version, used_count, created_by/updated_by, created_at/updated_at,
area_m2) are OUTPUT-only; the client never sets them. Loại khổ = 3 boolean; `size_type` is a
derived summary kept optional on input for backward-compat with the old single-dropdown UI.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

SizeGroup = Literal["cong_nghiep", "kho_a", "kho_cat", "custom"]


class PaperSizeCreate(BaseModel):
    # A. Thông tin chung — code optional (auto KG### khi bỏ trống)
    code: str | None = Field(default=None, max_length=20)
    name: str = Field(min_length=1, max_length=255)
    size_group: SizeGroup = "custom"
    # Loại khổ — gửi kèm hoặc bỏ trống (suy từ size_type back-compat)
    is_purchase_size: bool | None = None
    is_print_sheet_size: bool | None = None
    is_cut_size: bool | None = None
    size_type: str | None = Field(default=None, max_length=16)  # back-compat: "mua"/"in"
    note: str | None = Field(default=None, max_length=255)
    is_active: bool = True

    # B. Kích thước
    width_cm: float = Field(gt=0)
    height_cm: float = Field(gt=0)
    allow_rotation: bool = True

    # C. Áp dụng cho máy (NULL / [] = mọi máy)
    compatible_machine_ids: list[int] | None = None
    default_machine_id: int | None = None

    # D. Quan hệ khổ cắt
    parent_size_id: int | None = None
    cut_count: int | None = Field(default=None, ge=1)
    cut_waste_rate: float | None = Field(default=None, ge=0)

    # E. Ngày hiệu lực (version/used_count… do server quản)
    effective_from: date | None = None
    effective_to: date | None = None


class PaperSizeUpdate(BaseModel):
    # `code` không sửa sau khi tạo (khóa version-chain).
    name: str = Field(min_length=1, max_length=255)
    size_group: SizeGroup = "custom"
    is_purchase_size: bool | None = None
    is_print_sheet_size: bool | None = None
    is_cut_size: bool | None = None
    size_type: str | None = Field(default=None, max_length=16)
    note: str | None = Field(default=None, max_length=255)
    is_active: bool | None = Field(default=None)

    width_cm: float = Field(gt=0)
    height_cm: float = Field(gt=0)
    allow_rotation: bool = True

    compatible_machine_ids: list[int] | None = None
    default_machine_id: int | None = None

    parent_size_id: int | None = None
    cut_count: int | None = Field(default=None, ge=1)
    cut_waste_rate: float | None = Field(default=None, ge=0)

    effective_from: date | None = None
    effective_to: date | None = None


class PaperSizeRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    name: str
    size_group: str
    is_purchase_size: bool
    is_print_sheet_size: bool
    is_cut_size: bool
    size_type: str
    note: str | None = None

    width_cm: float
    height_cm: float
    area_m2: float
    allow_rotation: bool

    compatible_machine_ids: list[int] | None = None
    default_machine_id: int | None = None

    parent_size_id: int | None = None
    cut_count: int | None = None
    cut_waste_rate: float | None = None

    version: int
    effective_from: date | None = None
    effective_to: date | None = None
    used_count: int
    # "Đang dùng trong" = số phiếu tính giá (costings) tham chiếu khổ — server tính khi list.
    used_in_costings: int = 0
    created_by: int | None = None
    updated_by: int | None = None
    is_active: bool
    created_at: datetime


class PaperSizeListOut(BaseModel):
    items: list[PaperSizeRow]
    total: int
    page: int
    size: int


class PaperSizeDuplicateRef(BaseModel):
    """Khổ hiện có trùng kích thước (cả 2 chiều) — cảnh báo mềm khi tạo/sửa (§13)."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    name: str
    width_cm: float
    height_cm: float
    version: int


class PaperSizeDuplicateOut(BaseModel):
    matched: PaperSizeDuplicateRef | None = None


class PaperSizeUsageCosting(BaseModel):
    id: int
    code: str
    product_name: str | None = None
    qty_final: int
    status: str
    created_at: datetime


class PaperSizeUsageOut(BaseModel):
    paper_size_id: int
    code: str
    name: str
    costing_count: int
    costings: list[PaperSizeUsageCosting]
