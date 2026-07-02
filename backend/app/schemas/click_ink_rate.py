"""Pydantic schemas for the Click/Ink Rate API.
"""
from __future__ import annotations

from datetime import date, datetime
from pydantic import BaseModel, ConfigDict, Field

class ClickInkRateCreate(BaseModel):
    technology: str = Field(min_length=1, max_length=32)
    color_type: str = Field(min_length=1, max_length=32)
    machine_id: int | None = None
    unit: str = Field(min_length=1, max_length=16)
    unit_price: int = Field(ge=0)
    setup_fee: int = Field(default=0, ge=0)
    min_charge: int = Field(default=0, ge=0)
    effective_from: date

class ClickInkRateClose(BaseModel):
    effective_to: date

class ClickInkRateOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    technology: str
    color_type: str
    machine_id: int | None
    unit: str
    unit_price: int
    setup_fee: int
    min_charge: int
    effective_from: date
    effective_to: date | None
    is_active: bool
    created_at: datetime
    updated_at: datetime

class ClickInkRateListOut(BaseModel):
    items: list[ClickInkRateOut]
    total: int
    page: int
    size: int
