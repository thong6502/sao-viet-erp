"""Pydantic schemas — Danh mục Bù hao (mã + bậc số lượng ĐỘNG)."""
from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field


class BacBuHao(BaseModel):
    """1 bậc số lượng: [sl_tu, sl_den) → gia_tri (theo don_vi tờ|%). sl_den None = vô cực."""
    sl_tu: int = Field(default=0, ge=0)
    sl_den: int | None = None
    gia_tri: float = Field(default=0, ge=0)
    don_vi: str = "to"   # to | pct


class BuHaoIn(BaseModel):
    ma: str = Field(min_length=1, max_length=30)
    ten: str = Field(min_length=1, max_length=150)
    bac: list[BacBuHao] = Field(default_factory=list)
    ghi_chu: str | None = None
    active: bool = True


class BuHaoRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    ma: str
    ten: str
    bac: list | None = None
    ghi_chu: str | None = None

    active: bool
    updated_at: datetime | None = None





class BuHaoListOut(BaseModel):
    items: list
    total: int
    page: int
    size: int
