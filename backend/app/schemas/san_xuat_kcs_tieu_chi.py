"""Pydantic schemas — Danh mục Tiêu chí KCS (module KCS kiêm nhiệm, mirror `bu_hao.py`)."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class SanXuatKcsTieuChiIn(BaseModel):
    ma: str = Field(min_length=1, max_length=30)
    ten: str = Field(min_length=1, max_length=200)
    huong_dan: str | None = None
    bat_buoc: bool = True
    thu_tu: int = 0
    active: bool = True
    cong_doan_ids: list[int] = Field(default_factory=list)


class SanXuatKcsTieuChiRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    ma: str
    ten: str
    huong_dan: str | None = None
    bat_buoc: bool
    thu_tu: int
    active: bool
    cong_doan_ids: list[int] = []
    updated_at: datetime | None = None


class SanXuatKcsTieuChiListOut(BaseModel):
    items: list[SanXuatKcsTieuChiRow]
    total: int
    page: int
    size: int
