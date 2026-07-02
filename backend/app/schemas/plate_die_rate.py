"""Pydantic schemas for the Plate/Die Rate API.
"""
from __future__ import annotations

from datetime import date, datetime
from pydantic import BaseModel, ConfigDict, Field

class PlateDieRateCreate(BaseModel):
    plate_type: str = Field(min_length=1, max_length=32)
    technology: str = Field(min_length=1, max_length=32)
    unit: str = Field(min_length=1, max_length=16)
    unit_price: int = Field(ge=0)
    setup_fee: int = Field(default=0, ge=0)
    min_charge: int = Field(default=0, ge=0)
    reusable: bool = Field(default=False)
    effective_from: date

class PlateDieRateClose(BaseModel):
    effective_to: date

class PlateDieRateOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    plate_type: str
    technology: str
    unit: str
    unit_price: int
    setup_fee: int
    min_charge: int
    reusable: bool
    effective_from: date
    effective_to: date | None
    is_active: bool
    created_at: datetime
    updated_at: datetime

class PlateDieRateListOut(BaseModel):
    items: list[PlateDieRateOut]
    total: int
    page: int
    size: int
