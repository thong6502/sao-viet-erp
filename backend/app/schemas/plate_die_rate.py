"""Pydantic schemas for the Plate/Die Rate API — Đơn giá kẽm & khuôn."""
from __future__ import annotations

from datetime import date, datetime
from pydantic import BaseModel, ConfigDict, Field


class PlateDieRateBase(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    plate_type: str = Field(min_length=1, max_length=32)
    technology: str = Field(min_length=1, max_length=32)
    unit: str = Field(min_length=1, max_length=16)
    # A. Kẽm
    plate_kind: str | None = Field(default=None, max_length=16)
    plate_width_mm: int | None = Field(default=None, ge=0)
    plate_height_mm: int | None = Field(default=None, ge=0)
    machine_ids: list[int] | None = None
    paper_size_ids: list[int] | None = None
    # Đơn giá chung
    unit_price: int = Field(default=0, ge=0)
    setup_fee: int = Field(default=0, ge=0)
    min_charge: int = Field(default=0, ge=0)
    # B. Khuôn — cách tính
    pricing_method: str = Field(default="fixed", max_length=20)
    unit_price_area: int = Field(default=0, ge=0)
    unit_price_perimeter: int = Field(default=0, ge=0)
    max_charge: int | None = Field(default=None, ge=0)
    allow_manual_price: bool = False
    # Dùng lại
    reusable: bool = False
    reuse_price_method: str | None = Field(default=None, max_length=16)
    maintenance_fee: int = Field(default=0, ge=0)
    # NCC
    supplier: str | None = Field(default=None, max_length=255)
    lead_time_days: int = Field(default=0, ge=0)
    transport_fee: int = Field(default=0, ge=0)
    moq: int = Field(default=0, ge=0)
    is_active: bool = True
    effective_from: date


class PlateDieRateCreate(PlateDieRateBase):
    code: str = Field(min_length=1, max_length=40)


class PlateDieRateVersion(PlateDieRateBase):
    """Tạo version mới cho một mã đã có — code lấy từ bản gốc."""


class PlateDieRateClose(BaseModel):
    effective_to: date


class PlateDieRateOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    name: str
    plate_type: str
    technology: str
    unit: str
    plate_kind: str | None = None
    plate_width_mm: int | None = None
    plate_height_mm: int | None = None
    machine_ids: list[int] | None = None
    paper_size_ids: list[int] | None = None
    unit_price: int
    setup_fee: int
    min_charge: int
    pricing_method: str
    unit_price_area: int
    unit_price_perimeter: int
    max_charge: int | None = None
    allow_manual_price: bool
    reusable: bool
    reuse_price_method: str | None = None
    maintenance_fee: int
    supplier: str | None = None
    lead_time_days: int
    transport_fee: int
    moq: int
    effective_from: date
    effective_to: date | None
    is_active: bool
    used_count: int
    created_by: int | None = None
    updated_by: int | None = None
    created_at: datetime
    updated_at: datetime


class PlateDieRateListOut(BaseModel):
    items: list[PlateDieRateOut]
    total: int
    page: int
    size: int
