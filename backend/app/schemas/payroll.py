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
    cong_doan_rate: float | None = Field(default=None, ge=0, le=1)
    deduction_self: float | None = Field(default=None, ge=0)
    deduction_dependent: float | None = Field(default=None, ge=0)
    chuyen_can_default: float | None = Field(default=None, ge=0)
    standard_hours_per_day: float | None = Field(default=None, gt=0, le=24)
    ot_multiplier: float | None = Field(default=None, ge=1, le=5)
    ot_multiplier_restday: float | None = Field(default=None, ge=1, le=5)
    ot_multiplier_holiday: float | None = Field(default=None, ge=1, le=5)
    restday_work_multiplier: float | None = Field(default=None, ge=1, le=5)
    holiday_work_multiplier: float | None = Field(default=None, ge=1, le=5)
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
    cong_doan_rate: float = 0
    deduction_self: float
    deduction_dependent: float
    chuyen_can_default: float
    standard_hours_per_day: float
    ot_multiplier: float
    ot_multiplier_restday: float
    ot_multiplier_holiday: float
    restday_work_multiplier: float
    holiday_work_multiplier: float
    night_pct: float
    bh_base_cap: float
    bhtn_base_cap: float


# --- biểu thuế TNCN ---------------------------------------------------------


class PitBracketIn(BaseModel):
    seq: int = Field(ge=1)
    up_to: float | None = Field(default=None, ge=0)   # None = bậc cao nhất (∞)
    rate: float = Field(ge=0, le=1)


class PitBracketOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    seq: int
    up_to: float | None = None
    rate: float


class PitBracketsOut(BaseModel):
    items: list[PitBracketOut]


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
    amount_mode: str = Field(default="rule", pattern="^(rule|manual|dept_row)$")
    base_amount: float | None = Field(default=None, ge=0)
    # Trỏ 1 dòng bảng lương của tổ (department_salary_rows) → engine đọc sống. Khi set thì
    # amount_mode tự thành 'dept_row' (service tự đặt).
    source_salary_row_id: int | None = Field(default=None, ge=1)
    insurance_base: float | None = Field(default=None, ge=0)
    allowance: float = Field(default=0, ge=0)          # phụ cấp riêng NV
    chuyen_can: float = Field(default=0, ge=0)         # chuyên cần riêng NV
    note: str | None = Field(default=None, max_length=255)


class SalaryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    employee_id: int
    effective_from: date
    amount_mode: str
    base_amount: float | None = None
    source_salary_row_id: int | None = None
    insurance_base: float | None = None
    allowance: float
    chuyen_can: float = 0
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


class MyAdvanceIn(BaseModel):
    """Nhân viên tự lập đề nghị tạm ứng cho CHÍNH MÌNH (không có employee_id — suy từ user)."""
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
    code: str | None = None                # mã tạm ứng TU26-xxxx (sinh khi tạo)
    employee_id: int
    employee_name: str | None = None       # router fills
    department_name: str | None = None     # router fills — cho phiếu in
    bank_account: str | None = None        # router fills (bank của NV)
    bank_name: str | None = None           # router fills
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
    paid_at: datetime | None = None
    paid_by: int | None = None


class PeriodsOut(BaseModel):
    items: list[PeriodOut]


class GenerateIn(BaseModel):
    year: int = Field(ge=2000, le=2100)
    month: int = Field(ge=1, le=12)


class PeriodPayIn(BaseModel):
    year: int = Field(ge=2000, le=2100)
    month: int = Field(ge=1, le=12)
    note: str | None = Field(default=None, max_length=255)


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
    thuong_5s: float = 0
    thuong_doanh_so: float = 0
    thuong_thanh_tich: float = 0
    phep_nam: float = 0
    tra_dong_phuc: float = 0
    dieu_chinh_luong: float = 0
    di_tre: float = 0
    dt_vuot_troi: float = 0
    phat_bien_ban: float = 0
    phat_5s_dong_phuc: float = 0
    gross: float
    insurance_base: float
    bhxh: float
    cong_doan: float = 0
    pit: float
    pit_manual: bool = False
    pit_taxable: float = 0
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
    pit_manual: bool | None = None   # False = reset về tự tính; None = giữ nguyên
    monthly_override: float | None = Field(default=None, ge=0)
    note: str | None = Field(default=None, max_length=255)
    # Khoản chi tiết (phiếu lương) — HCNS nhập tay. Thưởng ge=0; dieu_chinh_luong cho phép ÂM.
    thuong_5s: float | None = Field(default=None, ge=0)
    thuong_doanh_so: float | None = Field(default=None, ge=0)
    thuong_thanh_tich: float | None = Field(default=None, ge=0)
    phep_nam: float | None = Field(default=None, ge=0)
    tra_dong_phuc: float | None = Field(default=None, ge=0)
    dieu_chinh_luong: float | None = Field(default=None)
    di_tre: float | None = Field(default=None, ge=0)
    dt_vuot_troi: float | None = Field(default=None, ge=0)
    phat_bien_ban: float | None = Field(default=None, ge=0)
    phat_5s_dong_phuc: float | None = Field(default=None, ge=0)


# --- self-service phiếu lương -----------------------------------------------


class PayslipOut(BaseModel):
    has_employee: bool
    employee_name: str | None = None
    period: PeriodOut | None = None
    line: LineOut | None = None
