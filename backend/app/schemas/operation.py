"""Pydantic schemas for the Operations API — spec-20/21.
"""
from __future__ import annotations

from datetime import date, datetime
from pydantic import BaseModel, ConfigDict, Field

class OperationRateCreate(BaseModel):
    setup_fee: int = Field(default=0, ge=0)
    run_rate: int = Field(default=0, ge=0)
    labor_rate: int = Field(default=0, ge=0)
    min_charge: int = Field(default=0, ge=0)
    speed: float = Field(default=0.0, ge=0)
    effective_from: date

class OperationRateOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    setup_fee: int
    run_rate: int
    labor_rate: int
    min_charge: int
    speed: float
    effective_from: date
    effective_to: date | None
    created_at: datetime

class OperationCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    # in, can_mang, be, gap, dong_cuon, dong_goi...
    operation_type: str = Field(min_length=1, max_length=32)
    unit: str = Field(min_length=1, max_length=16) # m2, luot, to, cuon, san_pham...
    allow_outsource: bool = False
    is_active: bool = True

class OperationUpdate(OperationCreate):
    """Same as create; code is read-only and is not sent."""

class OperationRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    name: str
    operation_type: str
    unit: str
    allow_outsource: bool
    is_active: bool
    rates: list[OperationRateOut] = Field(default_factory=list)

class OperationListOut(BaseModel):
    items: list[OperationRow]
    total: int
    page: int
    size: int

class OperationDetailOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    name: str
    operation_type: str
    unit: str
    allow_outsource: bool
    is_active: bool
    created_at: datetime
    updated_at: datetime
    rates: list[OperationRateOut] = Field(default_factory=list)
