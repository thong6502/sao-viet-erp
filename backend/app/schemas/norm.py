"""Pydantic schemas for the Norms/Losses API.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any
from pydantic import BaseModel, ConfigDict, Field

class NormCreate(BaseModel):
    norm_key: str = Field(min_length=1, max_length=32)
    value: float = Field(ge=0)
    product_type: str | None = Field(default=None, max_length=32)
    machine_id: int | None = None
    operation_id: int | None = None
    operation_key: str | None = Field(default=None, max_length=32)
    qty_min: int | None = Field(default=None, ge=0)
    qty_max: int | None = Field(default=None, ge=0)
    context: dict[str, Any] | None = None
    effective_from: date
    note: str | None = Field(default=None, max_length=500)

class NormClose(BaseModel):
    effective_to: date

class NormOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    norm_key: str
    value: float
    product_type: str | None
    machine_id: int | None
    operation_id: int | None
    operation_key: str | None
    qty_min: int | None
    qty_max: int | None
    context: dict[str, Any] | None
    context_key: str
    effective_from: date
    effective_to: date | None
    note: str | None
    created_at: datetime
    updated_at: datetime

class NormListOut(BaseModel):
    items: list[NormOut]
    total: int
    page: int
    size: int
