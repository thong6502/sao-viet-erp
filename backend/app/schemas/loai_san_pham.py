"""Pydantic schemas — Loại sản phẩm (template)."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class LoaiSanPhamIn(BaseModel):
    ma: str = Field(min_length=1, max_length=30)
    ten: str = Field(min_length=1, max_length=150)
    structural_type: str
    box_sub_type: str | None = None
    imposition_rule_id: int | None = None
    default_so_mat: int | None = None
    has_cover: bool = False
    cover_type: str | None = None
    default_binding: str | None = None
    default_stock_class: str | None = None
    routing_template: list | None = None
    vat_rate: int = 8
    ghi_chu: str | None = None
    active: bool = True


class LoaiSanPhamRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    ma: str
    ten: str
    structural_type: str
    box_sub_type: str | None = None
    imposition_rule_id: int | None = None
    default_so_mat: int | None = None
    has_cover: bool
    cover_type: str | None = None
    default_binding: str | None = None
    default_stock_class: str | None = None
    routing_template: list | None = None
    vat_rate: int
    ghi_chu: str | None = None
    active: bool
    updated_at: datetime | None = None


class LoaiSanPhamListOut(BaseModel):
    items: list[LoaiSanPhamRow]
    total: int
    page: int
    size: int
