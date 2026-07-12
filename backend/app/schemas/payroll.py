"""Pydantic models cho API Lương (module `luong`, Phase 1)."""
from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field


# --- params -----------------------------------------------------------------


class ParamsIn(BaseModel):
    standard_cong_default: float | None = Field(default=None, gt=0, le=31)
    probation_ratio: float | None = Field(default=None, gt=0, le=1)
    bhxh_rate: float | None = Field(default=None, ge=0, le=1)
    bhyt_rate: float | None = Field(default=None, ge=0, le=1)
    bhtn_rate: float | None = Field(default=None, ge=0, le=1)
    deduction_self: float | None = Field(default=None, ge=0)
    deduction_dependent: float | None = Field(default=None, ge=0)
    chuyen_can_default: float | None = Field(default=None, ge=0)
    standard_hours_per_day: float | None = Field(default=None, gt=0, le=24)
    ot_multiplier: float | None = Field(default=None, ge=1, le=5)
    night_pct: float | None = Field(default=None, ge=0, le=2)
    bh_base_cap: float | None = Field(default=None, ge=0)
    bhtn_base_cap: float | None = Field(default=None, ge=0)


class ParamsOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    standard_cong_default: float
    probation_ratio: float
    bhxh_rate: float
    bhyt_rate: float
    bhtn_rate: float
    deduction_self: float
    deduction_dependent: float
    chuyen_can_default: float
    standard_hours_per_day: float
    ot_multiplier: float
    night_pct: float
    bh_base_cap: float
    bhtn_base_cap: float


# --- salary_rate_rules ------------------------------------------------------


class RuleIn(BaseModel):
    payroll_group: str = Field(min_length=1, max_length=40)
    pay_grade_key: str | None = Field(default=None, max_length=20)
    seniority_band: str | None = Field(default=None, max_length=8)
    gender: str | None = Field(default=None, max_length=8)
    monthly_amount: float = Field(ge=0)
    chuyen_can: float | None = Field(default=None, ge=0)
    effective_from: date | None = None
    is_active: bool = True
    note: str | None = Field(default=None, max_length=255)


class RuleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    payroll_group: str
    pay_grade_key: str | None = None
    seniority_band: str | None = None
    gender: str | None = None
    monthly_amount: float
    chuyen_can: float | None = None
    effective_from: date | None = None
    is_active: bool
    note: str | None = None


class RulesOut(BaseModel):
    items: list[RuleOut]


# --- employee_salaries ------------------------------------------------------


class SalaryIn(BaseModel):
    effective_from: date
    amount_mode: str = Field(default="rule", pattern="^(rule|manual)$")
    base_amount: float | None = Field(default=None, ge=0)
    insurance_base: float | None = Field(default=None, ge=0)
    allowance: float = Field(default=0, ge=0)
    note: str | None = Field(default=None, max_length=255)


class SalaryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    employee_id: int
    effective_from: date
    amount_mode: str
    base_amount: float | None = None
    insurance_base: float | None = None
    allowance: float
    note: str | None = None
    created_at: datetime


class SalariesOut(BaseModel):
    employee_id: int
    employee_name: str | None = None
    items: list[SalaryOut]


class SalaryPreviewOut(BaseModel):
    employee_id: int
    monthly: float
    source: str            # rule | manual | none
    chuyen_can: float
    allowance: float
    insurance_base: float


# --- advances ---------------------------------------------------------------


class AdvanceIn(BaseModel):
    employee_id: int
    period_year: int = Field(ge=2000, le=2100)
    period_month: int = Field(ge=1, le=12)
    advance_date: date
    amount: float = Field(gt=0)
    reason: str | None = Field(default=None, max_length=255)


class AdvanceDecisionIn(BaseModel):
    note: str | None = Field(default=None, max_length=255)


class AdvanceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    employee_id: int
    employee_name: str | None = None       # router fills
    period_year: int
    period_month: int
    advance_date: date
    amount: float
    reason: str | None = None
    status: str
    decision_note: str | None = None
    created_at: datetime


class AdvancesOut(BaseModel):
    items: list[AdvanceOut]


class MyAdvancesOut(BaseModel):
    has_employee: bool
    items: list[AdvanceOut]


# --- periods / bảng lương ---------------------------------------------------


class PeriodOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    year: int
    month: int
    status: str
    standard_cong: float
    locked_at: datetime | None = None


class PeriodsOut(BaseModel):
    items: list[PeriodOut]


class GenerateIn(BaseModel):
    year: int = Field(ge=2000, le=2100)
    month: int = Field(ge=1, le=12)


class LineOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    employee_id: int
    employee_code: str | None = None       # router fills
    employee_name: str | None = None
    department_name: str | None = None
    payroll_group: str | None = None
    bank_account: str | None = None
    bank_name: str | None = None
    is_probation: bool
    actual_cong: float
    standard_cong: float
    monthly_salary: float
    luong_cong: float
    chuyen_can: float
    allowance: float
    khoan: float = 0
    ot_minutes: int = 0
    ot_pay: float = 0
    night_days: int = 0
    night_pay: float = 0
    vi_pham: float
    other_bonus: float
    gross: float
    insurance_base: float
    bhxh: float
    pit: float
    advance_total: float
    net_pay: float
    note: str | None = None


class TableOut(BaseModel):
    period: PeriodOut | None = None
    lines: list[LineOut] = []


class LineUpdateIn(BaseModel):
    vi_pham: float | None = Field(default=None, ge=0)
    other_bonus: float | None = Field(default=None, ge=0)
    pit: float | None = Field(default=None, ge=0)
    monthly_override: float | None = Field(default=None, ge=0)
    note: str | None = Field(default=None, max_length=255)


# --- self-service phiếu lương -----------------------------------------------


class PayslipOut(BaseModel):
    has_employee: bool
    employee_name: str | None = None
    period: PeriodOut | None = None
    line: LineOut | None = None
