"""Pydantic schemas — Danh mục Khuôn bế (khai báo nơi lưu trữ)."""
from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field


class KhuonBeIn(BaseModel):
    ma: str | None = Field(default=None, max_length=30)  # tạo mới: bỏ trống → backend tự sinh KB-####
    ten: str = Field(min_length=1, max_length=200)
    khach_hang: str | None = None
    so_ke: str | None = None
    ngay_lam_khuon: date | None = None
    tinh_trang: str = "dang_dung"
    ghi_chu: str | None = None
    active: bool = True


class KhuonBeRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    ma: str
    ten: str
    khach_hang: str | None = None
    so_ke: str | None = None
    ngay_lam_khuon: date | None = None
    tinh_trang: str
    ghi_chu: str | None = None
    active: bool
    updated_at: datetime | None = None


class KhuonBeListOut(BaseModel):
    items: list
    total: int
    page: int
    size: int
