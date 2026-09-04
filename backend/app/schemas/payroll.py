"""Pydantic models cho API Lương (module `luong`, Phase 1)."""
from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field


# --- params -----------------------------------------------------------------


class ParamsIn(BaseModel):
    standard_cong_default: float | None = Field(default=None, gt=0, le=31)
    probation_ratio: float | None = Field(default=None, gt=0, le=1)
    ot_max_minutes_per_month: int | None = Field(default=None, ge=0, le=44640)
    ot_max_minutes_per_day: int | None = Field(default=None, gt=0, le=2880)
    bhxh_rate: float | None = Field(default=None, ge=0, le=1)
    bhyt_rate: float | None = Field(default=None, ge=0, le=1)
    bhtn_rate: float | None = Field(default=None, ge=0, le=1)
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
    # Hạn mức chỉnh công/tháng (số NGÀY CÔNG, không phải số đơn). 0 = không giới hạn.
    adjust_max_per_month: int | None = Field(default=None, ge=0, le=31)
    # Khấu trừ 10% tại nguồn cho HĐ dưới 3 tháng / thời vụ.
    pit_flat_rate: float | None = Field(default=None, ge=0, le=1)
    pit_flat_threshold: float | None = Field(default=None, ge=0)
    # Trần khấu trừ kỷ luật (Đ102 BLLĐ). 0 = TẮT trần — cố ý cho phép, chủ tự chịu rủi ro.
    phat_cap_pct: float | None = Field(default=None, ge=0, le=1)
    # Ngưỡng ngày nghỉ không lương để MIỄN đóng BHXH tháng đó (QĐ 595 Đ42.4). 0 = TẮT luật.
    # `le=31` vì đây là số NGÀY trong một tháng, không phải tỷ lệ.
    bhxh_mien_tu_so_ngay: int | None = Field(default=None, ge=0, le=31)
    # Ngưỡng CÔNG của một ngày để hưởng trọn cơm/phụ cấp ca hôm đó (0,5 = nghỉ nửa buổi vẫn ăn).
    phu_cap_ca_min_cong: float | None = Field(default=None, ge=0, le=1)
    # SUẤT CƠM TĂNG CA — ngưỡng phút/ngày (chỉ áp cho NGÀY LÀM VIỆC) và tiền một suất.
    com_tang_ca_nguong_phut: int | None = Field(default=None, ge=0, le=1440)
    com_tang_ca_muc: float | None = Field(default=None, ge=0)
    # Phụ cấp cơm/ca đêm KHÔNG còn ở cấp công ty — khai theo từng CA (`work_shifts`).


class ParamsOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    standard_cong_default: float
    probation_ratio: float
    ot_max_minutes_per_month: int
    ot_max_minutes_per_day: int
    bhxh_rate: float
    bhyt_rate: float
    bhtn_rate: float
    advance_max_pct: float = 0.10
    # Mặc định để dòng params CŨ (chưa có cột) không vỡ validate.
    adjust_max_per_month: int = 5
    pit_flat_rate: float = 0.10
    pit_flat_threshold: float = 2_000_000
    phat_cap_pct: float = 0.30
    bhxh_mien_tu_so_ngay: int = 14
    phu_cap_ca_min_cong: float = 0.5
    # Mặc định để dòng params CŨ (chưa có cột) không vỡ validate — cùng lối các trường trên.
    com_tang_ca_nguong_phut: int = 180
    com_tang_ca_muc: float = 0
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

_COMPONENT_KEY = "^(chuyen_can|luong_khoan|tang_ca)$"   # `kpi` gỡ 29/07/2026


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
    # Có áp giảm trừ bản thân khi tính TNCN không. Mặc định BẬT; tắt khi người này đã đăng ký
    # giảm trừ bản thân ở nơi làm việc khác (chỉ được đăng ký ở MỘT nơi).
    apply_self_deduction: bool = True
    # % hoa hồng NV kinh doanh — PHÂN SỐ (0.05 = 5%). Chặn trên 1 để khỏi ai gõ "5" ra 500%.
    commission_pct: float = Field(default=0, ge=0, le=1)
    # "Lương trả 1 lần" — mức cố định điền sẵn khi tạo phiếu thanh toán lương đợt 1.
    luong_dot_1: float = Field(default=0, ge=0)
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
    apply_self_deduction: bool = True   # cờ giảm trừ bản thân — modal prefill checkbox
    # ⚠️ Thiếu dòng này là API nuốt im lặng: service trả đúng, Pydantic vứt, không báo lỗi.
    commission_pct: float = 0           # % hoa hồng (phân số) — modal prefill
    luong_dot_1: float = 0              # "lương trả 1 lần" — prefill khi tạo phiếu đợt 1
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
    # Loại phiếu: "tam_ung" (mặc định) | "luong_dot_1" (thanh toán lương đợt 1).
    kind: str = Field(default="tam_ung", pattern="^(tam_ung|luong_dot_1)$")


class MyAdvanceIn(BaseModel):
    """Nhân viên tự lập đề nghị tạm ứng cho CHÍNH MÌNH (không có employee_id — suy từ user)."""
    period_year: int = Field(ge=2000, le=2100)
    period_month: int = Field(ge=1, le=12)
    advance_date: date
    amount: float = Field(gt=0)
    reason: str | None = Field(default=None, max_length=255)
    kind: str = Field(default="tam_ung", pattern="^(tam_ung|luong_dot_1)$")


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
    kind: str = "tam_ung"                   # tam_ung | luong_dot_1
    status: str
    decision_note: str | None = None
    created_at: datetime


class AdvancesOut(BaseModel):
    items: list[AdvanceOut]


class MyAdvancesOut(BaseModel):
    has_employee: bool
    items: list[AdvanceOut]
    # Mức "Lương trả 1 lần" hiện hành của NV — FE điền sẵn khi tự xin phiếu đợt 1 (0 = chưa khai).
    luong_dot_1: float = 0
    #: Tháng SỚM NHẤT còn lập phiếu được ("YYYY-MM") = liền sau kỳ đã chốt/đã chi muộn nhất.
    #: FE đặt làm `min` của ô chọn kỳ — kỳ đã khoá KHÔNG chọn được nữa (chủ chốt 18/08/2026).
    ky_min_chon_duoc: str | None = None


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
    #: Cửa sổ xem phiếu của NLĐ: mở lúc `cong_bo_luc`, đóng lúc `dong_phieu_luc`.
    #: `cong_bo_luc = None` ⇒ chưa công bố. `dong_phieu_luc = None` ⇒ mở không thời hạn.
    cong_bo_luc: datetime | None = None
    dong_phieu_luc: datetime | None = None


class PeriodsOut(BaseModel):
    items: list[PeriodOut]


class GenerateIn(BaseModel):
    year: int = Field(ge=2000, le=2100)
    month: int = Field(ge=1, le=12)


class CongBoIn(BaseModel):
    """Cửa sổ xem phiếu. `luc = None` ⇒ mở NGAY. `den = None` ⇒ mở không thời hạn."""

    year: int = Field(ge=2000, le=2100)
    month: int = Field(ge=1, le=12)
    luc: datetime | None = None
    den: datetime | None = None


class PeriodPayIn(BaseModel):
    year: int = Field(ge=2000, le=2100)
    month: int = Field(ge=1, le=12)
    note: str | None = Field(default=None, max_length=255)


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
    # TRONG ĐÓ của `luong_cong` — tiền những ngày nghỉ phép, trả theo LƯƠNG VỊ TRÍ (không lương
    # trách nhiệm). ĐỪNG cộng thêm vào tổng: đã nằm trong `luong_cong` (cùng kiểu `phu_cap_tham_nien`).
    luong_ngay_phep: float = 0
    paid_leave_cong: float = 0     # số công phép có lương thực được trả
    excused_cong: float = 0        # công thiếu ĐƯỢC PHÉP (đơn nghỉ theo giờ) — giải trình chuyên cần
    chuyen_can: float
    allowance: float               # TỔNG phụ cấp tháng (đã gồm 3 dòng dưới)
    # Tách dòng cho phiếu lương (B2) — 2 số này CỘNG LẠI = `allowance`, đừng cộng thêm vào tổng.
    phu_cap_tham_nien: float = 0
    phu_cap_khac: float = 0        # router fills = allowance − thâm niên
    khoan: float = 0
    #: Khoán km giao hàng (mg 0231) — CỘNG THÊM vào gross, không phải "trong đó" của khoản nào.
    khoan_km: float = 0
    #: Thưởng/PHẠT tổ trưởng theo chất lượng (mg 0266) — CỘNG ĐẠI SỐ vào gross, CÓ THỂ ÂM.
    thuong_to_truong: float = 0
    ot_minutes: int = 0
    ot_pay: float = 0
    night_days: int = 0
    night_pay: float = 0           # = phụ cấp CA khai tay của NV — cột DB
    ca_pay: float = 0              # alias của `night_pay` (cùng MỘT số, đừng cộng 2 lần)
    night_premium_pay: float = 0   # premium CA ĐÊM theo giờ (giờ đêm × hệ số + tăng ca đêm) — tự tính, miễn TNCN
    # Phụ cấp theo CA THỰC LÀM (03/08/2026). Engine tính và LƯU từ đầu nhưng schema quên phơi ra
    # ⇒ phiếu lương ở FE đọc `l.meal_allowance_pay ?? 0` nên hiện 0đ mãi dù tiền đã cộng vào gross.
    meal_allowance_pay: float = 0
    #: Cơm TĂNG CA — dòng riêng trên phiếu lương, không gộp vào cơm ca (hai luật khác nhau,
    #: một ngày có thể ăn cả hai).
    com_tang_ca_pay: float = 0
    shift_allowance_pay: float = 0
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
    # Thu nhập CHỊU thuế = tổng lương − các khoản miễn (TRƯỚC giảm trừ gia cảnh + BHXH).
    # Khác `pit_taxable` (thu nhập TÍNH thuế, sau giảm trừ) ~15,5tr — đừng dùng lẫn.
    thu_nhap_chiu_thue: float = 0
    # Khoản DANH MỤC của dòng này (snapshot Tầng 3) — phiếu lương in TỪNG DÒNG từ đây.
    # ⚠️ Không có field này thì khoản `source='line'` (thưởng nóng) cộng vào `gross` nhưng KHÔNG
    # có dòng nào trên phiếu ⇒ tổng thu trên phiếu nhỏ hơn thực nhận, NV không đối chiếu được.
    components: list[LineComponentOut] = []
    # Tổng phần thu nhập được MIỄN thuế của kỳ (tăng ca + ca đêm + khoản danh mục không chịu thuế).
    # Thiếu dòng này thì cột tính đúng nhưng API nuốt mất — phiếu lương không bao giờ hiện được.
    thu_nhap_mien_thue: float = 0
    advance_total: float
    luong_dot_1_total: float = 0
    net_pay: float
    note: str | None = None


class TableOut(BaseModel):
    period: PeriodOut | None = None
    lines: list[LineOut] = []
    #: Vì sao CHƯA chốt được bảng lương — `None` = chốt được. Giao diện chỉ việc hiện câu này và
    #: tắt nút "Chốt"; KHÔNG tự suy lại luật (số lý do còn tăng, suy lại là hai bên trôi khác nhau).
    #: Xem `PayrollService.ly_do_chua_chot_duoc`.
    chan_chot_ly_do: str | None = None


class LineUpdateIn(BaseModel):
    # ⚠️ CỐ Ý KHÔNG CÓ: thuong_5s · thuong_doanh_so · thuong_thanh_tich · phep_nam ·
    # tra_dong_phuc · other_bonus. Từ 28/07/2026 mọi khoản thưởng khai qua DANH MỤC
    # (`POST /lines/{id}/components`) để cờ "Chịu thuế" là quy tắc chung, không phải ô tay đóng
    # đinh chịu thuế. 6 cột cũ vẫn còn trong `LineOut` + trong công thức cộng để kỳ ĐÃ CHỐT giữ
    # nguyên số; chỉ chặn ghi MỚI. Thêm lại vào đây là mở lại đường lách quy tắc thuế.
    vi_pham: float | None = Field(default=None, ge=0)
    pit: float | None = Field(default=None, ge=0)
    pit_manual: bool | None = None   # False = reset về tự tính; None = giữ nguyên
    di_tre_manual: bool | None = None  # False = đưa phạt trễ VỀ TỰ ĐỘNG (tính lại từ chấm công); None = giữ
    monthly_override: float | None = Field(default=None, ge=0)
    note: str | None = Field(default=None, max_length=255)
    # Khoản chi tiết (phiếu lương) — HCNS nhập tay. `dieu_chinh_luong` cho phép ÂM.
    dieu_chinh_luong: float | None = Field(default=None)
    di_tre: float | None = Field(default=None, ge=0)
    dt_vuot_troi: float | None = Field(default=None, ge=0)
    phat_bien_ban: float | None = Field(default=None, ge=0)
    phat_5s_dong_phuc: float | None = Field(default=None, ge=0)


# --- self-service phiếu lương -----------------------------------------------


class KyXemDuocOut(BaseModel):
    """Một kỳ NLĐ đang được xem phiếu — CHỈ nhãn tháng, không kèm tiền."""
    year: int
    month: int
    #: None = mở không thời hạn. Giao diện dùng để chú thích "xem tới ngày…".
    dong_phieu_luc: datetime | None = None


class ChoPhatOut(BaseModel):
    """Kỳ mới nhất NLĐ CHƯA được xem, kèm lý do — để màn hình thôi nói "chưa có kỳ lương nào".

    ⚠️ KHÔNG có trường tiền nào ở đây, và đừng thêm: cả cửa công bố sinh ra để NLĐ không đọc
    được số của kỳ chưa phát."""
    year: int
    month: int
    #: `chua_phat` (chưa ai bấm Công bố) · `hen_gio` (đã hẹn, chưa tới giờ) · `da_dong` (hết hạn xem)
    tinh_trang: str
    #: Chỉ có nghĩa khi `tinh_trang = "hen_gio"` — giờ phiếu sẽ mở.
    mo_luc: datetime | None = None


class PayslipOut(BaseModel):
    has_employee: bool
    employee_name: str | None = None
    period: PeriodOut | None = None
    line: LineOut | None = None
    #: Các kỳ NLĐ tra lại được, mới → cũ. Rỗng nghĩa là không có phiếu nào đang mở.
    ky_xem_duoc: list[KyXemDuocOut] = Field(default_factory=list)
    cho_phat: ChoPhatOut | None = None


# --- Danh mục khoản thu nhập (chủ 2026-07-27) --------------------------------


class ComponentIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    kind: str = Field(default="thu", pattern="^(thu|tru)$")
    is_taxable: bool = True
    in_insurance_base: bool = False
    sort_order: int = 0
    note: str | None = Field(default=None, max_length=255)


class ComponentPatchIn(BaseModel):
    """Sửa từng phần — field nào None thì giữ nguyên."""
    name: str | None = Field(default=None, min_length=1, max_length=120)
    kind: str | None = Field(default=None, pattern="^(thu|tru)$")
    is_taxable: bool | None = None
    in_insurance_base: bool | None = None
    sort_order: int | None = None
    is_active: bool | None = None
    note: str | None = Field(default=None, max_length=255)


class ComponentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    name: str
    kind: str
    is_taxable: bool
    in_insurance_base: bool
    sort_order: int
    is_active: bool
    note: str | None = None
    # Router điền — nền cho thông điệp "đã gán cho N nhân viên, đã chốt M kỳ lương".
    employee_count: int = 0
    period_count: int = 0


class ComponentsOut(BaseModel):
    items: list[ComponentOut]


class ComponentHoldersOut(BaseModel):
    """NV còn được gán một khoản ĐÃ NGỪNG ÁP DỤNG — nuôi cảnh báo đỏ. Tiền vẫn được trả bình
    thường; đây chỉ là danh sách để HCNS chủ động gỡ."""
    component_id: int
    component_name: str
    items: list[dict] = []


class ComponentAmountsOut(BaseModel):
    """Ai đang được gán MỘT khoản và mức bao nhiêu — cho modal gán hàng loạt xem trước.

    Khác `ComponentHoldersOut`: bảng kia CHỈ trả người giữ khoản đã NGỪNG ÁP DỤNG (nuôi cảnh
    báo đỏ) và không có số tiền, nên không dùng lại được cho việc này."""

    component_id: int
    items: list[dict] = []


class BulkAssignIn(BaseModel):
    """Rải MỘT khoản cho NHIỀU người (chủ 28/07/2026)."""

    amount: float = Field(ge=0)
    note: str | None = Field(default=None, max_length=255)
    # Chọn cụ thể; bỏ trống + `all_active=True` = tất cả NV ĐANG LÀM VIỆC trong phạm vi.
    employee_ids: list[int] = []
    all_active: bool = False
    # ⚠️ MẶC ĐỊNH False và phải giữ nguyên: bật lên là xoá mức riêng đã khai cho từng người,
    # không có đường hoàn tác. Client quên gửi ⇒ hành vi an toàn (không đè).
    overwrite: bool = False


class BulkAssignOut(BaseModel):
    assigned: int = 0            # thêm mới
    overwritten: int = 0         # ĐÈ mức riêng đã có — tách riêng để banner nói đúng
    skipped_existing: int = 0    # đã có mức riêng, không đè (mặc định)
    skipped_out_of_scope: int = 0
    total: int = 0


class ComponentDeleteOut(BaseModel):
    """Nói rõ việc vừa xảy ra: xoá hẳn hay chỉ ngừng áp dụng. `message` là câu hiển thị nguyên văn
    — màn hình KHÔNG được tự chế lại, tránh báo "đã xoá" khi thực ra chỉ tắt đi."""
    deleted: bool
    deactivated: bool
    employee_count: int = 0
    period_count: int = 0
    message: str = ""


class ComponentValueIn(BaseModel):
    component_id: int
    # None = GỠ khoản khỏi người này (kỳ sau không trả nữa).
    amount: float | None = Field(default=None, ge=0)
    # Ghi chú tự do — cho khoản "Thu nhập khác" lưu vết vì sao có khoản này.
    note: str | None = Field(default=None, max_length=255)


class ComponentValuesIn(BaseModel):
    items: list[ComponentValueIn] = []


class ComponentValueOut(BaseModel):
    component_id: int
    code: str
    name: str
    kind: str
    is_taxable: bool
    amount: float
    note: str | None = None
    # False = khoản đã NGỪNG ÁP DỤNG nhưng NV vẫn đang được gán ⇒ màn hình bật cảnh báo đỏ.
    # Tiền VẪN được trả (chốt của chủ) — cảnh báo để HCNS chủ động gỡ, không tự cắt lương.
    is_active: bool = True


class ComponentValuesOut(BaseModel):
    items: list[ComponentValueOut] = []


# --- Tầng 3: khoản PHÁT SINH trên một dòng lương ----------------------------


class LineComponentIn(BaseModel):
    component_id: int
    amount: float = Field(ge=0)
    note: str | None = Field(default=None, max_length=255)


class LineComponentPatchIn(BaseModel):
    amount: float | None = Field(default=None, ge=0)
    note: str | None = Field(default=None, max_length=255)


class LineComponentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    component_id: int
    code: str
    name: str
    kind: str
    is_taxable: bool
    amount: float
    note: str | None = None
    # `employee` = chép từ hồ sơ NV · `line` = thêm tay cho riêng kỳ này · `auto` = HỆ TỰ TÍNH
    # (hoa hồng KD). Giao diện phải KHOÁ ô của dòng `auto`: backend chặn sửa/gỡ, vì số bám hoá
    # đơn và bị ghi lại mỗi lần "Tính lại".
    source: str
    #: HCNS đã sửa tay số tiền CHO RIÊNG KỲ NÀY. Giao diện hiện nhãn "đã sửa cho kỳ này" + nút
    #: "Trả về theo hồ sơ". Hồ sơ nhân viên KHÔNG đổi — tháng sau tự về mức cũ.
    da_de_tay: bool = False


class LineComponentsOut(BaseModel):
    items: list[LineComponentOut]


# `LineOut` khai `components: list[LineComponentOut]` NHƯNG được định nghĩa phía trên → forward ref
# chưa giải được lúc tạo lớp. Rebuild tường minh ở đây cho lỗi (nếu có) nổ lúc import, không phải
# lúc trả response cho người dùng.
LineOut.model_rebuild()


class KhoanKmChuyenOut(BaseModel):
    """MỘT chuyến giao trong bảng đối chiếu khoán km (mg 0231)."""

    trip_id: int
    ngay: datetime | None = None
    km: int = 0
    don_gia_km: float = 0
    #: `tai_xe` | `phu_xe` — vai trò trong CHUYẾN ĐÓ, không phải chức danh của người.
    vai_tro: str
    #: % được hưởng của chuyến. Đi một mình = 100, không phải `pct_tai_xe`.
    pct: float = 0
    thanh_tien: float = 0


class KhoanKmChiTietOut(BaseModel):
    """Bảng đối chiếu cho HCNS. `tong` PHẢI khớp cột "Khoán km" trên bảng lương — lệch là một
    trong hai bên tính sai, và số nào cũng không tin được nữa."""

    items: list[KhoanKmChuyenOut] = []
    tong: float = 0
