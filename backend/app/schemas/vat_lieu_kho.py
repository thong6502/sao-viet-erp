"""Pydantic schemas — Vật liệu Kho (giấy/mực/bản)."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


# ---- Giấy ----
class GiayIn(BaseModel):
    ma: str = Field(min_length=1, max_length=30)
    ten: str = Field(min_length=1, max_length=150)
    kho_dai: int = Field(gt=0)
    kho_rong: int = Field(gt=0)
    gsm: int = Field(gt=0)
    caliper_micron: int | None = None
    tho: str | None = None
    don_vi_gia: str = "kg"
    don_gia: float = Field(default=0, ge=0)
    ton: float = Field(default=0, ge=0)
    active: bool = True


class GiayRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    ma: str
    ten: str
    kho_dai: int
    kho_rong: int
    gsm: int
    caliper_micron: int | None = None
    tho: str | None = None
    don_vi_gia: str
    don_gia: float
    ton: float
    active: bool
    updated_at: datetime | None = None


# ---- Mực ----
class MucIn(BaseModel):
    ma: str = Field(min_length=1, max_length=30)
    ten: str = Field(min_length=1, max_length=150)
    loai_muc: str = "process"
    ma_pantone: str | None = None
    don_gia: float = Field(default=0, ge=0)
    coverage_tiers: list | None = None
    active: bool = True


class MucRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    ma: str
    ten: str
    loai_muc: str
    ma_pantone: str | None = None
    don_gia: float
    coverage_tiers: list | None = None
    active: bool
    updated_at: datetime | None = None


# ---- Bản kẽm ----
class BanKemIn(BaseModel):
    ma: str = Field(min_length=1, max_length=30)
    ten: str = Field(min_length=1, max_length=150)
    khoa_class: str
    don_gia_kem: float = Field(default=0, ge=0)
    ton: float = Field(default=0, ge=0)
    active: bool = True


class BanKemRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    ma: str
    ten: str
    khoa_class: str
    don_gia_kem: float
    ton: float
    active: bool
    updated_at: datetime | None = None


class ListOut(BaseModel):
    items: list
    total: int
    page: int
    size: int
