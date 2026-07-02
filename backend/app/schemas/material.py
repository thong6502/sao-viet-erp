"""Pydantic schemas for the Materials API — spec-20/21.
"""
from __future__ import annotations

from datetime import date, datetime
from pydantic import BaseModel, ConfigDict, Field

class MaterialCostCreate(BaseModel):
    price_unit: str = Field(min_length=1, max_length=16)
    unit_price: int = Field(ge=0)
    effective_from: date

class MaterialCostOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    price_unit: str
    unit_price: int
    effective_from: date
    effective_to: date | None
    created_at: datetime

class MaterialCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    material_type: str = Field(min_length=1, max_length=32)
    unit: str = Field(min_length=1, max_length=16)
    min_fee: int = Field(default=0, ge=0)
    
    width_cm: float | None = Field(default=None, ge=0)
    height_cm: float | None = Field(default=None, ge=0)
    gsm: int | None = Field(default=None, ge=0)
    thickness_mm: float | None = Field(default=None, ge=0)
    default_waste_pct: float = Field(default=0.0, ge=0)
    min_purchase_qty: float = Field(default=0.0, ge=0)
    
    paper_family: str | None = Field(default=None, max_length=32)
    surface: str | None = Field(default=None, max_length=32)
    is_active: bool = True

class MaterialUpdate(MaterialCreate):
    """Same as create; code is read-only and is not sent."""

class MaterialRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    name: str
    material_type: str
    unit: str
    is_active: bool
    width_cm: float | None
    height_cm: float | None
    gsm: int | None
    paper_family: str | None
    surface: str | None
    costs: list[MaterialCostOut] = Field(default_factory=list)

class MaterialListStats(BaseModel):
    total_materials: int
    total_papers: int
    total_consumables: int
    no_price_count: int
    price_updates_this_month: int

class MaterialListOut(BaseModel):
    items: list[MaterialRow]
    total: int
    page: int
    size: int
    stats: MaterialListStats

class MaterialDetailOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    name: str
    material_type: str
    unit: str
    min_fee: int
    width_cm: float | None
    height_cm: float | None
    gsm: int | None
    thickness_mm: float | None
    default_waste_pct: float
    min_purchase_qty: float
    paper_family: str | None
    surface: str | None
    is_active: bool
    created_at: datetime
    updated_at: datetime
    costs: list[MaterialCostOut] = Field(default_factory=list)
