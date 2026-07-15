"""Pydantic schemas — Phiếu sản lượng công đoạn (Pha 5b)."""
from __future__ import annotations

from datetime import date

from pydantic import BaseModel, ConfigDict, Field


class OutputIn(BaseModel):
    production_order_id: int
    cong_doan: str = Field(min_length=1, max_length=30)
    year: int
    month: int = Field(ge=1, le=12)
    group_name: str | None = Field(default=None, max_length=40)
    employee_id: int | None = None      # khi công đoạn ghi_theo=nguoi (5b-2)
    piece_rate_id: int | None = None
    work_name: str | None = Field(default=None, max_length=255)
    unit: str | None = Field(default=None, max_length=12)
    unit_price: float | None = Field(default=None, ge=0)
    quantity: float = Field(default=0, ge=0)
    defect_qty: float = Field(default=0, ge=0)
    defect_cause: str | None = Field(default=None, max_length=20)
    may_id: int | None = None
    tinh_khoan: bool | None = None      # gate quyền cao (luong) — router kiểm
    work_date: date | None = None
    note: str | None = Field(default=None, max_length=255)


class OutputUpdateIn(BaseModel):
    quantity: float | None = Field(default=None, ge=0)
    unit_price: float | None = Field(default=None, ge=0)
    defect_qty: float | None = Field(default=None, ge=0)
    defect_cause: str | None = Field(default=None, max_length=20)
    may_id: int | None = None
    tinh_khoan: bool | None = None
    work_date: date | None = None
    note: str | None = Field(default=None, max_length=255)


class OutputOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    production_order_id: int
    cong_doan: str
    ghi_theo: str
    year: int
    month: int
    group_name: str | None = None
    employee_id: int | None = None
    may_id: int | None = None
    piece_rate_id: int | None = None
    work_name: str
    unit: str
    unit_price: float
    quantity: float
    amount: float = 0        # router tính qty×price cho FE
    defect_qty: float = 0
    defect_cause: str | None = None
    defect_deduction: float = 0
    net_amount: float = 0    # amount − defect_deduction (sàn 0), router tính
    tinh_khoan: bool
    work_date: date | None = None
    note: str | None = None


class OutputsOut(BaseModel):
    items: list[OutputOut]


class DefectReportRow(BaseModel):
    scope: str                       # nguoi / to
    employee_id: int | None = None
    group_name: str | None = None
    quantity: float
    defect_qty: float
    deduction: float
    defect_rate: float               # defect / (đạt + hỏng)


class DefectReportOut(BaseModel):
    items: list[DefectReportRow]
