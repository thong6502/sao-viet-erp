"""Pydantic schemas for the Imposition Type API — imposition/bình bài types master data.

Full spec A–E. Server-managed fields (version, used_count, created_by/updated_by,
created_at/updated_at) are OUTPUT-only; the client never sets them.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

GroupKind = Literal["one_side", "two_side", "multi_page", "custom"]
AppliesToSides = Literal["any", "1", "2", "multi"]


class ImpositionTypeCreate(BaseModel):
    # A. Thông tin chung
    code: str = Field(min_length=1, max_length=30)  # mã ngữ nghĩa: ONE_SIDE, TU_TRO…
    name: str = Field(min_length=1, max_length=255)
    group_kind: GroupKind = "custom"
    note: str | None = Field(default=None, max_length=2000)
    is_active: bool = True

    # B. Hệ số tính chính
    sides: int = Field(default=1)
    finished_factor: float = Field(gt=0)
    pass_count: float = Field(gt=0)
    plate_set_factor: float = Field(ge=0)
    ink_pass_factor: float = Field(ge=0)
    allow_rotate: bool = True
    shared_plate_set: bool = False

    # C. Điều kiện áp dụng (NULL / [] = tất cả)
    technology: str = Field(default="offset", max_length=20)
    applies_to_sides: AppliesToSides = "any"
    applicable_product_types: list[str] | None = None
    applicable_machine_ids: list[int] | None = None
    applicable_paper_size_ids: list[int] | None = None
    allow_multi_signature: bool = True
    priority: int = Field(default=100)

    # E. Ngày hiệu lực (version/used_count… do server quản)
    effective_from: date | None = None
    effective_to: date | None = None


class ImpositionTypeUpdate(BaseModel):
    # `code` không sửa sau khi tạo (khóa version-chain + engine tra theo code).
    # force_version=True: luôn tạo phiên bản mới (kể cả khi chưa dùng trong báo giá).
    force_version: bool = False
    name: str = Field(min_length=1, max_length=255)
    group_kind: GroupKind = "custom"
    note: str | None = Field(default=None, max_length=2000)
    is_active: bool | None = Field(default=None)

    sides: int = Field(default=1)
    finished_factor: float = Field(gt=0)
    pass_count: float = Field(gt=0)
    plate_set_factor: float = Field(ge=0)
    ink_pass_factor: float = Field(ge=0)
    allow_rotate: bool = True
    shared_plate_set: bool = False

    technology: str = Field(default="offset", max_length=20)
    applies_to_sides: AppliesToSides = "any"
    applicable_product_types: list[str] | None = None
    applicable_machine_ids: list[int] | None = None
    applicable_paper_size_ids: list[int] | None = None
    allow_multi_signature: bool = True
    priority: int = Field(default=100)

    effective_from: date | None = None
    effective_to: date | None = None


class ImpositionTypeRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    name: str
    group_kind: str
    sides: int
    finished_factor: float
    pass_count: float
    plate_set_factor: float
    ink_pass_factor: float
    allow_rotate: bool
    shared_plate_set: bool
    note: str | None = None

    technology: str
    applies_to_sides: str
    applicable_product_types: list[str] | None = None
    applicable_machine_ids: list[int] | None = None
    applicable_paper_size_ids: list[int] | None = None
    allow_multi_signature: bool
    priority: int

    version: int
    effective_from: date | None = None
    effective_to: date | None = None
    used_count: int
    created_by: int | None = None
    updated_by: int | None = None
    is_active: bool
    created_at: datetime


class ImpositionTypeListOut(BaseModel):
    items: list[ImpositionTypeRow]
    total: int
    page: int
    size: int
