"""Pydantic schemas for the Warehouses (cấu hình kho hàng) API."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class WarehouseCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=2000)
    notes: str | None = Field(default=None, max_length=2000)
    is_active: bool = True


class WarehouseUpdate(WarehouseCreate):
    """Same as create; code is read-only and is not sent."""


class WarehouseRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    name: str
    description: str | None = None
    notes: str | None = None
    is_active: bool
    created_at: datetime
    updated_at: datetime


class WarehouseListOut(BaseModel):
    items: list[WarehouseRow]
    total: int
    page: int
    size: int
