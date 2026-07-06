"""Pydantic schemas for the Kho hàng (warehouse items) operational API."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class WarehouseItemCreate(BaseModel):
    warehouse_id: int
    name: str = Field(min_length=1, max_length=255)
    quantity: float = Field(default=0, ge=0)
    unit: str = Field(default="cái", max_length=32)
    notes: str | None = Field(default=None, max_length=2000)


class WarehouseItemUpdate(WarehouseItemCreate):
    """Same fields as create."""


class WarehouseItemRow(BaseModel):
    id: int
    warehouse_id: int
    warehouse_code: str | None = None
    warehouse_name: str | None = None
    name: str
    quantity: float
    unit: str
    notes: str | None = None
    created_by_user_id: int | None = None
    created_by_name: str | None = None
    created_at: datetime
    updated_at: datetime


class WarehouseItemListOut(BaseModel):
    items: list[WarehouseItemRow]
    total: int
    page: int
    size: int


class WarehouseOption(BaseModel):
    id: int
    code: str
    name: str
