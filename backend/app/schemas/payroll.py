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
    # Trần tạm ứng/tháng theo % (lương vị trí + trách nhiệm). 0 = không giới hạn.
    advance_max_pct: float | None = Field(default=None, ge=0, le=1)
    # Phía NGƯỜI SỬ DỤNG LAO ĐỘNG — KHÔNG trừ vào lương NV, chỉ tính chi phí công ty.
    bhxh_rate_er: float | None = Field(default=None, ge=0, le=1)
    bhyt_rate_er: float | None = Field(default=None, ge=0, le=1)
    bhtn_rate_er: float | None = Field(default=None, ge=0, le=1)
    cong_doan_rate: float | None = Field(default=None, ge=0, le=1)
    # TNLĐ-BNN do CÔNG TY chịu (mẫu 0.5% = 0.005) — dùng khi NV có BH đóng ở nơi khác.
    tnld_bnn_rate: float | None = Field(default=None, ge=0, le=1)
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
    ot_night_extra_pct: float | None = Field(default=None, ge=0, le=2)
    bh_base_cap: float | None = Field(default=None, ge=0)
    bhtn_base_cap: float | None = Field(default=None, ge=0)
    # Phụ cấp cơm/ca đêm KHÔNG còn ở cấp công ty — khai theo từng CA (`work_shifts`).


class ParamsOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    standard_cong_default: float
    probation_ratio: float
    bhxh_rate: float
    bhyt_rate: float
    bhtn_rate: float
    advance_max_pct: float = 0.10
    bhxh_rate_er: float = 0.175
    bhyt_rate_er: float = 0.03
    bhtn_rate_er: float = 0.01
    cong_doan_rate: float = 0
    tnld_bnn_rate: float = 0.005
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
    ot_night_extra_pct: float = 0.2
    bh_base_cap: float
    bhtn_base_cap: float


# --- thành phần lương theo BỘ PHẬN (Cấu hình lương, Tab 2) ------------------

_COMPONENT_KEY = "^(kpi|chuyen_can|luong_khoan|tang_ca)$"


class DeptComponentIn(BaseModel):
    component_key: str = Field(pattern=_COMPONENT_KEY)
    is_enabled: bool = True
    # Mức của TỔ (PRD v2 C6 — TỔ là nơi khai chính). NULL = bật nhưng CHƯA khai mức → 0đ
    # (không còn "mức mặc định công ty" để rơi xuống).
    value: float | None = Field(default=None, ge=0)


class DeptComponentsIn(BaseModel):
    items: list[DeptComponentIn]


class DeptComponentOut(BaseModel):
    component_key: str
    is_enabled: bool
    value: float | None = None
    is_set: bool = False               # bộ phận đã khai riêng dòng này chưa
    # LEGACY (giữ để FE cũ không vỡ): danh mục phụ cấp cấp công ty đã gỡ — luôn trả mặc định.
    company_enabled: bool = True
    company_value: float | None = None
    company_unit: str | None = None


class DeptComponentsOut(BaseModel):
    department_id: int
    items: list[DeptComponentOut]


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


# --- bảng phạt đi trễ / về sớm ----------------------------------------------


class LatePenaltyBracketIn(BaseModel):
    seq: int = Field(ge=1)
    up_to_minute: int | None = Field(default=None, ge=0)   # None = bậc cao nhất (∞)
    amount: float = Field(ge=0)


class LatePenaltyBracketOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    seq: int
    up_to_minute: int | None = None
    amount: float


class LatePenaltyBracketsOut(BaseModel):
    items: list[LatePenaltyBracketOut]


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
    amount_mode: str = Field(default="manual", pattern="^(rule|manual|dept_row)$")
    base_amount: float | None = Field(default=None, ge=0)
    # MỨC LƯƠNG của NV — gõ riêng từng ô. Lương vị trí = lương cơ bản = mức đóng BH.
    luong_vi_tri: float = Field(default=0, ge=0)
    luong_trach_nhiem: float = Field(default=0, ge=0)
    # DORMANT: mức đóng BH khai riêng — engine THÔI đọc (BH bám luong_vi_tri). Giữ nhận cho FE cũ.
    insurance_base: float | None = Field(default=None, ge=0)
    # 3 khoản PHỤ CẤP KHAI TAY của NV — số cố định dùng mọi tháng, engine cộng phẳng
    # (không prorate theo công, không vào gốc tính tăng ca), hệ thống KHÔNG tự tính.
    allowance: float = Field(default=0, ge=0)              # phụ cấp KHÁC (gộp)
    phu_cap_ca: float = Field(default=0, ge=0)             # phụ cấp ca (đêm/tới sáng/cơm ca…)
    phu_cap_tham_nien: float = Field(default=0, ge=0)
    chuyen_can: float = Field(default=0, ge=0)         # chuyên cần riêng NV
    # BH đóng ở nơi khác → công ty không trừ BHXH/BHYT/BHTN của NV, chỉ chịu TNLĐ-BNN.
    insurance_elsewhere: bool = False
    # Đoàn viên công đoàn → mới bị trừ đoàn phí công đoàn (mặc định false = không đóng).
    union_member: bool = False
    note: str | None = Field(default=None, max_length=255)


class SalaryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    employee_id: int
    effective_from: date
    effective_to: date | None = None
    is_current: bool = False
    amount_mode: str
    base_amount: float | None = None
    luong_vi_tri: float = 0
    luong_trach_nhiem: float = 0
    insurance_base: float | None = None
    allowance: float
    phu_cap_ca: float = 0
    phu_cap_tham_nien: float = 0
    chuyen_can: float = 0
    insurance_elsewhere: bool = False   # cờ "BH đóng ở nơi khác" — để modal prefill checkbox
    union_member: bool = False          # cờ "đoàn viên công đoàn" — để modal prefill checkbox
    note: str | None = None
    created_at: datetime
    created_by: int | None = None
    actor_name: str | None = None      # tên người điều chỉnh (nhật ký "ai sửa")


class SalariesOut(BaseModel):
    employee_id: int
    employee_name: str | None = None
    items: list[SalaryOut]


class SalaryPreviewOut(BaseModel):
    employee_id: int
    monthly: float
    source: str            # employee | manual | none
    chuyen_can: float
    allowance: float
    phu_cap_ca: float = 0
    phu_cap_tham_nien: float = 0
    insurance_base: float    # = luong_vi_tri (mức đóng BH)
    luong_vi_tri: float = 0
    luong_trach_nhiem: float = 0


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


class AdvanceQuotaOut(BaseModel):
    """Hạn mức tạm ứng của 1 NV trong 1 kỳ — nuôi dòng "còn được ứng" trên form đề nghị."""

    monthly: float               # lương tháng làm gốc (vị trí + trách nhiệm)
    pct: float                   # tỷ lệ trần đang áp (0 = không giới hạn)
    limit: float | None = None   # số tiền trần; None = không giới hạn
    used: float = 0              # đã duyệt + đang chờ duyệt trong kỳ
    remaining: float | None = None  # còn được ứng; None = không giới hạn


class InsuranceLineOut(BaseModel):
    """Một dòng bảo hiểm NV đóng trên phiếu lương (BHXH / BHYT / BHTN), nhãn đã kèm tỷ lệ.

    Backend trả thẳng SỐ TIỀN để phiếu lương không phải đi xin tỷ lệ qua `GET /params` (endpoint đó
    đòi quyền `luong:view_salary` — nhân viên xem phiếu của chính mình không có ⇒ trước đây rơi về
    một dòng gộp). Ba dòng LUÔN cộng đúng bằng `LineOut.bhxh` đã đóng băng."""

    label: str
    amount: float


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
    allowance: float               # TỔNG phụ cấp tháng (đã gồm 3 dòng dưới)
    # Tách dòng cho phiếu lương (B2) — 2 số này CỘNG LẠI = `allowance`, đừng cộng thêm vào tổng.
    phu_cap_tham_nien: float = 0
    phu_cap_khac: float = 0        # router fills = allowance − thâm niên
    khoan: float = 0
    ot_minutes: int = 0
    ot_pay: float = 0
    night_days: int = 0
    night_pay: float = 0           # = phụ cấp CA khai tay của NV — cột DB
    ca_pay: float = 0              # alias của `night_pay` (cùng MỘT số, đừng cộng 2 lần)
    night_premium_pay: float = 0   # premium CA ĐÊM theo giờ (giờ đêm × hệ số + tăng ca đêm) — tự tính, miễn TNCN
    kpi_percent: float = 0
    kpi_bonus: float = 0
    vi_pham: float
    other_bonus: float
    thuong_5s: float = 0
    thuong_doanh_so: float = 0
    thuong_thanh_tich: float = 0
    phep_nam: float = 0
    tra_dong_phuc: float = 0
    dieu_chinh_luong: float = 0
    di_tre: float = 0
    di_tre_manual: bool = False    # True = HCNS sửa tay (phạt tự động không đè); False = tự động từ chấm công
    dt_vuot_troi: float = 0
    phat_bien_ban: float = 0
    phat_5s_dong_phuc: float = 0
    gross: float
    insurance_base: float
    bhxh: float                    # TỔNG bảo hiểm NV đóng (10.5%) — số đã đóng băng lúc tính lương
    # Tách 3 khoản để phiếu lương hiện chi tiết; tổng 3 dòng == `bhxh`. Router điền (cần params).
    insurance_lines: list[InsuranceLineOut] = []
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
    di_tre_manual: bool | None = None  # False = đưa phạt trễ VỀ TỰ ĐỘNG (tính lại từ chấm công); None = giữ
    monthly_override: float | None = Field(default=None, ge=0)
    note: str | None = Field(default=None, max_length=255)
    # % đạt KPI của tháng (ô nhập tay) → tiền = % × mức trần KPI của bộ phận.
    kpi_percent: float | None = Field(default=None, ge=0, le=200)
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
