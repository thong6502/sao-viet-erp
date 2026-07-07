"""Pydantic models cho API Lương khoán (module `luong`, nhịp 2)."""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


# --- đơn giá khoán ----------------------------------------------------------


class RateIn(BaseModel):
    group_name: str = Field(min_length=1, max_length=40)
    code: str | None = Field(default=None, max_length=20)
    name: str = Field(min_length=1, max_length=255)
    unit: str = Field(default="khac", max_length=12)
    unit_price: float = Field(ge=0)
    note: str | None = Field(default=None, max_length=255)
    is_active: bool = True


class RateOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    group_name: str
    code: str | None = None
    name: str
    unit: str
    unit_price: float
    note: str | None = None
    is_active: bool


class RatesOut(BaseModel):
    items: list[RateOut]


# --- sổ khoán (batch) -------------------------------------------------------


class BatchConfigIn(BaseModel):
    leader_employee_id: int | None = None
    leader_pct: float | None = Field(default=None, ge=0, le=1)
    min_guarantee: float | None = Field(default=None, ge=0)
    over_target: float | None = Field(default=None, ge=0)
    over_bonus_pct: float | None = Field(default=None, ge=0, le=5)
    note: str | None = Field(default=None, max_length=255)


class BatchOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    year: int
    month: int
    group_name: str
    leader_employee_id: int | None = None
    leader_pct: float
    min_guarantee: float
    over_target: float
    over_bonus_pct: float
    note: str | None = None


# --- dòng sản lượng ---------------------------------------------------------


class EntryIn(BaseModel):
    piece_rate_id: int | None = None
    work_name: str | None = Field(default=None, max_length=255)
    unit: str | None = Field(default=None, max_length=12)
    unit_price: float | None = Field(default=None, ge=0)
    quantity: float = Field(default=0, ge=0)
    note: str | None = Field(default=None, max_length=255)


class EntryUpdateIn(BaseModel):
    quantity: float | None = Field(default=None, ge=0)
    unit_price: float | None = Field(default=None, ge=0)
    note: str | None = Field(default=None, max_length=255)


class EntryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    batch_id: int
    piece_rate_id: int | None = None
    work_name: str
    unit: str
    unit_price: float
    quantity: float
    amount: float
    note: str | None = None


# --- chia về người ----------------------------------------------------------


class ShareIn(BaseModel):
    employee_id: int
    weight: float = Field(default=1, ge=0)
    note: str | None = Field(default=None, max_length=255)


class ShareOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    batch_id: int
    employee_id: int
    employee_name: str | None = None       # router fills
    weight: float
    amount: float
    note: str | None = None


# --- sổ khoán đầy đủ (cho FE) -----------------------------------------------


class SheetMeta(BaseModel):
    revenue: float
    total: float
    leader_cut: float
    pool: float


class SheetOut(BaseModel):
    batch: BatchOut | None = None
    entries: list[EntryOut] = []
    shares: list[ShareOut] = []
    meta: SheetMeta | None = None


class BatchesOut(BaseModel):
    items: list[BatchOut]
