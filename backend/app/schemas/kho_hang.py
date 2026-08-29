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
    items: list[KhoHangRow]
    total: int
    page: int
    size: int


# ── Vị trí cất trong kho (bảng `kho_vi_tri`) ────────────────────────────────────────────────
class KhoViTriIn(BaseModel):
    ma: str = Field(min_length=1, max_length=60)   # tên/mã vị trí: "Kệ A - Ô 1"
    ghi_chu: str | None = Field(default=None, max_length=255)


class KhoViTriRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    kho_id: int
    ma: str
    ghi_chu: str | None = None
    active: bool


class KhoViTriListOut(BaseModel):
    items: list[KhoViTriRow]
