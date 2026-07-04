"""Pydantic schemas for the Norms/Losses API (danh mục #7 — Định mức & Bù hao)."""
from __future__ import annotations

from datetime import date, datetime
from typing import Any
from pydantic import BaseModel, ConfigDict, Field


class NormCreate(BaseModel):
    # norm_key HOẶC waste_group — service tự suy cái còn lại (backward-compat với API cũ).
    norm_key: str | None = Field(default=None, max_length=32)
    waste_group: str | None = Field(default=None, max_length=24)
    calculation_method: str | None = Field(default=None, max_length=24)
    value: float = Field(default=0.0, ge=0)

    code: str | None = Field(default=None, max_length=64)
    name: str | None = Field(default=None, max_length=200)

    product_type: str | None = Field(default=None, max_length=32)
    machine_id: int | None = None
    operation_id: int | None = None
    operation_key: str | None = Field(default=None, max_length=32)
    applicable_product_types: list[str] | None = None
    applicable_machine_ids: list[int] | None = None

    qty_min: int | None = Field(default=None, ge=0)
    qty_max: int | None = Field(default=None, ge=0)
    context: dict[str, Any] | None = None

    # SETUP_WASTE
    setup_waste_qty: float | None = Field(default=None, ge=0)
    setup_waste_per_color: float | None = Field(default=None, ge=0)
    setup_waste_per_side: float | None = Field(default=None, ge=0)
    # clamp (SETUP / RUNNING / PAPER)
    min_waste_qty: float | None = Field(default=None, ge=0)
    max_waste_qty: float | None = Field(default=None, ge=0)
    # PAPER_EXTRA_WASTE
    paper_add_to_purchase: bool = True

    priority: int = 100
    effective_from: date
    note: str | None = Field(default=None, max_length=500)


class NormClose(BaseModel):
    effective_to: date


class NormDuplicate(BaseModel):
    """Sao chép rule → mở form thêm mới; server có thể tạo ngay bản mới với ngày hiệu lực mới."""
    effective_from: date
    code: str | None = Field(default=None, max_length=64)


class NormOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    norm_key: str
    waste_group: str | None
    calculation_method: str | None
    value: float
    code: str | None
    name: str | None
    product_type: str | None
    machine_id: int | None
    operation_id: int | None
    operation_key: str | None
    applicable_product_types: list[Any] | None
    applicable_machine_ids: list[Any] | None
    qty_min: int | None
    qty_max: int | None
    context: dict[str, Any] | None
    context_key: str
    setup_waste_qty: float | None
    setup_waste_per_color: float | None
    setup_waste_per_side: float | None
    min_waste_qty: float | None
    max_waste_qty: float | None
    paper_add_to_purchase: bool
    priority: int
    version: int
    used_count: int
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


# --- Test nhanh (§4.2 Khối 5) — chạy thử chuỗi số tờ, không ghi DB ---------

class NormTestInput(BaseModel):
    quantity: int = Field(ge=1)
    pieces_per_sheet: int = Field(default=1, ge=1)
    colors: int = Field(default=4, ge=1)
    sides: int = Field(default=1, ge=1)
    forms: int = Field(default=1, ge=1)
    product_type: str | None = None
    machine_id: int | None = None
    # Chuỗi công đoạn sau in theo thứ tự sản xuất (in → cán → bế → dán…).
    operation_keys: list[str] = Field(default_factory=list)
    at_date: date | None = None


class NormTestStep(BaseModel):
    label: str
    detail: str
    rule_code: str | None = None
    value: float | None = None


class NormTestOutput(BaseModel):
    theoretical_sheets: int
    required_before_print: int
    sheets_after_yield: int
    makeready_sheets: int
    running_sheets: int
    production_sheets: int
    paper_extra_sheets: int
    purchase_sheets: int
    steps: list[NormTestStep]
    warnings: list[str] = Field(default_factory=list)
