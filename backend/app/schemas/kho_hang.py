"""Pydantic schemas — Danh mục Kho hàng (khai báo kho)."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class KhoHangIn(BaseModel):
    ma: str | None = Field(default=None, max_length=30)  # tạo mới: bỏ trống → backend tự sinh KHO-####
    ten: str = Field(min_length=1, max_length=150)
    vi_tri: str | None = None
    ghi_chu: str | None = None
    active: bool = True


class KhoHangRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    ma: str
    ten: str
    vi_tri: str | None = None
    ghi_chu: str | None = None
    active: bool
    updated_at: datetime | None = None


class KhoHangListOut(BaseModel):
    items: list
    total: int
    page: int
    size: int
