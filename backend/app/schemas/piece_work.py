"""Pydantic models cho API Đơn giá khoán (module `luong`, nhịp 2)."""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


# --- đơn giá khoán ----------------------------------------------------------


class RateIn(BaseModel):
    group_name: str = Field(min_length=1, max_length=40)
    department_id: int | None = None
    code: str | None = Field(default=None, max_length=20)
    name: str = Field(min_length=1, max_length=255)
    cong_doan: str | None = Field(default=None, max_length=30)
    unit: str = Field(default="khac", max_length=12)
    unit_price: float = Field(ge=0)
    note: str | None = Field(default=None, max_length=255)
    is_active: bool = True


class RateOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    group_name: str
    department_id: int | None = None
    code: str | None = None
    name: str
    cong_doan: str | None = None
    unit: str
    unit_price: float
    note: str | None = None
    is_active: bool


class RatesOut(BaseModel):
    items: list[RateOut]
