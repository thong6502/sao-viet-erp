"""Payroll (Lương) business logic — lương thời gian.

Engine tính 1 dòng lương/NV/kỳ (xem docs/spec-luong.md + docs/prd-cau-hinh-luong.md):
  mức nền = lương vị trí + trách nhiệm CỦA NV (C1/C2; fallback base_amount → dòng tổ → rule)
  → luong_cong = mức × %thử_việc × (công thực / công chuẩn)     [công lấy từ Chấm công]
  → chuyên cần TRỪ DẦN: tỷ lệ = max(0, 1 − 0,5 × số ngày nghỉ)  [mức khai theo TỔ]
  → 4 khoản phụ cấp KHAI TAY theo NV (ca · trách nhiệm · thâm niên · khác): cộng PHẲNG, không
    prorate theo công, không vào gốc tính tăng ca — hệ thống KHÔNG tự tính khoản nào
  → gross = luong_cong + chuyên cần + phụ cấp + khoán + tăng ca + phụ cấp ca + thưởng − phạt(30%)
  → bhxh = mức_đóng_BH × 10.5% (KHÔNG prorate) ; TNCN lũy tiến (miễn tăng ca + tiền ca)
  → net = gross − bhxh − công đoàn − pit − tổng_tạm_ứng(đã duyệt)
"""
from __future__ import annotations

import secrets
from calendar import monthrange
from datetime import date, datetime, timezone

# Mã tạm ứng: TU-YYMMDD-XXXX (4 ký tự ngẫu nhiên). Bỏ ký tự dễ nhầm (0/O, 1/I) cho dễ đọc tay.
_ADV_CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"

from .attendance_service import _as_utc   # dán nhãn UTC cho mốc SQLite đọc ra naive
from ..models.employee import (
    PIT_CAM_KET_08,
    PIT_KHAU_TRU_10,
    STATUS_PROBATION,
    STATUS_PROBATION_ENDED,
    STATUS_RESIGNED,
)
from ..models.role import SCOPE_ALL
from ..models.payroll import (
    COMPONENT_SOURCE_AUTO,
    COMPONENT_SOURCE_LINE,
    ADV_APPROVED,
    ADV_CANCELLED,
    ADV_KIND_LUONG_DOT_1,
    ADV_KIND_TAM_UNG,
    ADV_PENDING,
    ADV_REJECTED,
    AMOUNT_DEPT_ROW,
    AMOUNT_MANUAL,
    AMOUNT_RULE,
    BAND_GT10,
    BAND_LT1,
    BAND_Y1_5,
    BAND_Y5_10,
    COMP_CHUYEN_CAN,
    COMP_LUONG_KHOAN,
    COMP_TANG_CA,
    PERIOD_DRAFT,
    PERIOD_LOCKED,
    PERIOD_PAID,
    SALARY_COMPONENT_KEYS,
)


class PayrollError(Exception):
    """Base cho lỗi nghiệp vụ lương."""


class PayrollValidationError(PayrollError):
    pass


class PayrollNotFound(PayrollError):
    pass


class PayrollForbidden(PayrollError):
    """Thao tác nằm ngoài phạm vi dữ liệu của người gọi (403)."""


class PayrollLocked(PayrollError):
    """Kỳ lương đã chốt — không sửa được."""


def _round(x) -> float:
    """Làm tròn về đồng (VND không có phần lẻ)."""
    return float(round(float(x or 0)))


def _seniority_band(hire_date: date | None, on: date) -> str | None:
    if hire_date is None:
        return None
    years = (on - hire_date).days / 365.25
    if years < 1:
        return BAND_LT1
    if years < 5:
        return BAND_Y1_5
    if years < 10:
        return BAND_Y5_10
    return BAND_GT10


# Biểu thuế TNCN mặc định 2026 — (seq, trần thu nhập tính thuế/tháng, suất). Trùng seed_pit_brackets;
# dùng khi bảng trống (fallback). None = bậc cao nhất (∞).
_DEFAULT_PIT_BRACKETS = [
    (1, 10_000_000, 0.05), (2, 30_000_000, 0.10), (3, 60_000_000, 0.20),
    (4, 100_000_000, 0.30), (5, None, 0.35),
]

# Bảng phạt đi trễ / về sớm mặc định (PRD §4/D11) — (seq, trần PHÚT, tiền phạt/lần).
# Dùng khi bảng trống (auto-seed). None = bậc cao nhất (∞): trên 1 giờ.
_DEFAULT_LATE_PENALTY_BRACKETS = [
    (1, 15, 20_000), (2, 30, 40_000), (3, 60, 100_000), (4, None, 150_000),
]


# LƯỚI DỰ PHÒNG cho `payroll_params.bhxh_mien_tu_so_ngay` — chỉ dùng khi bản ghi params cũ chưa có
# cột (cùng idiom `getattr(params, "phat_cap_pct", 0.30)`). Số thật khai ở màn Cấu hình lương:
# luật đổi thì gõ lại, KHÔNG sửa code. Xem QĐ 595/QĐ-BHXH Đ42.4.
BHXH_MIEN_TU_SO_NGAY_MAC_DINH = 14

#: Từ tháng này trở đi mới đòi CHỐT CÔNG trước khi chốt lương (chủ chốt 12/08/2026).
#:
#: Vì sao có mốc chứ không áp cho mọi tháng: hệ thống đang chạy có những tháng ĐÃ CHỐT / ĐÃ CHI
#: lương mà chưa hề tồn tại dòng kỳ công (kỳ công chỉ sinh khi có người đụng vào tháng đó). Áp
#: ngược lại quá khứ thì ai mở lại một kỳ lương cũ để sửa sẽ KHÔNG CHỐT LẠI ĐƯỢC — muốn chốt công
#: tháng đó phải đi duyệt sạch đơn treo từ đời nào, có khi của người đã nghỉ việc.
#:
#: Đổi mốc = đổi đúng dòng này. Đừng gỡ hẳn điều kiện: gỡ là mất luôn hàng rào cho tháng mới.
AP_DUNG_CHOT_CONG_TRUOC_TU = (2026, 8)


def _chuyen_can_ratio(actual_cong, standard_cong) -> float:
    """Tỷ lệ chuyên cần TRỪ DẦN (PRD C3, khớp bảng lương thật):
    `số ngày nghỉ = max(0, công chuẩn − công thực)` · `tỷ lệ = max(0, 1 − 0,5 × số ngày nghỉ)`.
    Vd công chuẩn 26: 26 công → 100% · 25,5 → 75% · 25 → 50% · ≤24 → 0%."""
    days_off = max(0.0, float(standard_cong or 0) - float(actual_cong or 0))
    return max(0.0, 1.0 - 0.5 * days_off)


def _luong_cong_split(*, eff_monthly: float, std: float,
                      actual_cong: float, paid_leave_cong: float,
                      special_cong: float = 0.0) -> tuple[float, float, float]:
    """Tách tiền theo công thành (TỔNG, phần NGÀY PHÉP, số công phép được trả).

    ⚠️ **ĐẢO 17/08/2026 — ngày nghỉ phép năm nay trả ĐỦ MỨC NỀN** (cơ bản + trách nhiệm), bỏ chốt
    cũ 27/07/2026 "chỉ lương vị trí". Chủ chốt: *"tiền công 1 ngày là lương cơ bản cộng lương
    trách nhiệm"* — nghỉ phép năm là ngày nghỉ CÓ LƯƠNG (Đ113 hưởng nguyên lương) nên phải theo
    đúng luật đó, giống ngày lễ và ngày off1x. Trước bản vá mỗi ngày phép hụt đúng phần trách
    nhiệm chia cho công chuẩn.

    `luong_ngay_phep` nay CÙNG đơn giá với công đi làm — giữ tách riêng chỉ để phiếu lương giải
    thích được "trong lương công có bao nhiêu là ngày phép", KHÔNG còn khác đơn giá.

    Cách chia: **công LÀM lấp trần trước, công PHÉP lấy phần dư** —
    nhờ vậy người làm dôi công (đi làm ngày lễ/CN, `actual_cong > std`) KHÔNG bị trừ hai lần:
    trần đã cắt bớt công của họ rồi, trừ tiếp phần trách nhiệm của ngày phép là phạt lần nữa.

    ⚠️ **`special_cong` (công ngày LỄ / NGHỈ TUẦN có đi làm) KHÔNG đi qua trần** — sửa 17/08/2026.
    Trước đó nó nằm chung rổ bị `min(worked, std)` cắt: ai đã đủ công chuẩn rồi mới làm Chủ nhật thì
    phần gốc 1× bị nuốt, `ot_pay` chỉ bù `(hệ số − 1)` ⇒ thực nhận **1× thay vì 2×** (lễ: 2× thay vì
    3×) — trái Đ98.1.b/c. Ai CHƯA chạm trần thì số không đổi một đồng (đã đối chiếu 4 kịch bản).
    Phần gốc vẫn ăn **đơn giá MỨC NỀN**; chỉ phần premium ở `ot_pay` mới ăn đơn giá lương vị trí
    (chốt 12/08/2026) — đừng gộp hai đơn giá làm một.

    `luong_ngay_phep` là số **TRONG ĐÓ** của `luong_cong` — ĐỪNG cộng nó vào gross lần nữa
    (cùng idiom với `phu_cap_tham_nien ⊂ allowance`).

    Dùng CHUNG cho `_compute` ("Tính lại") và `update_line` ("Sửa 1 ô") — hai đường tính lệch
    nhau là bệnh đã tái phát nhiều lần ở file này.
    """
    std = float(std) or 1.0
    actual = max(0.0, float(actual_cong))
    # Công NGÀY LỄ / NGHỈ TUẦN có đi làm: KHÔNG đi qua trần (xem docstring). Kẹp trong `actual`
    # để dữ liệu lệch không đẻ ra tiền âm/ảo.
    special = max(0.0, min(float(special_cong), actual))
    leave = max(0.0, min(float(paid_leave_cong), max(0.0, actual - special)))
    worked = max(0.0, actual - special - leave)          # chỉ công NGÀY THƯỜNG mới bị trần
    paid_worked = min(worked, std)
    paid_leave_eff = min(leave, max(0.0, std - paid_worked))
    luong_ngay_phep = (float(eff_monthly) / std) * paid_leave_eff
    # `special` cộng NGOÀI trần, vẫn ăn đơn giá MỨC NỀN (vị trí + trách nhiệm) — KHÔNG hạ xuống
    # đơn giá lương vị trí như phần premium, nếu không người có tiền trách nhiệm bị cắt lương.
    luong_cong = (float(eff_monthly) / std) * (paid_worked + special) + luong_ngay_phep
    return luong_cong, luong_ngay_phep, paid_leave_eff


def _capped_penalty(*, gross_pre, bhxh, pit, phat_total, khoan_defect=0.0,
                    cap_pct=0.30) -> float:
    """Trần khấu trừ BỒI THƯỜNG/KỶ LUẬT trên lương tháng SAU khi trích BHXH + TNCN, GỘP cả trừ
    lỗi khoán. Phần vượt KHÔNG trừ kỳ này.

    `cap_pct` = `payroll_params.phat_cap_pct` (chủ 29/07/2026 — "bỏ cái 30% fix cứng trong
    code"). Mặc định 0.30 là **mức LUẬT** (Điều 102 BLLĐ 2019), không phải chính sách công ty.

    ⚠️ `cap_pct <= 0` = **TẮT TRẦN**: ghi phạt bao nhiêu trừ bấy nhiêu. Cố ý cho phép — chủ tự
    quyết và tự chịu rủi ro pháp lý; màn Cấu hình lương có cảnh báo. Thực nhận vẫn có sàn 0.

    Dùng CHUNG cho `_compute` ("Tính lại") và `update_line` ("Sửa 1 ô") — trước đây hai
    đường tính lệch nhau (update_line quên trừ `khoan_defect`) nên sửa 1 ô ra số khác."""
    if cap_pct is None or float(cap_pct) <= 0:
        return float(phat_total)
    base_102 = max(0.0, float(gross_pre) - float(bhxh) - float(pit))
    room = max(0.0, float(cap_pct) * base_102 - float(khoan_defect or 0))
    return min(float(phat_total), room)


def _pit_amount(taxable, brackets) -> float:
    """Thuế TNCN lũy tiến TỪNG PHẦN trên thu nhập TÍNH THUẾ/tháng, theo biểu `brackets`
    (đã sắp theo seq; `up_to` None = bậc cao nhất ∞)."""
    t = max(0.0, float(taxable or 0))
    tax = 0.0
    lower = 0.0
    for b in brackets:
        upper = float(b.up_to) if b.up_to is not None else float("inf")
        if t <= lower:
            break
        tax += (min(t, upper) - lower) * float(b.rate)
        lower = upper
    return tax


def _late_penalty_amount(minutes, brackets) -> float:
    """Tiền phạt đi trễ/về sớm cho MỘT lần vi phạm `minutes` phút, theo bảng `brackets`
    (đã sắp theo seq; `up_to_minute` None = bậc cao nhất ∞) — mirror logic ô "Tính nhanh" ở FE:
    chọn bậc ĐẦU có `up_to_minute >= minutes`, hết bậc thì lấy bậc cuối."""
    m = int(minutes or 0)
    if m <= 0 or not brackets:
        return 0.0
    for b in brackets:
        if b.up_to_minute is None or m <= int(b.up_to_minute):
            return float(b.amount)
    return float(brackets[-1].amount)


class PayrollService:
    def __init__(self, payroll, employees, attendance, audit=None, piece=None,
                 departments=None, components=None, vouchers=None) -> None:
        self.payroll = payroll
        self.employees = employees
        self.attendance = attendance   # AttendanceService — nguồn số CÔNG
        self.piece = piece             # PieceWorkService — nguồn tiền KHOÁN (nhịp 2)
        self.audit = audit
        # DepartmentRepository | None — chỉ để đọc cờ `has_piece_work`: tổ khoán KHÔNG tính
        # tăng ca theo giờ (khoán đã trả theo sản lượng).
        self.departments = departments
        # PayrollComponentRepository | None — danh mục khoản thu nhập (cờ chịu thuế TNCN).
        # None (unit test dựng tay) ⇒ không có khoản nào, số ra y như trước khi có danh mục.
        self.components = components
        # AccountingRepository | None — CHỈ ĐỌC, chỉ để hỏi "phiếu tạm ứng này đã lập phiếu chi
        # chưa" trước khi cho huỷ (chủ chốt 18/08/2026). None (unit test dựng tay) ⇒ bỏ qua chốt,
        # hành vi y như trước.
        self._vouchers = vouchers
        # Cache thành phần lương theo bộ phận trong 1 request: `generate` gọi engine cho hàng
        # trăm NV. Ghi cấu hình → `_reset_config_cache`.
        self._comp_cache: dict[int, dict] = {}

    # --- params -------------------------------------------------------------

    def get_params(self):
        """Tham số lương — tự tạo 1 dòng mặc định nếu chưa có."""
        p = self.payroll.get_params()
        if p is None:
            p = self.payroll.create_params()
        return p

    def _audit(self, actor, action: str, target: str, detail: str) -> None:
        """Ghi nhật ký thao tác lương (None-guard: test unit dựng service không audit → bỏ qua).
        KHÔNG đưa số tiền lương vào detail (nhạy cảm, hiện ở Nhật ký chung)."""
        if self.audit is not None:
            self.audit.create(actor_user_id=getattr(actor, "id", None), action=action,
                              target=target, detail=detail)

    def update_params(self, **fields):
        p = self.get_params()
        allowed = {
            "standard_cong_default", "probation_ratio", "bhxh_rate", "bhyt_rate",
            "bhtn_rate", "bhxh_rate_er", "bhyt_rate_er", "bhtn_rate_er",
            "deduction_self", "deduction_dependent", "chuyen_can_default",
            "standard_hours_per_day", "ot_multiplier", "ot_multiplier_restday",
            "ot_multiplier_holiday", "restday_work_multiplier", "holiday_work_multiplier",
            "night_pct", "bh_base_cap", "bhtn_base_cap", "cong_doan_rate",
            "tnld_bnn_rate", "ot_night_extra_pct", "adjust_max_per_month",
            "pit_flat_rate", "pit_flat_threshold", "phat_cap_pct",
            # ⚠️ Tên nào KHÔNG có trong rổ này thì PUT chạy ngon lành mà số không hề đổi — thêm
            # cột mà quên khai ở đây là dựng ra một ô cấu hình giả. `phu_cap_ca_min_cong` thêm từ
            # 03/08/2026 đã bị sót đúng kiểu đó, tuy tài liệu ghi là "khai được".
            "phu_cap_ca_min_cong", "bhxh_mien_tu_so_ngay",
            # Trần giờ làm thêm Đ107 (17/08/2026) — sót ở rổ này là ô cấu hình GIẢ.
            "ot_max_minutes_per_month", "ot_max_minutes_per_day",
            "com_tang_ca_nguong_phut", "com_tang_ca_muc",
        }
        data = {k: v for k, v in fields.items() if k in allowed and v is not None}
        data["updated_at"] = datetime.now(timezone.utc)
        saved = self.payroll.update_params(p, **data)
        self._reset_config_cache()
        return saved

    # --- cấu hình lương: thành phần theo BỘ PHẬN ----------------------------

    def _reset_config_cache(self) -> None:
        self._comp_cache = {}

    def _dept_comp_map(self, department_id) -> dict:
        if department_id is None:
            return {}
        cached = self._comp_cache.get(department_id)
        if cached is None:
            cached = {c.component_key: c for c in self.payroll.list_dept_components(department_id)}
            self._comp_cache[department_id] = cached
        return cached

    def _default_component_enabled(self, key: str, department_id) -> bool:
        """Mặc định khi bộ phận CHƯA khai dòng nào. `luong_khoan` soi cờ sẵn có
        `departments.has_piece_work` (chỉ phơi lại cờ, không dựng nguồn thứ 2)."""
        if key == COMP_LUONG_KHOAN:
            if self.departments is None or department_id is None:
                return False
            dept = self.departments.get_by_id(department_id)
            return bool(getattr(dept, "has_piece_work", False))
        return True

    def _effective_component(self, key: str, *, department_id=None, emp_value=None,
                             fallback=None):
        """Mức hiệu lực của MỘT khoản theo chuỗi ghi đè **2 cấp: NV → TỔ** (danh mục phụ cấp
        cấp công ty đã gỡ — nó không điều khiển gì nữa).

        Trả `None` khi TỔ TẮT khoản đó (tắt ở tổ thì cấp NV cũng không được cộng). `fallback` cho
        khoản còn tham số cấp công ty theo thói quen của chủ (chuyên cần —
        `payroll_params.chuyen_can_default`).

        (Cờ `require_dept_row` đã gỡ 29/07/2026 cùng thưởng KPI — KPI là khoản DUY NHẤT dùng nó.)"""
        comp = self._dept_comp_map(department_id).get(key)
        if comp is not None and not comp.is_enabled:
            return None
        if emp_value is not None:
            return float(emp_value)
        if comp is not None and comp.value is not None:
            return float(comp.value)
        return fallback

    def _component_enabled(self, key: str, department_id=None) -> bool:
        """Bật/tắt thuần (không kèm giá trị) — vd tăng ca, lương khoán, lương theo bậc."""
        comp = self._dept_comp_map(department_id).get(key)
        if comp is None:
            return self._default_component_enabled(key, department_id)
        return bool(comp.is_enabled)

    def dept_components(self, department_id: int) -> list[dict]:
        """Cấu hình thành phần lương của 1 bộ phận — LUÔN trả đủ các khoản CÒN khai theo TỔ
        (chuyên cần · lương khoán · tăng ca). Phụ cấp ca/trách nhiệm/thâm niên đã chuyển sang
        KHAI TAY theo từng NV; thưởng KPI đã gỡ hẳn 29/07/2026 — nên cả hai không còn ở đây."""
        comps = self._dept_comp_map(department_id)
        out: list[dict] = []
        for key in SALARY_COMPONENT_KEYS:
            c = comps.get(key)
            out.append({
                "component_key": key,
                "is_enabled": bool(c.is_enabled) if c is not None
                else self._default_component_enabled(key, department_id),
                "value": float(c.value) if (c is not None and c.value is not None) else None,
                "is_set": c is not None,
            })
        return out

    def set_dept_components(self, *, department_id: int, items, actor=None) -> list[dict]:
        """Ghi cấu hình thành phần lương của 1 bộ phận (upsert theo `component_key`)."""
        if self.departments is not None and self.departments.get_by_id(department_id) is None:
            raise PayrollNotFound("Không tìm thấy phòng ban.")
        items = list(items or [])
        # ⚠️ GỠ 17/08/2026 — trước đây Khoán ⟷ Tăng ca LOẠI TRỪ nhau (bật khoán thì tự tắt tăng
        # ca, chốt 22/07/2026). Chủ ĐẢO lại: "Tổ khoán VẪN CÓ tăng ca". Hai công tắc nay ĐỘC LẬP.
        # Đừng dựng lại luật loại trừ ở đây — engine cũng đã gỡ vế `has_piece_work` khỏi `ot_pay`.
        for it in items:
            key = it.get("component_key")
            if key not in SALARY_COMPONENT_KEYS:
                raise PayrollValidationError(f"Thành phần lương không hợp lệ: {key}")
            enabled = bool(it.get("is_enabled", True))
            self.payroll.upsert_dept_component(
                department_id=department_id, component_key=key, is_enabled=enabled,
                value=it.get("value"), updated_at=datetime.now(timezone.utc),
            )
            # `luong_khoan` chỉ phơi lại cờ `departments.has_piece_work` → ghi thẳng về cờ đó,
            # tránh 2 nguồn sự thật (tiền khoán đang TẠM GÁC, không đụng phần tính tiền).
            if key == COMP_LUONG_KHOAN and self.departments is not None:
                dept = self.departments.get_by_id(department_id)
                if dept is not None and bool(dept.has_piece_work) != enabled:
                    self.departments.set_salary_policy(
                        dept, salary_mechanism=dept.salary_mechanism,
                        probation_ratio=dept.probation_ratio, has_piece_work=enabled,
                    )
        self._reset_config_cache()
        self._audit(actor, "payroll_set_dept_components", f"department:{department_id}",
                    f"{len(items)} thành phần")
        return self.dept_components(department_id)

    # --- salary_rate_rules --------------------------------------------------

    def list_rules(self):
        return self.payroll.list_rules()

    def create_rule(self, **fields):
        if not fields.get("payroll_group"):
            raise PayrollValidationError("Thiếu nhóm lương.")
        if fields.get("monthly_amount") is None:
            raise PayrollValidationError("Thiếu mức lương.")
        return self.payroll.create_rule(**fields)

    def update_rule(self, rule_id: int, **fields):
        r = self.payroll.get_rule(rule_id)
        if r is None:
            raise PayrollNotFound("Không tìm thấy quy tắc lương.")
        return self.payroll.update_rule(r, **{k: v for k, v in fields.items() if v is not None})

    def delete_rule(self, rule_id: int) -> None:
        r = self.payroll.get_rule(rule_id)
        if r is None:
            raise PayrollNotFound("Không tìm thấy quy tắc lương.")
        self.payroll.delete_rule(r)

    # --- biểu thuế TNCN (sửa được) ------------------------------------------

    def get_pit_brackets(self):
        """Biểu thuế TNCN — tự tạo mặc định 2026 nếu bảng trống."""
        bks = self.payroll.list_pit_brackets()
        if not bks:
            for seq, up_to, rate in _DEFAULT_PIT_BRACKETS:
                self.payroll.create_pit_bracket(seq=seq, up_to=up_to, rate=rate)
            bks = self.payroll.list_pit_brackets()
        return bks

    def create_pit_bracket(self, *, seq, up_to, rate):
        if rate is None or float(rate) < 0:
            raise PayrollValidationError("Thuế suất không hợp lệ.")
        return self.payroll.create_pit_bracket(seq=int(seq), up_to=up_to, rate=rate)

    def update_pit_bracket(self, bracket_id: int, *, seq, up_to, rate):
        b = self.payroll.get_pit_bracket(bracket_id)
        if b is None:
            raise PayrollNotFound("Không tìm thấy bậc thuế.")
        return self.payroll.update_pit_bracket(b, seq=int(seq), up_to=up_to, rate=rate)

    def delete_pit_bracket(self, bracket_id: int) -> None:
        b = self.payroll.get_pit_bracket(bracket_id)
        if b is None:
            raise PayrollNotFound("Không tìm thấy bậc thuế.")
        self.payroll.delete_pit_bracket(b)

    # --- bảng phạt đi trễ / về sớm (sửa được) -------------------------------

    def get_late_penalty_brackets(self):
        """Bảng phạt trễ/sớm — tự tạo 4 bậc mặc định nếu bảng trống (như biểu TNCN)."""
        bks = self.payroll.list_late_penalty_brackets()
        if not bks:
            for seq, up_to_minute, amount in _DEFAULT_LATE_PENALTY_BRACKETS:
                self.payroll.create_late_penalty_bracket(
                    seq=seq, up_to_minute=up_to_minute, amount=amount)
            bks = self.payroll.list_late_penalty_brackets()
        return bks

    def create_late_penalty_bracket(self, *, seq, up_to_minute, amount):
        if amount is None or float(amount) < 0:
            raise PayrollValidationError("Số tiền phạt không hợp lệ.")
        return self.payroll.create_late_penalty_bracket(
            seq=int(seq), up_to_minute=up_to_minute, amount=amount)

    def update_late_penalty_bracket(self, bracket_id: int, *, seq, up_to_minute, amount):
        b = self.payroll.get_late_penalty_bracket(bracket_id)
        if b is None:
            raise PayrollNotFound("Không tìm thấy bậc phạt.")
        return self.payroll.update_late_penalty_bracket(
            b, seq=int(seq), up_to_minute=up_to_minute, amount=amount)

    def delete_late_penalty_bracket(self, bracket_id: int) -> None:
        b = self.payroll.get_late_penalty_bracket(bracket_id)
        if b is None:
            raise PayrollNotFound("Không tìm thấy bậc phạt.")
        self.payroll.delete_late_penalty_bracket(b)

    def _auto_pit(self, *, gross, bhxh, ot_pay, night_pay, dependents_count, params, brackets,
                  night_premium_pay=0.0, component_exempt=0.0, apply_self_deduction=True,
                  pit_mode=None, cong_doan=0.0, ot_taxable=0.0):
        """Trả (thu nhập CHỊU thuế, thu nhập TÍNH thuế, thuế TNCN). Miễn TOÀN BỘ tiền tăng ca + ca đêm — gồm cả premium ca đêm
        theo giờ (`night_premium_pay`, Luật 109/2025); trừ BHXH + giảm trừ bản thân + người phụ thuộc.

        `component_exempt` = Σ các khoản DANH MỤC có `is_taxable = false` (trang phục, tiền nhà,
        đi lại, tiền cơm…). Trước đây mọi phụ cấp bị gộp vào một ô nên không tách được, thuế thu
        thừa của người có phụ cấp."""
        # `ot_taxable` = phần NẰM TRONG `ot_pay` nhưng KHÔNG được miễn ⇒ cộng ngược lại.
        # Hiện dùng cho TIỀN NGÀY off1x (kế toán chốt 17/08/2026: "lương thuế chỉ 1 công bình
        # thường") — nó trả 1×, KHÔNG hệ số, nên không có phần "trả cao hơn" nào để miễn.
        # Mặc định 0.0 ⇒ mọi caller cũ chạy y nguyên.
        assessable = (float(gross) - (float(ot_pay) - float(ot_taxable)) - float(night_pay)
                      - float(night_premium_pay) - float(component_exempt))

        # --- Nhánh HĐ DƯỚI 3 THÁNG / thời vụ / thực tập (chủ 2026-07-27) --------------------
        # Khấu trừ 10% TẠI NGUỒN trên thu nhập chịu thuế, KHÔNG bảng luỹ tiến, KHÔNG giảm trừ gia
        # cảnh. Có cam kết 08/CK-TNCN thì không khấu trừ. Đặt TRƯỚC phần luỹ tiến và return sớm để
        # tuyệt đối không đụng công thức cũ.
        if pit_mode == PIT_CAM_KET_08:
            return max(0.0, assessable), 0.0, 0.0
        if pit_mode == PIT_KHAU_TRU_10:
            rate = float(getattr(params, "pit_flat_rate", 0.10) or 0)
            floor = float(getattr(params, "pit_flat_threshold", 0) or 0)
            base = max(0.0, assessable)
            # Dưới ngưỡng/lần trả thì chưa phải khấu trừ.
            pit = _round(base * rate) if base >= floor else 0.0
            # `pit_taxable` ở nhánh này = chính thu nhập chịu thuế (không có giảm trừ nào).
            return base, base, pit
        # Giảm trừ BẢN THÂN chỉ được đăng ký ở MỘT nơi làm việc ⇒ tắt được theo từng người.
        # Giảm trừ NGƯỜI PHỤ THUỘC không phụ thuộc cờ này.
        deduction = (float(params.deduction_self) if apply_self_deduction else 0.0)
        deduction += float(params.deduction_dependent) * int(dependents_count or 0)
        # ĐOÀN PHÍ GIẢM THU NHẬP TÍNH THUẾ (chủ chốt 12/08/2026) — theo đúng bảng lương công ty
        # đang dùng: khối "Các khoản giảm trừ" gồm bản thân + NPT + BH bắt buộc + ĐOÀN PHÍ, và cột
        # "Thu nhập tính thuế" = chịu thuế − đúng khối đó (đã dò lại số trên bảng tháng 5/2026).
        # Ghi để khỏi bàn lại: TT 111/2013 Đ9 KHÔNG liệt đoàn phí vào danh sách giảm trừ. Đây là
        # cố ý làm theo cách công ty hạch toán, không phải nhầm.
        taxable = max(0.0, assessable - float(bhxh) - float(cong_doan or 0) - deduction)
        # CHỊU thuế (trước giảm trừ) và TÍNH thuế (sau giảm trừ) là HAI số khác nhau — chủ hỏi
        # "tổng mức lương chịu thuế" là số đầu.
        return max(0.0, assessable), taxable, _round(_pit_amount(taxable, brackets))

    def _apply_auto_pit(self, ln) -> None:
        """Tính lại TNCN tự động cho 1 dòng (theo gross/bhxh/OT/đêm hiện tại + người phụ thuộc).

        Phần MIỄN thuế của các khoản danh mục lấy từ SNAPSHOT `thu_nhap_mien_thue` trên chính dòng
        đó, trừ đi phần OT/đêm — không đọc lại danh mục sống. Nhờ vậy "Sửa 1 ô" ra đúng số của
        "Tính lại", và sửa dòng của kỳ CŨ không bị cờ chịu thuế hôm nay làm lệch."""
        emp = self.employees.get_by_id(ln.employee_id)
        sal = self.payroll.current_salary(ln.employee_id, date.today())
        # Tiền off1x nằm trong `ot_pay` nhưng KHÔNG nằm trong `thu_nhap_mien_thue` (nó chịu thuế),
        # nên phải trừ ra trước khi suy ngược phần miễn của danh mục — thiếu vế này là comp_exempt
        # bị hụt đúng bằng off1x và "Sửa 1 ô" tính thuế cao hơn "Tính lại".
        off1x = float(getattr(ln, "off1x_pay", 0) or 0)
        ot = (float(ln.ot_pay or 0) - off1x + float(ln.night_pay or 0)
              + float(getattr(ln, "night_premium_pay", 0) or 0))
        comp_exempt = max(0.0, float(getattr(ln, "thu_nhap_mien_thue", 0) or 0) - ot)
        _assess, tx, pit = self._auto_pit(
            gross=ln.gross, bhxh=ln.bhxh, ot_pay=ln.ot_pay, night_pay=ln.night_pay,
            night_premium_pay=getattr(ln, "night_premium_pay", 0) or 0,
            component_exempt=comp_exempt,
            apply_self_deduction=bool(getattr(sal, "apply_self_deduction", True)) if sal else True,
            pit_mode=getattr(emp, "pit_mode", None),
            dependents_count=getattr(emp, "dependents_count", 0),
            params=self.get_params(), brackets=self.get_pit_brackets(),
            # ⚠️ Đọc `ln.cong_doan` ĐANG CÓ TRÊN DÒNG. `update_line` phải tính lại đoàn phí TRƯỚC
            # khi gọi hàm này — trước 12/08/2026 nó tính SAU, vô hại vì thuế chưa dùng tới. Nay
            # dùng rồi: sai thứ tự là thuế ăn số đoàn phí CŨ, và "Sửa 1 ô" lệch "Tính lại".
            cong_doan=float(getattr(ln, "cong_doan", 0) or 0),
            ot_taxable=off1x,
        )
        ln.pit = pit
        ln.pit_taxable = tx

    def _components_for(self, employee) -> list[dict]:
        """Khoản danh mục ĐANG DÙNG của 1 NV = mặc định nhóm lương, đè bởi mức riêng của người.

        Cùng một hàm nuôi cả engine lẫn màn hồ sơ ⇒ số trên màn và số ra tiền không lệch nhau."""
        if self.components is None:
            return []
        by_id = {c.id: c for c in self.components.list_components()}
        out: list[dict] = []
        for row in self.components.employee_rows(employee.id):
            c = by_id.get(row.component_id)
            # KHÔNG lọc `is_active`: khoản đã ngừng áp dụng mà NV còn giữ thì VẪN TRẢ (chốt của
            # chủ 27/07) — chỉ cảnh báo trên màn, không tự ý cắt lương ai.
            if c is None or not row.amount:
                continue
            out.append({"component_id": c.id, "code": c.code, "name": c.name, "kind": c.kind,
                        "is_taxable": bool(c.is_taxable), "amount": float(row.amount),
                        "note": row.note})
        return out

    def _hoa_hong_rows(self, employee_id: int, year: int, month: int) -> list[dict]:
        """Dòng khoản HOA HỒNG KD của kỳ — hệ TỰ TÍNH, không ai gõ (nguồn `auto`).

        Trả `[]` khi không có tiền: đừng đẻ dòng 0 đồng trên phiếu lương của cả trăm người không
        làm kinh doanh.

        Cờ `is_taxable` lấy từ DANH MỤC chứ không đóng đinh ở đây — đó đúng là lý do khoản thưởng
        bị bắt đi qua danh mục từ 28/07/2026 (xem `LineUpdateIn`): cờ chịu thuế phải là một quy
        tắc khai được, không phải hằng số nằm trong engine.
        """
        if self.components is None:
            return []
        from calendar import monthrange

        from ..models.payroll import COMPONENT_CODE_HOA_HONG
        from .hoa_hong_service import HoaHongService

        kh = self.components.get_by_code(COMPONENT_CODE_HOA_HONG)
        if kh is None or not bool(getattr(kh, "is_active", True)):
            return []                       # chưa khai khoản ⇒ chưa bật tính năng

        tien = HoaHongService(self.components.db).hoa_hong_ky(
            employee_id,
            tu_ngay=date(int(year), int(month), 1),
            den_ngay=date(int(year), int(month), monthrange(int(year), int(month))[1]),
        )
        if tien <= 0:
            return []
        return [{
            "component_id": kh.id, "code": kh.code, "name": kh.name, "kind": kh.kind,
            "is_taxable": bool(kh.is_taxable), "amount": float(tien), "note": None,
        }]

    def _line_extra_components(self, line_id: int | None) -> list[dict]:
        """Khoản PHÁT SINH thêm tay cho riêng kỳ này (thưởng nóng) — Tầng 3.

        Đọc từ snapshot chứ không từ hồ sơ: nó vốn không thuộc về hồ sơ, và phải KHÔNG lặp sang
        kỳ sau."""
        if self.components is None or not line_id:
            return []
        return [
            {"component_id": r.component_id, "code": r.code, "name": r.name, "kind": r.kind,
             "is_taxable": bool(r.is_taxable), "amount": float(r.amount), "note": r.note}
            for r in self.components.line_components(line_id, source=COMPONENT_SOURCE_LINE)
        ]

    def _lookup_rule(self, *, payroll_group, pay_grade_key, seniority_band, gender, on: date):
        """Tra mức lương chuẩn: khớp cụ thể nhất trong các rule cùng nhóm, active,
        effective_from ≤ on. Chiều NULL của rule = wildcard; chiều non-null phải khớp."""
        if not payroll_group:
            return None
        best = None
        best_key = None
        for r in self.payroll.list_rules(active_only=True):
            if r.payroll_group != payroll_group:
                continue
            if r.effective_from is not None and r.effective_from > on:
                continue
            score = 0
            ok = True
            for rule_val, emp_val in (
                (r.pay_grade_key, pay_grade_key),
                (r.seniority_band, seniority_band),
                (r.gender, gender),
            ):
                if rule_val is not None:
                    if rule_val != emp_val:
                        ok = False
                        break
                    score += 1
            if not ok:
                continue
            # cụ thể hơn thắng; hòa thì effective_from mới hơn.
            eff = r.effective_from or date.min
            key = (score, eff, r.id)
            if best_key is None or key > best_key:
                best, best_key = r, key
        return best

    def _employment_context_on(self, employee, on: date) -> tuple[str, int | None]:
        """Resolve status and department as they were on a historical date.

        Employee columns hold today's values. Transition events let payroll
        walk future changes backwards without rewriting closed old periods.
        """
        status = employee.status
        department_id = getattr(employee, "department_id", None)
        for event in self.employees.list_events(employee.id):
            if event.effective_date is None or event.effective_date <= on:
                continue
            if event.field == "status" and event.from_value:
                status = event.from_value
            elif event.field == "department":
                department_id = int(event.from_value) if event.from_value else None
        return status, department_id

    def _effective_chuyen_can(self, employee, salary, params,
                              department_id: int | None = None) -> float:
        """Chuyên cần (chủ chốt 2026-07-23): TIỀN chỉ có MỘT nơi khai = hồ sơ NV
        (`employee_salaries.chuyen_can`). Tổ CHỈ CÒN CÔNG TẮC bật/tắt — tắt ở tổ thì không cộng
        dù NV đã khai riêng.

        Đã BỎ mức tiền cấp tổ và mức mặc định cấp công ty (`payroll_params.chuyen_can_default`
        thành dormant): trước đây bật ở tổ mà bỏ trống ô tiền thì màn hình báo 0đ nhưng engine
        vẫn trả 300k — số trên màn lệch tiền thật. Nay chưa khai ở hồ sơ = 0đ, đúng như hiển thị."""
        dept = (getattr(employee, "department_id", None)
                if department_id is None else department_id)
        if not self._component_enabled(COMP_CHUYEN_CAN, dept):
            return 0.0
        return float(getattr(salary, "chuyen_can", 0) or 0) if salary is not None else 0.0

    def _resolve_salary(self, employee, salary, params, on: date,
                        department_id: int | None = None) -> dict:
        """Ra {monthly, chuyen_can_amt, source} cho 1 NV tại kỳ. Chuyên cần LUÔN theo chuỗi
        NV → tổ → công ty (xem trên); `monthly` xem `_resolve_monthly`."""
        res = self._resolve_monthly(employee, salary, params, on)
        res["chuyen_can_amt"] = self._effective_chuyen_can(
            employee, salary, params, department_id=department_id
        )
        return res

    def _resolve_monthly(self, employee, salary, params, on: date) -> dict:
        """MỨC lương tháng nền {monthly, source} — gốc prorate theo công và gốc tính tăng ca.

        Chủ chốt 2026-07-20: mức nền có ĐÚNG 1 nguồn = `luong_vi_tri + luong_trach_nhiem` của NV
        (gõ tay từng ô). Bỏ hẳn nhánh bậc/quy tắc. `base_amount` giữ làm fallback DORMANT cho vài
        bản ghi cũ chỉ khai 1 số tổng — đừng để ai ra 0đ vì đổi cách khai."""
        emp_vt = float(getattr(salary, "luong_vi_tri", 0) or 0) if salary is not None else 0.0
        emp_tn = float(getattr(salary, "luong_trach_nhiem", 0) or 0) if salary is not None else 0.0
        if emp_vt + emp_tn > 0:
            return {"monthly": emp_vt + emp_tn, "source": "employee"}
        # Fallback dữ liệu cũ: 1 số tổng nhập tay (KHÔNG là mức đóng BH — BH bám luong_vi_tri).
        if salary is not None and getattr(salary, "base_amount", None) is not None:
            return {"monthly": float(salary.base_amount), "source": "manual"}
        return {"monthly": 0.0, "source": "none"}

    # --- employee_salaries (khai báo / điều chỉnh) --------------------------

    def list_salaries(self, employee_id: int):
        return self.payroll.list_salaries(employee_id)

    def set_salary(self, *, employee_id, actor, effective_from, amount_mode="manual",
                   base_amount=None, insurance_base=None, allowance=0, note=None,
                   chuyen_can=0, luong_vi_tri=0, luong_trach_nhiem=0,
                   phu_cap_ca=0, phu_cap_tham_nien=0, insurance_elsewhere=False,
                   union_member=False, luong_dot_1=0, apply_self_deduction=True,
                   commission_pct=0):
        """Khai báo/điều chỉnh lương = LUÔN thêm MỘT bản ghi mới (không ghi đè), kể cả nhiều lần
        trong ngày → giữ NHẬT KÝ điều chỉnh đầy đủ (ai · lúc nào · số nào). "Hiện hành" cho 1 kỳ =
        bản `effective_from` lớn nhất ≤ kỳ, hòa ngày thì `id` lớn hơn (bản lưu SAU) thắng — xem
        repo `current_salary`/`list_salaries` (đã sort `effective_from` desc, `id` desc).

        Mức nền = `luong_vi_tri + luong_trach_nhiem` (gõ riêng từng ô). Chủ 2026-07-20: **lương
        vị trí = lương cơ bản = mức đóng BH**. Phụ cấp (`phu_cap_ca` · `phu_cap_tham_nien` ·
        `allowance` = khác) KHAI TAY, số cố định dùng mọi tháng — engine cộng phẳng, không tự tính.
        `insurance_base` giữ nhận cho tương thích API cũ nhưng engine THÔI đọc (BH bám vị trí)."""
        emp = self.employees.get_by_id(employee_id)
        if emp is None:
            raise PayrollNotFound("Không tìm thấy nhân viên.")
        if effective_from is None:
            raise PayrollValidationError("Thiếu ngày hiệu lực.")
        vi_tri = float(luong_vi_tri or 0)
        trach_nhiem = float(luong_trach_nhiem or 0)
        has_own = vi_tri + trach_nhiem > 0
        if has_own and amount_mode == AMOUNT_RULE:
            amount_mode = AMOUNT_MANUAL      # mức riêng của NV = ấn định tay
        if amount_mode == AMOUNT_MANUAL and base_amount is None and not has_own:
            raise PayrollValidationError("Cần khai mức lương (lương vị trí) cụ thể.")
        return self.payroll.create_salary(
            employee_id=employee_id,
            effective_from=effective_from,
            created_by=getattr(actor, "id", None),
            amount_mode=amount_mode,
            base_amount=base_amount, insurance_base=insurance_base, allowance=allowance or 0,
            note=note, chuyen_can=chuyen_can or 0,
            luong_vi_tri=vi_tri, luong_trach_nhiem=trach_nhiem,
            phu_cap_ca=phu_cap_ca or 0, phu_cap_tham_nien=phu_cap_tham_nien or 0,
            insurance_elsewhere=bool(insurance_elsewhere),
            union_member=bool(union_member),
            apply_self_deduction=bool(apply_self_deduction),
            luong_dot_1=float(luong_dot_1 or 0),
            # CHỈ KHAI: `_compute` không đọc cột này — khai bao nhiêu cũng không đổi tiền.
            commission_pct=float(commission_pct or 0),
        )

    def delete_salary(self, salary_id: int) -> None:
        s = self.payroll.get_salary(salary_id)
        if s is None:
            raise PayrollNotFound("Không tìm thấy bản ghi lương.")
        self.payroll.delete_salary(s)

    def salary_preview(self, employee_id: int, on: date | None = None) -> dict:
        """Xem trước mức lương hiện hành của 1 NV (cho tab Lương nhân viên)."""
        emp = self.employees.get_by_id(employee_id)
        if emp is None:
            raise PayrollNotFound("Không tìm thấy nhân viên.")
        on = on or date.today()
        params = self.get_params()
        salary = self.payroll.current_salary(employee_id, on)
        res = self._resolve_salary(emp, salary, params, on)
        vi_tri = float(getattr(salary, "luong_vi_tri", 0) or 0) if salary else 0.0
        return {
            "employee_id": employee_id,
            "monthly": res["monthly"],
            "source": res["source"],
            "chuyen_can": res["chuyen_can_amt"],
            "allowance": float(salary.allowance) if salary else 0.0,
            "phu_cap_ca": float(getattr(salary, "phu_cap_ca", 0) or 0) if salary else 0.0,
            "phu_cap_tham_nien": float(getattr(salary, "phu_cap_tham_nien", 0) or 0) if salary else 0.0,
            # Mức đóng BH = MỨC NỀN (vị trí + trách nhiệm) — chủ chốt 12/08/2026, đảo chốt cũ
            # 20/07/2026. PHẢI khớp `_compute`: màn hồ sơ lương xem trước một số, bảng lương ra số
            # khác thì HCNS mất niềm tin vào cả hai.
            "insurance_base": res["monthly"],
            "luong_vi_tri": vi_tri,
            "luong_trach_nhiem": float(getattr(salary, "luong_trach_nhiem", 0) or 0) if salary else 0.0,
        }

    # --- advances (tạm ứng) -------------------------------------------------

    def _new_advance_code(self, advance_date, kind=ADV_KIND_TAM_UNG) -> str:
        """Mã phiếu <TU|L1>-YYMMDD-XXXX (duy nhất, thử lại nếu trùng). Tiền tố L1 = lương đợt 1."""
        pre = "L1" if kind == ADV_KIND_LUONG_DOT_1 else "TU"
        d = advance_date
        if isinstance(d, str):
            try:
                d = date.fromisoformat(d[:10])
            except ValueError:
                d = date.today()
        ymd = d.strftime("%y%m%d")
        for _ in range(20):
            suffix = "".join(secrets.choice(_ADV_CODE_ALPHABET) for _ in range(4))
            code = f"{pre}-{ymd}-{suffix}"
            if not self.payroll.advance_code_exists(code):
                return code
        # Cực hiếm 20 lần trùng → nới suffix 6 ký tự cho chắc chắn duy nhất.
        return f"{pre}-{ymd}-{''.join(secrets.choice(_ADV_CODE_ALPHABET) for _ in range(6))}"

    def _chan_neu_ky_luong_da_khoa(self, year: int, month: int, viec: str) -> None:
        """Chặn đụng vào TẠM ỨNG của kỳ lương đã CHỐT / ĐÃ CHI (chủ chốt 15/08/2026).

        Tạm ứng khác chấm công ở một điểm quyết định: nó KHÔNG có ảnh chụp. Số tiền được nướng
        thẳng vào dòng lương lúc "Tính lại", nên phiếu đổi trạng thái sau đó là hai bên lệch ngay.
        Lệch theo hai chiều tiền ngược nhau, cả hai đều không để lại dấu:
          · duyệt muộn  → lương đã trả ĐỦ, mà tiền mặt thì đã đưa ⇒ công ty mất khoản đó;
          · huỷ muộn    → lương đã TRỪ rồi, phiếu lại không còn ⇒ thợ mất khoản đó.
        """
        if int(year) <= 0 or int(month) <= 0:
            return
        period = self.payroll.get_period_by_ym(int(year), int(month))
        if period is not None and period.status in (PERIOD_LOCKED, PERIOD_PAID):
            da_chi = period.status == PERIOD_PAID
            raise PayrollLocked(
                f"Kỳ lương {int(month):02d}/{int(year)} đã "
                + ("CHI" if da_chi else "chốt")
                + f" — số đã khoá nên không {viec} nữa. "
                + ("Huỷ 'đã chi' rồi mở lại kỳ lương" if da_chi else "Mở lại kỳ lương")
                + " trước, sửa xong nhớ bấm “Tính lại”."
            )

    def create_advance(self, *, employee_id, actor, period_year, period_month,
                        advance_date, amount, reason=None, kind=ADV_KIND_TAM_UNG):
        """Tạo phiếu tạm ứng (kind=tam_ung) hoặc phiếu thanh toán lương đợt 1 (kind=luong_dot_1).
        Trần tạm ứng ĐÃ GỠ (chủ 2026-07-24) — không còn giới hạn số tiền."""
        emp = self.employees.get_by_id(employee_id)
        if emp is None:
            raise PayrollNotFound("Không tìm thấy nhân viên.")
        if amount is None or float(amount) <= 0:
            raise PayrollValidationError("Số tiền phải > 0.")
        self._chan_neu_ky_luong_da_khoa(period_year, period_month, "lập thêm phiếu tạm ứng")
        code = self._new_advance_code(advance_date, kind=kind)
        row = self.payroll.create_advance(
            code=code, employee_id=employee_id, period_year=period_year, period_month=period_month,
            advance_date=advance_date, amount=amount, reason=reason, kind=kind,
            status=ADV_PENDING, created_by=getattr(actor, "id", None),
        )
        self._audit(actor, "payroll_create_advance", f"salary_advance:{row.id}",
                    f"{row.code or row.id} · {kind} · {float(amount):,.0f}đ")
        return row

    def list_advances(self, *, year, month, status=None):
        return self.payroll.list_advances(year=year, month=month, status=status)

    def count_pending_advances(self) -> int:
        """Số tạm ứng đang CHỜ DUYỆT (mọi kỳ) — nuôi badge real-time cho người duyệt."""
        return self.payroll.count_advances_by_status(ADV_PENDING)

    def advances_by_employee(self, employee_id: int):
        return self.payroll.list_advances_by_employee(employee_id)

    def decide_advance(self, *, advance_id, actor, approve: bool, scope: str, note=None):
        """Duyệt / từ chối đề nghị tạm ứng.

        Chủ chốt 29/07/2026: **tạm ứng do bên NHÂN SỰ duyệt**. Hiện chỉ HCNS có ô quyền `luong`
        (scope `all`) nên chốt phạm vi dưới đây KHÔNG đổi hành vi hôm nay — nó là lớp khoá dự
        phòng: mai kia ai đó cấp `luong:update` cho một vai scope `department` thì người đó cũng
        chỉ duyệt được tạm ứng trong tổ mình, không phải cả công ty. Tạm ứng là TIỀN MẶT."""
        a = self.payroll.get_advance(advance_id)
        if a is None:
            raise PayrollNotFound("Không tìm thấy đề nghị tạm ứng.")
        emp = self.employees.get_by_id(a.employee_id)
        if emp is not None and not self.employees.can_access(
            employee=emp, scope=scope, actor=actor
        ):
            raise PayrollForbidden("Nhân viên này ngoài phạm vi quản lý của bạn.")
        if a.status != ADV_PENDING:
            raise PayrollValidationError("Đề nghị đã được xử lý.")
        self._chan_neu_ky_luong_da_khoa(
            a.period_year, a.period_month, "duyệt / từ chối phiếu tạm ứng của kỳ đó")
        out = self.payroll.update_advance(
            a, status=ADV_APPROVED if approve else ADV_REJECTED,
            decided_by=getattr(actor, "id", None), decided_at=datetime.now(timezone.utc),
            decision_note=note,
        )
        # TẠM ỨNG LÀ TIỀN MẶT ⇒ phải có vết. Trước 18/08/2026 cả vòng đời tạm ứng không ghi một
        # dòng nhật ký nào, nên không trả lời được "ai duyệt phiếu ứng 5 triệu này, lúc nào".
        self._audit(actor, "payroll_decide_advance", f"salary_advance:{a.id}",
                    f"{'DUYỆT' if approve else 'TỪ CHỐI'} {a.code or a.id} · "
                    f"{float(a.amount):,.0f}đ" + (f" · {note}" if note else ""))
        return out

    def cancel_advance(self, *, advance_id, actor):
        a = self.payroll.get_advance(advance_id)
        if a is None:
            raise PayrollNotFound("Không tìm thấy đề nghị tạm ứng.")
        if a.status not in (ADV_PENDING, ADV_APPROVED):
            raise PayrollValidationError("Không thể hủy đề nghị này.")
        self._chan_neu_ky_luong_da_khoa(
            a.period_year, a.period_month, "huỷ phiếu tạm ứng của kỳ đó")
        # ĐÃ LẬP PHIẾU CHI = TIỀN ĐÃ RỜI KÉT ⇒ KHÔNG cho huỷ (chủ chốt 18/08/2026). Huỷ ở đây mà
        # phiếu chi vẫn nằm trong sổ quỹ là mất dấu chứng từ: sổ quỹ có khoản chi, phân hệ Lương
        # thì bảo phiếu đã huỷ, và số tạm ứng khấu trừ vào bảng lương cũng biến mất theo.
        # Muốn huỷ thì phải huỷ PHIẾU CHI trước.
        if self._vouchers is not None:
            pc = self._vouchers.get_voucher_by_salary_advance(a.id)
            if pc is not None:
                raise PayrollValidationError(
                    f"Phiếu tạm ứng này đã lập phiếu chi {pc.code} — huỷ phiếu chi trước rồi mới huỷ được."
                )
        out = self.payroll.update_advance(a, status=ADV_CANCELLED)
        self._audit(actor, "payroll_cancel_advance", f"salary_advance:{a.id}",
                    f"{a.code or a.id} · {float(a.amount):,.0f}đ")
        return out

    # --- engine tính 1 dòng -------------------------------------------------

    def _compute(self, *, employee, salary, params, actual_cong, standard_cong,
                 vi_pham=0.0, other_bonus=0.0, khoan=0.0, khoan_km=0.0, khoan_defect=0.0,
                 ot_minutes=0, night_days=0, holiday_cong=0.0, restday_cong=0.0, plain_cong=0.0,
                 paid_leave_cong=0.0, excused_cong=0.0,
                 ot_holiday_minutes=0, ot_restday_minutes=0,
                 night_premium_minutes=0.0, ot_night_normal_minutes=0,
                 ot_night_restday_minutes=0, ot_night_holiday_minutes=0, has_piece_work=False,
                 thuong_5s=0.0, thuong_doanh_so=0.0, thuong_thanh_tich=0.0, phep_nam=0.0,
                 tra_dong_phuc=0.0, dieu_chinh_luong=0.0, di_tre=0.0, dt_vuot_troi=0.0,
                 phat_bien_ban=0.0, phat_5s_dong_phuc=0.0,
                 components=None, line_components=None,
                 # {ca → [công từng ngày làm ca đó]} từ Chấm công + bảng tra ca (mức cơm/phụ cấp).
                 # Mặc định rỗng để unit test dựng tay không phải khai — số ra y như trước.
                 ca_lam=None, ot_days=None, shift_by_id=None,
                  brackets=None, on: date, employee_status: str | None = None,
                  department_id: int | None = None) -> dict:
        effective_status = employee_status or employee.status
        # "Hết thử việc, chờ HCNS xác nhận" ĂN TIỀN Y HỆT THỬ VIỆC (chủ chốt 22/08/2026): vẫn
        # hệ số `probation_ratio`, vẫn không đóng BHXH, vẫn không trừ đoàn phí. Chủ chốt là tiền
        # KHÔNG đổi cho tới khi HCNS bấm "Chuyển chính thức" — trạng thái mới chỉ để MÀN HÌNH nói
        # đúng rằng thời gian thử việc đã hết, không phải để đổi số.
        # ⚠️ Rủi ro đã ghi rõ cho chủ trước khi chốt: Điều 27 BLLĐ coi người làm tiếp sau thử việc
        # là ĐÃ chính thức, nên phần 20% giữ lại kể từ ngày hết hạn là trả thiếu. Chủ vẫn chọn
        # phương án này. ĐỪNG tự "sửa cho đúng luật" — hỏi chủ trước.
        is_probation = effective_status in (STATUS_PROBATION, STATUS_PROBATION_ENDED)
        ratio = float(params.probation_ratio) if is_probation else 1.0
        dept_id = (getattr(employee, "department_id", None)
                   if department_id is None else department_id)
        res = self._resolve_salary(
            employee, salary, params, on, department_id=dept_id
        )
        monthly = res["monthly"]
        eff_monthly = monthly * ratio  # mức tháng thực (đã tính %thử việc)

        std = float(standard_cong) or 1.0
        daily_rate = eff_monthly / std                       # đơn giá 1 công
        # CHẶN TRẦN: làm ĐỦ (≥ công chuẩn) → nguyên lương tháng, KHÔNG trả dư khi tháng dài; làm
        # thiếu → prorate theo tỉ lệ công thực / công chuẩn. NGÀY NGHỈ PHÉP trong đó chỉ trả
        # lương VỊ TRÍ (không trách nhiệm) — xem `_luong_cong_split`.
        # Hồ sơ cũ chỉ khai `base_amount` (source != "employee") thì coi cả cục là lương vị trí,
        # nếu không ngày phép của họ ra 0 đồng.
        vi_tri = float(getattr(salary, "luong_vi_tri", 0) or 0) if salary is not None else 0.0
        eff_vi_tri = (vi_tri if res.get("source") == "employee" else monthly) * ratio
        # Công lễ/nghỉ tuần CÓ đi làm — tách khỏi rổ bị trần (Đ98.1.b/c). `holiday_cong` và
        # `restday_cong` là TẬP CON của `actual_cong` (Chấm công chỉ trừ riêng `plain_cong`).
        special_cong = max(0.0, float(holiday_cong) + float(restday_cong))
        luong_cong, luong_ngay_phep, paid_leave_eff = _luong_cong_split(
            eff_monthly=eff_monthly, std=std,
            actual_cong=actual_cong, paid_leave_cong=paid_leave_cong,
            special_cong=special_cong,
        )
        # Chuyên cần TRỪ DẦN (C3): nghỉ 0,5 ngày −25% · 1 ngày −50% · ≥2 ngày mất hết.
        # Công thiếu NHƯNG CÓ ĐƠN nghỉ theo giờ đã duyệt được bù lại ở đây (chủ chốt: có đơn thì
        # không mất chuyên cần) — tiền công thì vẫn trừ, `actual_cong` không đổi.
        chuyen_can = float(res["chuyen_can_amt"]) * _chuyen_can_ratio(
            float(actual_cong) + float(excused_cong), standard_cong)
        # Phụ cấp KHAI TAY của NV (`employee_salaries`) — số cố định, hệ thống KHÔNG tính toán gì;
        # cộng PHẲNG (không prorate theo công, không vào gốc tính tăng ca).
        # `allowance` (dòng lương) = phụ cấp KHÁC + thâm niên; phụ cấp CA đi riêng qua `night_pay`
        # (miễn TNCN như tăng ca — giữ nguyên). Trách nhiệm KHÔNG ở đây — nó là `luong_trach_nhiem`
        # trong mức nền (đã vào luong_cong).
        tham_nien = _round(getattr(salary, "phu_cap_tham_nien", 0) or 0) if salary else 0.0
        # Khoản DANH MỤC (chủ 2026-07-27) — thay ô "phụ cấp khác" gộp một cục. Cộng vào `allowance`
        # để không đổi cấu trúc phiếu lương, nhưng giữ riêng phần MIỄN THUẾ để `_auto_pit` trừ ra.
        #
        # ⚠️ HAI DANH SÁCH, ĐỪNG GỘP:
        #   `components`      = khoản gán ở HỒ SƠ NV (Tầng 2, `source='employee'`) ⇒ vào `allowance`.
        #   `line_components` = khoản PHÁT SINH riêng kỳ này (Tầng 3, `source='line'`) ⇒ KHÔNG vào
        #                       `allowance`, chỉ cộng thẳng vào `gross_pre`.
        # Lý do: `update_line` cộng `extra_thu` (phần `source='line'`) LÊN TRÊN `ln.allowance` đã
        # lưu. Nếu `allowance` cũng nuốt luôn phần đó thì "Tính lại" rồi sửa một ô là CỘNG HAI LẦN.
        comp_rows = list(components or [])
        line_rows = list(line_components or [])
        comp_thu = sum(float(c["amount"]) for c in comp_rows if c.get("kind") != "tru")
        # Khấu trừ và phần miễn thuế tính trên CẢ HAI nguồn — thuế/khấu trừ không phân biệt nguồn.
        comp_tru = sum(float(c["amount"]) for c in comp_rows + line_rows if c.get("kind") == "tru")
        component_exempt = sum(float(c["amount"]) for c in comp_rows + line_rows
                               if c.get("kind") != "tru" and not c.get("is_taxable", True))
        extra_thu_line = sum(float(c["amount"]) for c in line_rows if c.get("kind") != "tru")
        allowance = (float(salary.allowance) if salary else 0.0) + tham_nien + comp_thu

        # Tăng ca + làm ngày đặc biệt (Đ98) — KHÔNG prorate theo công (tính trên đơn giá chuẩn).
        # OT tách theo LOẠI NGÀY: thường ×ot_multiplier · nghỉ tuần ×restday · lễ ×holiday.
        # Làm NGUYÊN CÔNG ngày nghỉ tuần/lễ: cộng THÊM premium (hệ số − 1)×đơn giá công (base 1×
        # đã nằm trong luong_cong vì holiday_cong/restday_cong là tập con của actual_cong).
        # ⚠️ ĐƠN GIÁ GIỜ BÁM LƯƠNG VỊ TRÍ, KHÔNG BÁM MỨC NỀN (chủ chốt 12/08/2026).
        # Trước đó gốc tính tăng ca là `eff_monthly` = vị trí + TRÁCH NHIỆM. Chủ chốt: "tiền tăng ca
        # tính trên lương cơ bản thôi, không có tiền trách nhiệm" — và xác nhận premium ca đêm +
        # premium làm ngày nghỉ/lễ "giảm cả", vì cả ba dùng CHUNG một đơn giá.
        # `luong_cong` (lương theo công) KHÔNG đổi — nó vẫn ăn `daily_rate` của mức nền đầy đủ.
        daily_rate_ot = eff_vi_tri / std
        hours_per_day = float(getattr(params, "standard_hours_per_day", 8) or 8)
        hourly_rate = daily_rate_ot / hours_per_day if hours_per_day else 0.0
        ot_h = max(0, int(ot_minutes) - int(ot_holiday_minutes) - int(ot_restday_minutes)) / 60.0
        m_ot = float(getattr(params, "ot_multiplier", 1.5) or 0)
        m_ot_rest = float(getattr(params, "ot_multiplier_restday", 2.0) or 0)
        m_ot_hol = float(getattr(params, "ot_multiplier_holiday", 3.0) or 0)
        m_rest = float(getattr(params, "restday_work_multiplier", 2.0) or 0)
        m_hol = float(getattr(params, "holiday_work_multiplier", 3.0) or 0)
        # Tiền ngày off1x tách thành BIẾN RIÊNG: nó nằm trong `ot_pay` (để trả) nhưng CHỊU thuế
        # (kế toán chốt 17/08/2026), nên thuế phải cộng ngược lại qua `ot_taxable`.
        off1x_pay = daily_rate * float(plain_cong) * 1.0
        if not self._component_enabled(COMP_TANG_CA, dept_id):
            # ⚠️ ĐẢO 17/08/2026 — GỠ vế `has_piece_work`. Chủ chốt: "Tổ khoán VẪN CÓ tăng ca".
            # Lý do biện minh cũ ("khoán đã trả theo sản lượng") KHÔNG tồn tại: cột `khoan` LUÔN
            # bằng 0 vì `ProductionOutputRepository` chưa dựng và `deps.py` truyền `outputs=None`
            # ⇒ tổ khoán mất trắng cả giờ OT, cả premium lễ/CN, cả tiền ngày off1x.
            # NĐ 145/2020 Đ55.2 cũng buộc trả làm thêm cho người hưởng lương theo SẢN PHẨM.
            # Nay chỉ còn MỘT cổng: công tắc `tang_ca` của bộ phận ở Cấu hình lương.
            ot_pay = 0.0
            off1x_pay = 0.0   # không trả thì cũng không có gì để chịu thuế
        else:
            ot_pay = _round(
                hourly_rate * (ot_h * m_ot
                               + (int(ot_restday_minutes) / 60.0) * m_ot_rest
                               + (int(ot_holiday_minutes) / 60.0) * m_ot_hol)
                # PREMIUM ngày lễ / nghỉ tuần = phần TRẢ THÊM ⇒ bám `daily_rate_ot` (lương vị trí),
                # cùng gốc với tăng ca theo chủ chốt 12/08/2026.
                #
                # ⚠️ HAI HỆ SỐ KHÁC NHAU — CỐ Ý, ĐỪNG "dọn" cho giống nhau (chủ chốt 17/08/2026):
                #  • NGÀY LỄ dùng TRỌN `m_hol` (300%). Đ98.1.c trả "ít nhất 300% CHƯA KỂ tiền lương
                #    ngày lễ" — mà tiền lương ngày lễ (Đ112) người đó ĐÃ được hưởng dù có đi làm hay
                #    không. Phần 1× nằm trong `luong_cong` CHÍNH LÀ khoản Đ112 đó ⇒ tổng 1× + 3× = 4×.
                #  • NGHỈ TUẦN dùng `m_rest - 1` (100%). Chủ nhật KHÔNG có lương nếu nghỉ ở nhà, nên
                #    phần 1× trong `luong_cong` là tiền TRẢ CHO VIỆC ĐI LÀM, không phải khoản có sẵn
                #    ⇒ tổng 1× + 1× = 2×, đúng Đ98.1.b. Cho ngày lễ ăn `m_hol - 1` là trả THIẾU 1×;
                #    cho Chủ nhật ăn trọn `m_rest` là trả THỪA 1×.
                + daily_rate_ot * (float(holiday_cong) * max(0.0, m_hol)
                                   + float(restday_cong) * max(0.0, m_rest - 1.0))
                # ⚠️ Ngày 'off1x' KHÔNG đi cùng nhánh trên: đây KHÔNG phải premium mà là LƯƠNG CHÍNH
                # của ngày đó (làm 1×, không hệ số) — `plain_cong` đã bị loại khỏi `actual_cong` ở
                # Chấm công nên `luong_cong` không trả nó, phải trả trọn ở đây. Nó phải ăn ĐÚNG mức
                # nền như mọi ngày công khác. Kéo nó sang `daily_rate_ot` là âm thầm cắt phần lương
                # trách nhiệm của riêng những ngày off1x — một khoản CẮT KHÔNG AI YÊU CẦU.
                + off1x_pay
            )
        # ⚠️ NGƯNG 03/08/2026 — đường phụ cấp ca PER-NGƯỜI (số phẳng gõ tay ở hồ sơ lương) đã tắt.
        # Phụ cấp cơm/ca nay tính THEO CA THỰC LÀM ở khối ngay dưới. Phải tắt CÙNG LƯỢT với việc
        # bật khối đó — để cả hai cùng chạy là TRẢ HAI LẦN. Cột `employee_salaries.phu_cap_ca` vẫn
        # còn (không drop) để giữ lịch sử; ô trên màn Lương chuyển thành chỉ đọc.
        night_pay = 0.0

        # --- Phụ cấp CƠM CA + PHỤ CẤP CA, theo TỪNG CA THỰC LÀM ---------------------------
        # `ca_lam` = {ca → [công của từng ngày làm ca đó]} do Chấm công báo (đã đóng băng qua Chốt
        # công ở `ca_lam_json`). Ở ĐÂY mới áp CHÍNH SÁCH: ngày đủ ngưỡng thì hưởng TRỌN, dưới
        # ngưỡng thì không có — cố ý KHÔNG nhân theo tỷ lệ (chủ chốt 03/08/2026). Một suất ăn là
        # có hoặc không; nhân tỷ lệ thì đi muộn 15 phút (công 0,97) ra 24.250đ tiền cơm.
        min_cong = float(getattr(params, "phu_cap_ca_min_cong", 0.5) or 0)
        ca_theo_id = shift_by_id or {}
        meal_allowance_pay = 0.0
        shift_allowance_pay = 0.0
        for shift_id, cong_list in (ca_lam or {}).items():
            ca = ca_theo_id.get(int(shift_id))
            if ca is None:
                continue          # ca đã xoá khỏi danh mục → không đoán mức, bỏ qua
            so_ngay = sum(1 for c in cong_list if float(c or 0) >= min_cong)
            if so_ngay <= 0:
                continue
            meal_allowance_pay += float(getattr(ca, "meal_allowance", 0) or 0) * so_ngay
            shift_allowance_pay += float(getattr(ca, "shift_allowance", 0) or 0) * so_ngay
        meal_allowance_pay = _round(meal_allowance_pay)
        shift_allowance_pay = _round(shift_allowance_pay)

        # --- SUẤT CƠM TĂNG CA (chủ chốt 12/08/2026) --------------------------------------
        # "Tăng ca 3 tiếng được thưởng tiền cơm, setup động; riêng ngày chủ nhật cứ tăng ca là có
        # dù 1 hay 2 tiếng." Chủ chốt chốt tiếp: "chủ nhật" hiểu là NGÀY NGHỈ THEO LỊCH CHUNG —
        # nhà máy đổi ngày nghỉ thì luật đi theo, và ngày lễ / off1x cũng vào nhánh dễ.
        #
        # Chấm công đã phân sẵn hai rổ (`ot_days.lam` / `.nghi`) nên ở đây chỉ còn ÁP CHÍNH SÁCH:
        #   ngày LÀM VIỆC → phải đủ ngưỡng phút
        #   ngày NGHỈ     → có phút nào là có suất
        # Hưởng TRỌN suất hoặc KHÔNG — cùng lối với cơm ca, không nhân theo tỷ lệ.
        muc_com_tc = float(getattr(params, "com_tang_ca_muc", 0) or 0)
        nguong_tc = int(getattr(params, "com_tang_ca_nguong_phut", 180) or 0)
        od = ot_days or {}
        so_suat_com_tc = (
            sum(1 for phut in (od.get("lam") or {}).values() if int(phut) >= nguong_tc)
            + sum(1 for phut in (od.get("nghi") or {}).values() if int(phut) > 0)
        )
        # Bộ phận TẮT tăng ca: không có tiền tăng ca thì cũng không có suất cơm tăng ca.
        # (Gỡ vế `has_piece_work` 17/08/2026 cùng lượt với `ot_pay` — tổ khoán nay CÓ tăng ca.)
        if ot_pay <= 0 and not self._component_enabled(COMP_TANG_CA, dept_id):
            so_suat_com_tc = 0
        com_tang_ca_pay = _round(so_suat_com_tc * muc_com_tc)
        # MIỄN TNCN cả hai (chủ chốt 04/08/2026). Trước đó để chịu thuế với lý do "khoản nào thật
        # sự miễn thì khai ở danh mục khoản thu nhập" — nhưng khai ở đó nữa là TRẢ HAI LẦN, nên
        # thực tế không có đường nào miễn: cùng một khoản tiền cơm, đi đường ca thì chịu thuế, đi
        # đường danh mục thì miễn. Kế toán đang xếp "Tiền ăn ca/CN/GH" vào nhóm MIỄN
        # (`docs/prd-thu-nhap-chiu-thue.md §1`). KHÔNG áp trần 730.000đ/tháng — đồng bộ chốt "miễn
        # toàn bộ, không áp trần luật" ở §2 của chính tài liệu đó; rủi ro đã ghi ở §7.
        # Cơm tăng ca miễn TNCN như cơm ca (chủ chốt 12/08/2026: "Có").
        ca_exempt = meal_allowance_pay + shift_allowance_pay + com_tang_ca_pay

        # Lương CA ĐÊM theo GIỜ (Đ98) — DÒNG RIÊNG (`night_premium_pay`), MIỄN TNCN như tăng ca. Hai phần:
        #  (1) giờ đêm TRONG ca × hệ số per-ca (Chấm công đã weight (hệ số−1)) → premium theo giờ.
        #  (2) TĂNG CA ĐÊM (Đ98.3): cộng dồn (night_pct + ot_extra×hệ số loại ngày) trên đơn giá giờ; hệ số
        #      OT gốc ĐÃ nằm trong `ot_pay` (ot_minutes gồm cả giờ OT đêm) → chỉ cộng phần chênh, KHÔNG double.
        night_pct = float(getattr(params, "night_pct", 0.3) or 0.3)
        ot_extra = float(getattr(params, "ot_night_extra_pct", 0.2) or 0.2)
        night_premium_pay = _round(
            hourly_rate * float(night_premium_minutes) / 60.0
            + hourly_rate * ((int(ot_night_normal_minutes) / 60.0) * (night_pct + ot_extra * 1.0)
                             + (int(ot_night_restday_minutes) / 60.0) * (night_pct + ot_extra * m_rest)
                             + (int(ot_night_holiday_minutes) / 60.0) * (night_pct + ot_extra * m_hol))
        )


        # Các khoản thưởng chi tiết = thu nhập CHỊU THUẾ (như other_bonus); dieu_chinh_luong cộng đại số (±).
        extra_income = (float(thuong_5s) + float(thuong_doanh_so) + float(thuong_thanh_tich)
                        + float(phep_nam) + float(tra_dong_phuc) + float(dieu_chinh_luong))
        # Lương TRƯỚC khấu trừ kỷ luật. vi_pham (+ các khoản phạt chi tiết) là khấu trừ SAU thuế
        # (bồi thường/kỷ luật) — KHÔNG giảm thu nhập chịu thuế TNCN, và bị kẹp trần 30% (Điều 102) ở dưới.
        # `extra_thu_line` nằm NGOÀI `allowance` (xem khối khoản danh mục ở trên) nên phải cộng
        # riêng ở đây — cùng cách `update_line` cộng `extra_thu`, để hai đường ra CÙNG một số.
        # `khoan_km` CỘNG PHẲNG như `khoan`: tài xế ăn NGUYÊN lương chấm công rồi cộng thêm tiền
        # theo km — không prorate theo công, không nhân hệ số thử việc. Và nó CHỊU TNCN: không nằm
        # trong `mien_ngoai_danh_muc` nên tự động vào thu nhập chịu thuế, đúng luật.
        gross_pre = (luong_cong + chuyen_can + allowance + float(khoan) + float(khoan_km)
                     + ot_pay + night_pay + night_premium_pay + float(other_bonus)
                     + meal_allowance_pay + shift_allowance_pay + com_tang_ca_pay
                     + extra_income + extra_thu_line)

        # Số ngày KHÔNG làm việc và KHÔNG hưởng lương trong tháng — dùng cho luật 14 ngày ở dưới.
        # `actual_cong` ĐÃ gồm ngày lễ hưởng lương và ngày phép có lương (Chấm công cộng vào
        # `total_cong` ở `attendance_service.py:1258` và `:1276`) nên hai loại đó KHÔNG bị đếm là
        # nghỉ không lương — đúng ý luật. Riêng `plain_cong` (ngày off1x CÓ đi làm, CÓ trả 1×) đã
        # bị trừ khỏi `total_cong` ở `:1195` nên phải cộng trả lại, nếu không người đi làm ngày
        # off1x bị đếm nhầm thành nghỉ không lương và mất BHXH oan.
        ngay_khong_luong = max(
            0.0,
            float(standard_cong or 0) - float(actual_cong or 0) - float(plain_cong or 0),
        )
        nguong_bhxh = int(
            getattr(params, "bhxh_mien_tu_so_ngay", BHXH_MIEN_TU_SO_NGAY_MAC_DINH) or 0)

        # BHXH: thử việc KHÔNG đóng (HĐ thử việc, Đ2 Luật BHXH); áp trần RIÊNG BHXH/BHYT vs BHTN.
        if is_probation:
            insurance_base = 0.0
            bhxh = 0.0
        elif bool(getattr(salary, "insurance_elsewhere", False)):
            # BH đóng ở nơi khác (công ty B) → công ty mình KHÔNG trừ BHXH/BHYT/BHTN của NV. GIỮ
            # insurance_base (= lương cơ bản) để đoàn phí công đoàn vẫn tính + hiển thị. Công ty chỉ chịu
            # TNLĐ-BNN (`params.tnld_bnn_rate`) — khoản đó thuộc phía chủ SDLĐ, KHÔNG trừ vào lương và chỉ
            # hiện ở màn Sửa lương (FE); engine không ghi vào bảng lương tháng nên không xuất ở đây.
            # Cùng gốc với nhánh đóng BH bình thường (chủ chốt 12/08/2026): vị trí + trách
            # nhiệm. Để lệch giữa các nhánh là ĐOÀN PHÍ ra hai mức khác nhau — nó tính trên
            # `insurance_base`, và hai nhánh miễn BHXH VẪN đóng đoàn phí (doc §8.5 bẫy 2).
            insurance_base = float(monthly)
            bhxh = 0.0
        elif nguong_bhxh > 0 and ngay_khong_luong >= nguong_bhxh:
            # QĐ 595/QĐ-BHXH Đ42.4: không làm việc và không hưởng tiền lương từ `nguong_bhxh` ngày
            # làm việc trở lên trong tháng thì THÁNG ĐÓ KHÔNG ĐÓNG BHXH. Một nhánh này phủ cả hai
            # tình huống: người vào/nghỉ việc GIỮA THÁNG (ít công), và người nghỉ không lương dài.
            #
            insurance_base = float(monthly)
            bhxh = 0.0
        else:
            # MỨC ĐÓNG BH = LƯƠNG CƠ BẢN + LƯƠNG TRÁCH NHIỆM (chủ chốt 12/08/2026, ĐẢO lại chốt
            # cũ ngày 20/07/2026 "chỉ lương vị trí"). Bảng lương thật của công ty xác nhận: BH bắt
            # buộc 1.102.080 ÷ 10,5% = 10.496.000, đúng bằng mức nền đầy đủ — và đoàn phí
            # 52.480 ÷ 0,5% ra CÙNG con số đó.
            # Giữ nguyên: KHÔNG prorate theo công · KHÔNG × hệ số thử việc · vẫn kẹp trần.
            # `monthly` đã là vị trí + trách nhiệm (xem `_resolve_monthly`), và với hồ sơ CŨ chỉ
            # khai `base_amount` thì nó là cả cục đó — đúng ý "mức nền đầy đủ" ở cả hai kiểu khai.
            insurance_base = float(monthly)
            bh_cap = float(getattr(params, "bh_base_cap", 0) or 0)
            bhtn_cap = float(getattr(params, "bhtn_base_cap", 0) or 0)
            bh_base = min(insurance_base, bh_cap) if bh_cap > 0 else insurance_base
            bhtn_base = min(insurance_base, bhtn_cap) if bhtn_cap > 0 else insurance_base
            bhxh = (bh_base * (float(params.bhxh_rate) + float(params.bhyt_rate))
                    + bhtn_base * float(params.bhtn_rate))

        # Đoàn phí công đoàn: CHỈ ĐOÀN VIÊN (cờ `union_member`) mới đóng, theo tỷ lệ cấu hình trên mức
        # đóng BH; thử việc KHÔNG đóng. Không là đoàn viên → 0 (chủ 2026-07-21: opt-in từng người).
        # ⚠️ TỪ 12/08/2026 đoàn phí GIẢM thu nhập TÍNH THUẾ (xem `_auto_pit`) — trước đó chỉ trừ vào
        # thực nhận. Nên biến này phải tính XONG TRƯỚC khi gọi `_auto_pit`, ở CẢ HAI đường.
        is_union = bool(getattr(salary, "union_member", False)) if salary else False
        cong_doan = 0.0 if (is_probation or not is_union) else _round(insurance_base * float(getattr(params, "cong_doan_rate", 0) or 0))

        gross_pre_r = _round(gross_pre)
        bhxh_r = _round(bhxh)
        # TNCN tự tính (5 bậc lũy tiến) — miễn toàn bộ OT+ca đêm, trừ BHXH + giảm trừ gia cảnh.
        # Tính trên lương TRƯỚC khấu trừ kỷ luật (khấu trừ kỷ luật không giảm thu nhập chịu thuế).
        if brackets is None:
            brackets = self.get_pit_brackets()
        dependents = int(getattr(employee, "dependents_count", 0) or 0)
        pit_assessable, pit_taxable, pit_auto = self._auto_pit(
            gross=gross_pre_r, bhxh=bhxh_r, ot_pay=ot_pay, night_pay=night_pay,
            night_premium_pay=night_premium_pay, component_exempt=component_exempt + ca_exempt,
            apply_self_deduction=bool(getattr(salary, "apply_self_deduction", True)) if salary else True,
            pit_mode=getattr(employee, "pit_mode", None), cong_doan=cong_doan,
            dependents_count=dependents, params=params, brackets=brackets,
            ot_taxable=off1x_pay,   # tiền ngày off1x nằm trong ot_pay nhưng CHỊU thuế
        )

        # Điều 102 BLLĐ: tổng khấu trừ BỒI THƯỜNG/KỶ LUẬT ≤ 30% lương tháng SAU khi trích BHXH + TNCN.
        # GỘP tất cả khoản phạt chi tiết + vi_pham + trừ lỗi khoán vào CHUNG 1 trần 30%. Phần vượt KHÔNG
        # trừ kỳ này. LƯU RAW từng cột phạt (không phân rã capped) → phiếu hiện đúng số đã nhập.
        phat_total = (float(vi_pham) + float(di_tre) + float(dt_vuot_troi)
                      + float(phat_bien_ban) + float(phat_5s_dong_phuc))
        phat_eff = _capped_penalty(gross_pre=gross_pre_r, bhxh=bhxh_r, pit=pit_auto,
                                   phat_total=phat_total, khoan_defect=khoan_defect,
                                   cap_pct=getattr(params, "phat_cap_pct", 0.30))
        # SÀN 0: trần 30% vốn là thứ ngăn `gross` xuống âm (phạt ≤ 30% của chính thu nhập). Khi
        # chủ TẮT trần (`phat_cap_pct = 0`) thì hàng rào đó mất — phạt lớn hơn thu nhập sẽ ra
        # gross ÂM, in ra phiếu lương là số vô nghĩa. Phần vượt KHÔNG dồn sang kỳ sau.
        gross_r = max(0.0, _round(gross_pre_r - phat_eff))

        return {
            "is_probation": is_probation,
            # Khoản DANH MỤC loại TRỪ — trừ thẳng vào THỰC NHẬN, cố ý KHÔNG gộp vào trần 30% của
            # Điều 102: trần đó dành cho BỒI THƯỜNG/KỶ LUẬT, còn đây là khấu trừ thoả thuận
            # (mua đồng phục, ứng tiền…). Gộp nhầm là nới trần kỷ luật cho một khoản không phải phạt.
            "component_deduct": _round(comp_tru),
            # Snapshot 2 số DẪN XUẤT cho phiếu lương. CHỊU thuế ≠ TÍNH thuế (`pit_taxable`).
            "thu_nhap_chiu_thue": _round(pit_assessable),
            "thu_nhap_mien_thue": _round(
                float(ot_pay) - float(off1x_pay) + float(night_pay) + float(night_premium_pay)
                + component_exempt + ca_exempt),
            # TRONG ĐÓ của `ot_pay` — tiền ngày off1x, CHỊU thuế. Snapshot để "Sửa 1 ô" trừ đúng
            # y "Tính lại". ĐỪNG cộng vào gross: đã nằm trong `ot_pay`.
            "off1x_pay": _round(off1x_pay),
            "monthly_salary": _round(monthly),
            "luong_cong": _round(luong_cong),
            # TRONG ĐÓ của `luong_cong` — phiếu lương hiện dòng riêng, TUYỆT ĐỐI không cộng
            # lại vào gross (cùng idiom với `phu_cap_tham_nien ⊂ allowance` bên dưới).
            "luong_ngay_phep": _round(luong_ngay_phep),
            "paid_leave_cong": round(float(paid_leave_eff), 2),
            # Snapshot để "Sửa 1 ô" gọi lại `_luong_cong_split` ra ĐÚNG số của "Tính lại".
            "special_cong": round(float(special_cong), 2),
            "excused_cong": round(float(excused_cong), 2),
            "chuyen_can": _round(chuyen_can),
            "allowance": _round(allowance),
            "khoan": _round(khoan),
            "khoan_km": _round(khoan_km),
            "ot_minutes": int(ot_minutes),
            "ot_pay": ot_pay,
            "night_days": int(night_days),
            "night_pay": night_pay,          # NGƯNG 03/08/2026 — luôn 0 (xem chỗ gán)
            "night_premium_pay": night_premium_pay,   # premium giờ đêm + tăng ca đêm (theo giờ), miễn TNCN
            # Phụ cấp theo CA THỰC LÀM — MIỄN TNCN (xem `ca_exempt` ở trên). Hai cột này CỘNG
            # THÊM vào gross, KHÔNG phải "trong đó" của khoản nào.
            "meal_allowance_pay": meal_allowance_pay,
            "com_tang_ca_pay": com_tang_ca_pay,
            "shift_allowance_pay": shift_allowance_pay,

            # TRONG ĐÓ của `allowance` (đã cộng ở trên) — tách ra để phiếu lương hiện DÒNG RIÊNG
            # (chữa B2 "phụ cấp một cục"). ĐỪNG cộng lại vào gross lần nữa.
            "phu_cap_tham_nien": tham_nien,
            "vi_pham": _round(vi_pham),        # RAW (không capped) — trần 30% áp cho TỔNG phạt
            "other_bonus": _round(other_bonus),
            "thuong_5s": _round(thuong_5s),
            "thuong_doanh_so": _round(thuong_doanh_so),
            "thuong_thanh_tich": _round(thuong_thanh_tich),
            "phep_nam": _round(phep_nam),
            "tra_dong_phuc": _round(tra_dong_phuc),
            "dieu_chinh_luong": _round(dieu_chinh_luong),
            "di_tre": _round(di_tre),
            "dt_vuot_troi": _round(dt_vuot_troi),
            "phat_bien_ban": _round(phat_bien_ban),
            "phat_5s_dong_phuc": _round(phat_5s_dong_phuc),
            "gross": gross_r,
            "insurance_base": _round(insurance_base),
            "bhxh": bhxh_r,
            "cong_doan": cong_doan,
            "pit": pit_auto,
            "pit_taxable": pit_taxable,
        }

    # --- periods / bảng lương tháng -----------------------------------------

    def list_periods(self):
        return self.payroll.list_periods()

    def _cong_map(self, year: int, month: int) -> dict[int, float]:
        """{employee_id → số công} — đọc SNAPSHOT kỳ công đã CHỐT nếu có, chưa chốt thì tính live
        (logic gom ở AttendanceService.cong_map — Đ3: Lương đọc bản đã chốt)."""
        return self.attendance.cong_map(year, month)

    def generate(self, *, year, month, actor, scope="all"):
        """Tạo/làm mới bảng lương tháng. Giữ nguyên các ô TAY (vi phạm/thưởng/pit/ghi chú)
        của dòng đã có; chỉ tính lại phần tự động (công/mức/BHXH/tạm ứng)."""
        if not (1 <= int(month) <= 12):
            raise PayrollValidationError("Tháng phải trong 1–12.")
        self._reset_config_cache()   # luôn tính lại trên cấu hình lương MỚI NHẤT
        period = self.payroll.get_period_by_ym(year, month)
        params = self.get_params()
        # Công chuẩn ĐỘNG theo tháng (redesign-hcns Đ3/N4): số ngày làm việc THỰC của tháng theo Lịch
        # chung (tuần làm việc − ngày lễ + cộng làm bù). Nhờ vậy làm ĐỦ tháng = nguyên lương kể cả tháng
        # ngắn (vd T2 chỉ 24 ngày làm), và đơn giá giờ đúng NĐ145/2020 Đ55 (lương tháng ÷ số ngày làm việc
        # bình thường TRONG THÁNG ÷ giờ/ngày) — đây cũng là gốc tính tăng ca.
        # `standard_cong_default` chỉ còn là LƯỚI DỰ PHÒNG khi chưa có lịch (ô đã gỡ khỏi Cấu hình lương).
        std = None
        if self.attendance is not None:
            std = self.attendance.standard_working_days(year, month)
        std = float(std or 0)
        if std <= 0:
            std = float(params.standard_cong_default or 0)
        if std <= 0:
            std = 26.0
        if period is None:
            period = self.payroll.create_period(
                year=year, month=month, status=PERIOD_DRAFT,
                standard_cong=std, created_by=getattr(actor, "id", None),
            )
        if period.status != PERIOD_DRAFT:
            raise PayrollLocked("Kỳ lương đã chốt/đã chi — mở lại trước khi tính lại.")
        # Đồng bộ công chuẩn của kỳ (draft) theo tham số chung mỗi lần tính lại (snapshot mẫu số đã dùng).
        if float(period.standard_cong) != std:
            self.payroll.update_period(period, standard_cong=std)

        on = date(int(year), int(month), 1)
        # Lương/điều chỉnh có hiệu lực TRONG tháng (gán/đổi giữa tháng, vd NV mới vào ngày 17) vẫn
        # áp cho kỳ này → tra mức "hiện hành đến CUỐI tháng", không phải chỉ tính đến ngày 01.
        pay_on = date(int(year), int(month), monthrange(int(year), int(month))[1])
        metrics_map = self.attendance.metrics_map(year, month)   # {emp: {cong, ot_minutes, night_days}}
        # Bảng tra CA → mức cơm/phụ cấp. Nạp MỘT lần cho cả kỳ: `generate` chạy engine cho hàng
        # trăm NV, tra từng người là hàng trăm query lẻ.
        shift_by_id = {s.id: s for s in self.attendance.list_shifts()}
        advance_map = self.payroll.approved_advance_map(year, month, kind=ADV_KIND_TAM_UNG)
        dot1_map = self.payroll.approved_advance_map(year, month, kind=ADV_KIND_LUONG_DOT_1)
        salary_map = self.payroll.latest_salaries_map(pay_on)
        khoan_map = self.piece.khoan_map(year, month) if self.piece is not None else {}
        # Khoán km giao hàng (mg 0231) — nạp MỘT lần cho cả kỳ, cùng khuôn `khoan_map`.
        # Đi qua `self.components.db` vì `PayrollService` không giữ session riêng; khối `try` để
        # phân hệ Giao hàng chưa dựng bảng (unit test dựng DB tối giản) không làm sập cả kỳ lương.
        khoan_km_map: dict[int, float] = {}
        if self.components is not None:
            from .khoan_km_service import KhoanKmService
            try:
                khoan_km_map = KhoanKmService(self.components.db).theo_ky(year, month)
            except Exception:                                   # noqa: BLE001 — xem ghi chú trên
                khoan_km_map = {}
        # Trừ lỗi khoán theo NGƯỜI (Điều 102: gộp vào trần khấu trừ 30%).
        defect_map = self.piece.defect_map(year, month) if self.piece is not None else {}
        brackets = self.get_pit_brackets()
        late_brackets = self.get_late_penalty_brackets()   # phạt đi trễ/về sớm TỰ ĐỘNG (từ chấm công)
        # Tổ khoán (has_piece_work): KHÔNG tính tăng ca theo giờ — khoán đã trả theo sản lượng.
        piece_dept_ids: set[int] = set()
        if self.departments is not None:
            piece_dept_ids = {
                d.id for d in self.departments.list_all()
                if getattr(d, "has_piece_work", False)
            }

        # Các ô tay chi tiết (thưởng/phạt) được HCNS nhập ở "Sửa lương" — preserve khi Tính lại.
        detail_fields = ("thuong_5s", "thuong_doanh_so", "thuong_thanh_tich", "phep_nam",
                         "tra_dong_phuc", "dieu_chinh_luong", "di_tre", "dt_vuot_troi",
                         "phat_bien_ban", "phat_5s_dong_phuc")
        employees = self.employees.list_scoped_all(scope=scope, actor=actor)
        for emp in employees:
            employment_status, employment_department_id = self._employment_context_on(emp, pay_on)
            existing = self.payroll.get_line_by_pe(period.id, emp.id)
            m = metrics_map.get(emp.id) or {}   # NV không chấm công → rỗng (KHÔNG KeyError)
            # Hoa hồng tính TRƯỚC cổng dưới: NV kinh doanh nghỉ việc tháng trước, tháng này
            # mới xuất hoá đơn của đơn họ chốt ⇒ vẫn còn tiền phải trả. Bỏ ra khỏi `has_work` là
            # họ không có dòng lương nào, tiền bốc hơi mà không một dòng cảnh báo.
            hoa_hong_rows = self._hoa_hong_rows(emp.id, period.year, period.month)
            # Khoán km cũng phải nằm TRƯỚC cổng: tài xế nghỉ việc giữa kỳ vẫn còn tiền các
            # chuyến đã chạy. Bỏ ra khỏi `has_work` là họ không có dòng lương nào — cùng bẫy đã
            # cắn với hoa hồng.
            has_work = (bool(m) or emp.id in khoan_map or emp.id in khoan_km_map
                        or existing is not None or bool(hoa_hong_rows))
            # NV nghỉ việc: CHỈ bỏ khi không có công/khoán/dòng lương trong kỳ — còn làm thì vẫn
            # trả lương tháng cuối (không quỵt).
            if employment_status == STATUS_RESIGNED and not has_work:
                continue
            vi_pham = float(existing.vi_pham) if existing else 0.0
            other_bonus = float(existing.other_bonus) if existing else 0.0
            note = existing.note if existing else None
            detail_kw = {k: (float(getattr(existing, k)) if existing else 0.0) for k in detail_fields}
            # Phạt đi trễ/về sớm TỰ ĐỘNG: nếu HCNS CHƯA sửa tay ô này (`di_tre_manual`) → tính từ chấm công
            # (mỗi ngày vi phạm KHÔNG phép tra bảng phạt 1 lần rồi cộng — chủ 2026-07-21). Sửa tay → GIỮ số
            # tay (đã nạp ở detail_kw trên). Mirror cơ chế pit_manual.
            di_tre_manual = bool(existing.di_tre_manual) if existing else False
            if not di_tre_manual:
                detail_kw["di_tre"] = sum(
                    _late_penalty_amount(off, late_brackets) for off in m.get("late_off_days", [])
                )

            salary = salary_map.get(emp.id)
            actual_cong = float(m.get("cong", 0.0))
            ot_minutes = int(m.get("ot_minutes", 0))
            night_days = int(m.get("night_days", 0))
            khoan = khoan_map.get(emp.id, 0.0)
            vals = self._compute(
                employee=emp, salary=salary, params=params, actual_cong=actual_cong,
                standard_cong=std, vi_pham=vi_pham, other_bonus=other_bonus, khoan=khoan,
                khoan_km=float(khoan_km_map.get(emp.id, 0.0)),
                khoan_defect=float(defect_map.get(emp.id, 0.0)),
                # HAI danh sách RIÊNG, đừng nối lại: khoản hồ sơ vào `allowance`, khoản phát sinh
                # thì không (nếu không "Tính lại" rồi sửa một ô là cộng đôi — xem `_compute`).
                components=self._components_for(emp),
                # Khoản thêm tay (Tầng 3) + hoa hồng hệ tự tính (nguồn `auto`). Nối vào ĐÂY chứ
                # không vào `components`: `components` chảy vào `allowance`, mà hoa hồng đổi theo
                # TỪNG KỲ nên không thuộc về hồ sơ nhân viên.
                line_components=(self._line_extra_components(existing.id if existing else None)
                                 + hoa_hong_rows),
                ot_minutes=ot_minutes, night_days=night_days,
                holiday_cong=float(m.get("holiday_cong", 0.0)),
                restday_cong=float(m.get("restday_cong", 0.0)),
                plain_cong=float(m.get("plain_cong", 0.0)),
                paid_leave_cong=float(m.get("paid_leave_days", 0.0)),
                excused_cong=float(m.get("excused_cong", 0.0)),
                ot_holiday_minutes=int(m.get("ot_holiday_minutes", 0)),
                ot_restday_minutes=int(m.get("ot_restday_minutes", 0)),
                night_premium_minutes=float(m.get("night_premium_minutes", 0.0)),
                ot_night_normal_minutes=int(m.get("ot_night_normal_minutes", 0)),
                ot_night_restday_minutes=int(m.get("ot_night_restday_minutes", 0)),
                ot_night_holiday_minutes=int(m.get("ot_night_holiday_minutes", 0)),
                ca_lam=m.get("ca_lam") or {},
                ot_days=m.get("ot_days") or {},
                shift_by_id=shift_by_id,
                has_piece_work=(employment_department_id in piece_dept_ids),
                brackets=brackets, on=on,
                employee_status=employment_status,
                department_id=employment_department_id,
                **detail_kw,
            )
            # TNCN: GIỮ số HCNS đã ghi đè tay (pit_manual); ngược lại dùng số tự tính.
            if existing is not None and existing.pit_manual:
                pit_eff, pit_manual = float(existing.pit), True
            else:
                pit_eff, pit_manual = vals["pit"], False
            advance_total = _round(advance_map.get(emp.id, 0.0))
            luong_dot_1_total = _round(dot1_map.get(emp.id, 0.0))
            # Sàn 0: thực nhận (đợt 2) không bao giờ âm. Trừ cả tạm ứng LẪN lương đợt 1 đã trả giữa tháng.
            net = max(0.0, vals["gross"] - vals["bhxh"] - vals["cong_doan"] - pit_eff
                      - advance_total - luong_dot_1_total - vals.get("component_deduct", 0.0))

            fields = dict(
                is_probation=vals["is_probation"], actual_cong=actual_cong, standard_cong=std,
                monthly_salary=vals["monthly_salary"], luong_cong=vals["luong_cong"],
                luong_ngay_phep=vals["luong_ngay_phep"], special_cong=vals["special_cong"],
                off1x_pay=vals["off1x_pay"],
                paid_leave_cong=vals["paid_leave_cong"], excused_cong=vals["excused_cong"],
                chuyen_can=vals["chuyen_can"], allowance=vals["allowance"],
                phu_cap_tham_nien=vals["phu_cap_tham_nien"], khoan=vals["khoan"],
                khoan_km=vals["khoan_km"],
                ot_minutes=vals["ot_minutes"], ot_pay=vals["ot_pay"],
                night_days=vals["night_days"], night_pay=vals["night_pay"],
                night_premium_pay=vals["night_premium_pay"],
                meal_allowance_pay=vals["meal_allowance_pay"],
                com_tang_ca_pay=vals["com_tang_ca_pay"],
                shift_allowance_pay=vals["shift_allowance_pay"],
                vi_pham=vals["vi_pham"], other_bonus=vals["other_bonus"], gross=vals["gross"],
                insurance_base=vals["insurance_base"], bhxh=vals["bhxh"], cong_doan=vals["cong_doan"],
                pit=pit_eff, pit_manual=pit_manual, pit_taxable=vals["pit_taxable"],
                thu_nhap_chiu_thue=vals["thu_nhap_chiu_thue"],
                thu_nhap_mien_thue=vals["thu_nhap_mien_thue"],
                advance_total=advance_total, luong_dot_1_total=luong_dot_1_total,
                net_pay=_round(net), note=note,
                thuong_5s=vals["thuong_5s"], thuong_doanh_so=vals["thuong_doanh_so"],
                thuong_thanh_tich=vals["thuong_thanh_tich"], phep_nam=vals["phep_nam"],
                tra_dong_phuc=vals["tra_dong_phuc"], dieu_chinh_luong=vals["dieu_chinh_luong"],
                di_tre=vals["di_tre"], di_tre_manual=di_tre_manual, dt_vuot_troi=vals["dt_vuot_troi"],
                phat_bien_ban=vals["phat_bien_ban"], phat_5s_dong_phuc=vals["phat_5s_dong_phuc"],
                updated_at=datetime.now(timezone.utc),
            )
            if existing:
                self.payroll.update_line(existing, **fields)
                line = existing
            else:
                line = self.payroll.create_line(period_id=period.id, employee_id=emp.id, **fields)
            # Hoa hồng: ghi lại thành khoản nguồn `auto` — xoá sạch rồi ghi mới mỗi lần tính
            # lại, vì số chạy theo hoá đơn phát sinh thêm. KHÔNG đụng nguồn `line` (thưởng thêm
            # tay) lẫn `employee` (khoản hồ sơ).
            if self.components is not None:
                self.components.replace_auto_line_components(line.id, hoa_hong_rows)

            # SNAPSHOT từng khoản lên dòng lương: phiếu lương in được từng dòng, và đổi cờ
            # "Chịu thuế" ở danh mục về sau KHÔNG sửa số của kỳ này.
            if self.components is not None:
                comp_rows = self._components_for(emp)
                # ⚠️ BỎ QUA khoản đã có dòng ĐÈ TAY trên dòng lương này. `replace_...` đã chừa
                # dòng đè ra khi xoá, nên nếu ở đây vẫn ghi lại khoản đó thì mỗi lần "Tính lại"
                # sinh THÊM MỘT DÒNG NỮA và NV ăn tiền hai lần. Hai vế phải đi cùng nhau.
                da_de = {int(r.component_id) for r in self.components.line_components(line.id)
                         if getattr(r, "da_de_tay", False)}
                self.components.replace_employee_line_components(line.id, [
                    {"component_id": c["component_id"], "code": c["code"], "name": c["name"],
                     "kind": c["kind"], "is_taxable": c["is_taxable"], "amount": c["amount"],
                     "note": c.get("note")}
                    for c in comp_rows if int(c["component_id"]) not in da_de
                ])
                self.components.commit()
        # Đóng dấu "engine vừa chạy xong" — cột này là thứ DUY NHẤT phân biệt "đã tính lại" với
        # "có người sửa tay một ô thưởng" (xem chú thích ở `PayrollPeriod.generated_at`).
        # Đặt Ở CUỐI, sau khi mọi dòng đã ghi: đặt ở đầu mà giữa chừng vỡ là dấu nói dối.
        self.payroll.update_period(period, generated_at=datetime.now(timezone.utc))
        self._audit(actor, "payroll_generate", f"payroll_period:{period.id}", f"{int(month)}/{int(year)}")
        return period

    def nv_duoc_xem(self, *, scope, actor) -> set[int] | None:
        """Tập `employee_id` người gọi được xem theo PHẠM VI. None = không giới hạn (Tất cả).

        LỖ HỔNG ĐÃ ĐO 15/08/2026: bảng lương trả về MỌI dòng của kỳ, chỉ hỏi "có ô Xem Lương
        không" mà không hỏi "quản ai". Cấp ô Xem Lương với phạm vi *Của tôi* thì người đó vẫn đọc
        được lương của cả công ty, gồm cả giám đốc. Đúng căn bệnh tester ghi ở đợt rà soát lần 1:
        *"Phạm vi của tôi nhưng xem được tất cả"*.

        Dùng lại `list_scoped_all` — CÙNG một nguồn phạm vi với Chấm công, Nghỉ phép, Tăng ca.
        Tự viết điều kiện lọc thứ hai ở đây là hai nơi hiểu "cả phòng" theo hai kiểu."""
        if scope is None or scope == SCOPE_ALL:
            return None
        return {e.id for e in self.employees.list_scoped_all(scope=scope, actor=actor)}

    def get_table(self, *, year, month, scope=None, actor=None):
        """Kỳ lương + các dòng (kèm thông tin NV) cho FE. None nếu chưa tạo.

        `scope`/`actor` = phạm vi của NGƯỜI XEM. Bỏ trống (mặc định) = không lọc — chỉ dùng cho
        đường nội bộ đã tự gác; mọi endpoint phơi ra ngoài PHẢI truyền vào."""
        period = self.payroll.get_period_by_ym(year, month)
        if period is None:
            return None
        lines = self.payroll.list_lines(period.id)
        duoc_xem = self.nv_duoc_xem(scope=scope, actor=actor)
        if duoc_xem is not None:
            lines = [ln for ln in lines if ln.employee_id in duoc_xem]
        return {"period": period, "lines": lines}

    def chan_ngoai_pham_vi(self, *, employee_id: int, scope, actor) -> None:
        """Chặn đụng vào dòng lương của người NGOÀI phạm vi. Dùng cho các đường đi thẳng theo
        `line_id` — ở đó không có danh sách để lọc, phải hỏi từng lần."""
        duoc_xem = self.nv_duoc_xem(scope=scope, actor=actor)
        if duoc_xem is not None and int(employee_id) not in duoc_xem:
            raise PayrollForbidden(
                "Dòng lương này thuộc người ngoài phạm vi quản lý của bạn."
            )

    def _khoan_defect_for(self, period, employee_id) -> float:
        """Trừ lỗi hàng khoán của NV trong kỳ (Đ102: gộp vào trần khấu trừ 30%). Đọc LẠI từ sổ
        khoán để "Sửa 1 ô" ra CÙNG số với "Tính lại" (trước đây update_line bỏ qua khoản này)."""
        defect_map = getattr(self.piece, "defect_map", None) if self.piece is not None else None
        if defect_map is None or period is None:
            return 0.0
        return float(defect_map(period.year, period.month).get(employee_id, 0.0))

    # --- Tầng 3: khoản PHÁT SINH cho riêng một kỳ (thưởng nóng) --------------

    def _line_for_edit(self, line_id: int, *, scope=None, actor=None):
        ln = self.payroll.get_line(line_id)
        if ln is None:
            raise PayrollNotFound("Không tìm thấy dòng lương.")
        period = self.payroll.get_period(ln.period_id)
        if period is None or period.status != PERIOD_DRAFT:
            raise PayrollLocked("Kỳ lương đã chốt/đã chi — không sửa được.")
        # PHẠM VI (15/08/2026): gác ở ĐÂY vì cả 4 đường sửa dòng lương đều đi qua hàm này —
        # sửa dòng, thêm/sửa/bỏ đè/xoá khoản phát sinh. Gác ở từng endpoint là bốn chỗ để quên.
        self.chan_ngoai_pham_vi(employee_id=ln.employee_id, scope=scope, actor=actor)
        return ln

    def list_line_components(self, *, line_id: int, scope=None, actor=None) -> list:
        ln = self.payroll.get_line(line_id)
        if ln is None:
            raise PayrollNotFound("Không tìm thấy dòng lương.")
        # Khoản phát sinh của một người là tiền của người đó — cùng hàng rào phạm vi với bảng lương.
        self.chan_ngoai_pham_vi(employee_id=ln.employee_id, scope=scope, actor=actor)
        return self.components.line_components(line_id) if self.components else []

    def chi_tiet_khoan_km(self, *, line_id: int, scope=None, actor=None) -> list[dict]:
        """Từng chuyến giao đã sinh ra tiền khoán km của dòng lương này (mg 0231).

        ⭐ Vì sao phải có: km là TÀI XẾ TỰ GÕ. Khác hẳn hoa hồng — nguồn của hoa hồng là hoá đơn
        kế toán đã xuất, đã qua tay người khác. Không cho HCNS soi lại từng chuyến thì khoán km
        thành tiền tự khai, và cuối tháng không ai đối chiếu được với sổ tài xế.

        Cùng hàng rào phạm vi với bảng lương: tiền của một người là dữ liệu của người đó.
        """
        ln = self.payroll.get_line(line_id)
        if ln is None:
            raise PayrollNotFound("Không tìm thấy dòng lương.")
        self.chan_ngoai_pham_vi(employee_id=ln.employee_id, scope=scope, actor=actor)
        ky = self.payroll.get_period(ln.period_id)
        if ky is None or self.components is None:
            return []
        from .khoan_km_service import KhoanKmService
        return KhoanKmService(self.components.db).chi_tiet(ln.employee_id, ky.year, ky.month)

    def add_line_component(self, *, actor, line_id: int, component_id: int, amount: float, scope=None,
                           note: str | None = None):
        """Thêm khoản chỉ có ở KỲ NÀY. Chép `name`/`kind`/`is_taxable` từ danh mục tại thời điểm
        thêm — kỳ sau đổi danh mục thì dòng này vẫn giữ đúng số đã trả."""
        ln = self._line_for_edit(line_id, scope=scope, actor=actor)
        c = self.components.get_component(component_id) if self.components else None
        if c is None:
            raise PayrollValidationError(
                "Khoản này không có trong danh mục. Tạo ở Cấu hình lương → Danh mục khoản "
                "thu nhập trước."
            )
        if float(amount) < 0:
            raise PayrollValidationError("Số tiền không được âm.")
        row = self.components.add_line_component(
            line_id=line_id, component_id=c.id, code=c.code, name=c.name, kind=c.kind,
            is_taxable=bool(c.is_taxable), amount=float(amount), note=(note or None))
        self._recompute_line(ln, actor)
        self._audit(actor, "add_line_component", f"payroll_line:{line_id}",
                    f"{c.name} {float(amount):,.0f}đ — {note or ''}")
        return row

    def update_line_component(self, *, actor, row_id: int, amount=None, note=None, scope=None):
        row = self.components.get_line_component(row_id) if self.components else None
        if row is None:
            raise PayrollNotFound("Không tìm thấy khoản trên dòng lương.")
        # Dòng HỆ TỰ TÍNH (hoa hồng KD) KHÔNG cho gõ tay.
        #
        # Đã mở ra rồi ĐÓNG LẠI trong cùng ngày 24/08/2026. Chủ thử xong chốt: *"số tiền hoa hồng
        # ấy đừng cho sửa tay nữa, kệ nó ăn theo đơn hàng cho chắc"*. Đúng: cho đè tay thì kỳ đó
        # thôi chạy theo hoá đơn — kế toán xuất thêm hoá đơn sau, tiền không tự cộng, và không ai
        # nhớ ra để sửa lại. Số bám hoá đơn thì luôn đối chiếu được với sổ bán hàng.
        #
        # Cần trả thêm/bớt cho một người ⇒ dùng khoản "Thu nhập khác", đúng chỗ và có ghi chú.
        if row.source == COMPONENT_SOURCE_AUTO:
            raise PayrollValidationError(
                "Hoa hồng do hệ thống tự tính theo hoá đơn bán trong kỳ — không sửa tay ở đây. "
                "% của đơn được chốt cứng lúc CHỐT ĐƠN theo hồ sơ lương của nhân viên, nên đơn đã "
                "chốt thì không nắn lại được: cần trả thêm/bớt thì dùng khoản \"Thu nhập khác\". "
                "Muốn đổi % cho các đơn SAU thì sửa ở Lương → Thiết lập lương."
            )
        ln = self._line_for_edit(row.line_id, scope=scope, actor=actor)
        fields = {}
        if amount is not None:
            if float(amount) < 0:
                raise PayrollValidationError("Số tiền không được âm.")
            fields["amount"] = float(amount)
            # ĐÈ CHO RIÊNG KỲ NÀY (chủ chốt 12/08/2026): "gán Hỗ trợ chi phí đi lại, nhưng tháng
            # này nó đi nhiều hơn thì sửa thế nào?". Trước đó chặn thẳng, vì dòng chép từ hồ sơ bị
            # xoá-ghi-lại mỗi lần "Tính lại" ⇒ sửa xong là mất số âm thầm.
            # Nay đánh dấu để `replace_employee_line_components` và `generate` cùng chừa nó ra.
            # HỒ SƠ KHÔNG ĐỔI — tháng sau tự về mức cũ, không phải nhớ sửa ngược.
            if row.source != COMPONENT_SOURCE_LINE:
                fields["da_de_tay"] = True
        if note is not None:
            fields["note"] = note or None
        if fields:
            self.components.update_line_component(row, **fields)
            self._recompute_line(ln, actor)
        self._audit(actor, "update_line_component", f"payroll_line:{row.line_id}", row.name)
        return row

    def bo_de_line_component(self, *, actor, row_id: int, scope=None):
        """Trả một khoản đã đè về ĐÚNG SỐ Ở HỒ SƠ, ngay lập tức.

        Không chỉ tắt cờ rồi chờ "Tính lại": người bấm "Trả về theo hồ sơ" muốn thấy số cũ NGAY.
        Đọc lại mức hồ sơ theo `component_id` — khoản đã bị gỡ khỏi hồ sơ thì xoá luôn dòng, vì
        giữ lại là trả một khoản NV không còn được hưởng."""
        row = self.components.get_line_component(row_id) if self.components else None
        if row is None:
            raise PayrollNotFound("Không tìm thấy khoản trên dòng lương.")
        if row.source == COMPONENT_SOURCE_LINE:
            raise PayrollValidationError(
                "Khoản phát sinh do người dùng thêm tay — không có 'mức hồ sơ' để trả về. "
                "Sửa thẳng số tiền, hoặc xoá dòng."
            )
        # KHÔNG cần nhánh cho `auto`: dòng hệ tự tính không sửa tay được (xem
        # `update_line_component`) nên không bao giờ mang cờ `da_de_tay`, tức nút "Trả về" không
        # bao giờ hiện cho nó. Thêm nhánh phòng xa ở đây là code không đường nào chạy tới.
        ln = self._line_for_edit(row.line_id, scope=scope, actor=actor)
        emp = self.employees.get_by_id(ln.employee_id)
        goc = next((c for c in (self._components_for(emp) if emp else [])
                    if int(c["component_id"]) == int(row.component_id)), None)
        if goc is None:
            self.components.delete_line_component(row)
            self._recompute_line(ln, actor)
            self._audit(actor, "delete_line_component", f"payroll_line:{ln.id}",
                        f"{row.name} (hồ sơ không còn khoản này)")
            return None
        self.components.update_line_component(row, amount=float(goc["amount"]), da_de_tay=False)
        self._recompute_line(ln, actor)
        self._audit(actor, "bo_de_line_component", f"payroll_line:{ln.id}", row.name)
        return row

    def delete_line_component(self, *, actor, row_id: int, scope=None) -> None:
        row = self.components.get_line_component(row_id) if self.components else None
        if row is None:
            raise PayrollNotFound("Không tìm thấy khoản trên dòng lương.")
        if row.source == COMPONENT_SOURCE_AUTO:
            # Báo cho ĐÚNG chỗ: câu dưới chỉ sang "Lương nhân viên", mà hoa hồng không nằm ở đó —
            # HCNS sẽ đi tìm mỏi mắt. Mà có gỡ được cũng vô nghĩa: "Tính lại" là nó mọc lại.
            raise PayrollValidationError(
                "Hoa hồng do hệ thống tự tính theo hoá đơn bán trong kỳ — gỡ ở đây không có tác "
                "dụng, tính lại là hiện lại. Không muốn tính nữa thì bỏ % hoa hồng của nhân viên "
                "ở Lương → Thiết lập lương (chỉ ăn vào đơn chốt từ đó trở đi), hoặc huỷ hoá đơn."
            )
        if row.source != COMPONENT_SOURCE_LINE:
            raise PayrollValidationError(
                "Khoản chép từ hồ sơ nhân viên không gỡ được ở đây — gỡ ở Lương → Lương nhân viên."
            )
        ln = self._line_for_edit(row.line_id, scope=scope, actor=actor)
        name = row.name
        self.components.delete_line_component(row)
        self._recompute_line(ln, actor)
        self._audit(actor, "delete_line_component", f"payroll_line:{row.line_id}", name)

    def _recompute_line(self, ln, actor) -> None:
        """Tính lại tổng của MỘT dòng sau khi khoản phát sinh đổi.

        Dùng lại đúng đường `update_line` (KHÔNG chép công thức ra chỗ thứ hai) — bệnh "Sửa 1 ô ra
        số khác Tính lại" đã tái phát nhiều lần ở file này."""
        self.update_line(line_id=ln.id, actor=actor)

    def update_line(self, *, line_id, actor, scope=None, vi_pham=None, pit=None,
                    pit_manual=None, di_tre_manual=None, monthly_override=None, note=None,
                    dieu_chinh_luong=None, di_tre=None, dt_vuot_troi=None,
                    phat_bien_ban=None, phat_5s_dong_phuc=None):
        """Sửa ô tay 1 dòng (chỉ khi kỳ draft) → tính lại gross/TNCN/net.

        ⚠️ KHÔNG nhận khoản thưởng nữa (`thuong_5s`, `other_bonus`…): từ 28/07/2026 thưởng khai
        qua danh mục (`add_line_component`). Các cột cũ vẫn ĐƯỢC CỘNG ở dưới để kỳ đã chốt giữ
        nguyên số — chỉ không ghi mới."""
        ln = self.payroll.get_line(line_id)
        if ln is None:
            raise PayrollNotFound("Không tìm thấy dòng lương.")
        period = self.payroll.get_period(ln.period_id)
        if period is None or period.status != PERIOD_DRAFT:
            raise PayrollLocked("Kỳ lương đã chốt/đã chi — không sửa được.")

        if vi_pham is not None:
            ln.vi_pham = _round(vi_pham)
        # Ô tay chi tiết (phạt + điều chỉnh). dieu_chinh_luong cho phép ÂM.
        for attr, val in (("dieu_chinh_luong", dieu_chinh_luong),
                          ("di_tre", di_tre), ("dt_vuot_troi", dt_vuot_troi),
                          ("phat_bien_ban", phat_bien_ban), ("phat_5s_dong_phuc", phat_5s_dong_phuc)):
            if val is not None:
                setattr(ln, attr, _round(val))
        # Phạt đi trễ/về sớm: `di_tre_manual=False` = ĐƯA VỀ TỰ ĐỘNG (tính lại từ chấm công NGAY);
        # HCNS gõ tay ô `di_tre` → khóa `di_tre_manual=True` (không cho Tính lại đè). Mirror pit_manual.
        if di_tre_manual is False:
            m_off = self.attendance.metrics_map(period.year, period.month).get(ln.employee_id) or {}
            lbk = self.get_late_penalty_brackets()
            ln.di_tre = _round(sum(_late_penalty_amount(off, lbk) for off in m_off.get("late_off_days", [])))
            ln.di_tre_manual = False
        elif di_tre is not None:
            ln.di_tre_manual = True
        if monthly_override is not None:
            # sửa tay mức tháng → tính lại lương công theo tỷ lệ công hiện có (chặn trần công).
            # PHẢI dùng chung `_luong_cong_split` với `_compute`, nếu không "Sửa 1 ô" sẽ xoá phần
            # tách ngày phép và ra số khác "Tính lại" (bệnh đã tái phát nhiều lần ở file này).
            ln.monthly_salary = _round(monthly_override)
            std = float(ln.standard_cong) or 1.0
            leave_cong = float(getattr(ln, "paid_leave_cong", 0) or 0)
            # ✅ GỠ 17/08/2026 — trước đây phải suy ngược `vi_tri_rate` từ `luong_ngay_phep` cũ
            # chia `paid_leave_cong` cũ, vì ngày phép ăn đơn giá KHÁC (chỉ lương vị trí). Phép suy
            # đó là lỗi #1b ở `CONG_THUC_TINH_LUONG.md` Phần 14: đổi mức tháng KHÔNG đổi đơn giá
            # ngày phép. Nay ngày phép ăn CÙNG mức nền nên không còn gì để suy — lỗi tự hết.
            old_monthly = float(ln.monthly_salary) or 1.0
            lc, lnp, eff = _luong_cong_split(
                eff_monthly=old_monthly, std=std,
                actual_cong=float(ln.actual_cong), paid_leave_cong=leave_cong,
                # Công lễ/CN KHÔNG qua trần — phải truyền y hệt `_compute`, nếu không "Sửa 1 ô"
                # sẽ trả lại đúng cái lỗi trần nuốt gốc mà mg 0204 vừa vá. Kỳ cũ = 0 ⇒ số không đổi.
                special_cong=float(getattr(ln, "special_cong", 0) or 0),
            )
            ln.luong_cong = _round(lc)
            ln.luong_ngay_phep = _round(lnp)
            ln.paid_leave_cong = round(eff, 2)
        if note is not None:
            ln.note = note

        # Khoản danh mục trên dòng này (Tầng 3). Đọc từ SNAPSHOT nên gồm cả phần chép từ hồ sơ
        # lẫn khoản phát sinh thêm tay — một nguồn duy nhất, không double-count.
        #   `ln.allowance` đã gồm phần `source='employee'` (chốt lúc Tính lại) ⇒ chỉ cộng thêm
        #   phần `source='line'`; còn khấu trừ và phần miễn thuế thì tính trên TOÀN BỘ.
        comps = self.components.line_components(ln.id) if self.components else []
        extra_thu = sum(float(c.amount) for c in comps
                        if c.kind != "tru" and c.source == COMPONENT_SOURCE_LINE)
        comp_deduct = sum(float(c.amount) for c in comps if c.kind == "tru")
        comp_exempt = sum(float(c.amount) for c in comps
                          if c.kind != "tru" and not c.is_taxable)
        # Phần MIỄN thuế KHÔNG đến từ danh mục: tăng ca + ca đêm + cơm ca + phụ cấp ca.
        # Phải đặt TRƯỚC `_apply_auto_pit` — hàm đó đọc `thu_nhap_mien_thue` để trừ ra khỏi
        # thu nhập chịu thuế (nó tự suy phần danh mục = snapshot − OT/đêm, nên cơm/phụ cấp ca rơi
        # vào vế "danh mục" của nó và vẫn được miễn đúng; không phải sửa hàm đó).
        ca_mien = (float(getattr(ln, "meal_allowance_pay", 0) or 0)
                   + float(getattr(ln, "shift_allowance_pay", 0) or 0)
                   # Cơm tăng ca cũng miễn thuế — sót ở ĐÂY thì "Sửa 1 ô" tính thuế trên cả khoản
                   # đáng ra được miễn, còn "Tính lại" thì không. Hai đường lệch nhau, im lặng.
                   + float(getattr(ln, "com_tang_ca_pay", 0) or 0))
        mien_ngoai_danh_muc = (float(ln.ot_pay or 0) - float(getattr(ln, "off1x_pay", 0) or 0)
                               + float(ln.night_pay or 0)
                               + float(getattr(ln, "night_premium_pay", 0) or 0) + ca_mien)
        ln.thu_nhap_mien_thue = _round(mien_ngoai_danh_muc + comp_exempt)

        # Lương TRƯỚC khấu trừ kỷ luật (gồm các khoản thưởng chi tiết) → TNCN tính trên số này.
        # ⚠️ PHẢI khớp 1-1 với `gross_pre` của `_compute`. Thiếu một số hạng ở đây là "Sửa 1 ô"
        # ăn mất tiền của người lao động mà bảng lương vẫn trông bình thường — `ca_mien` (cơm ca +
        # phụ cấp ca) đã từng bị sót đúng kiểu đó, giống bệnh cũ của `khoan_defect` và
        # `component_deduct`. Thêm số hạng mới vào `_compute` thì thêm CẢ ở đây.
        gross_pre = _round(extra_thu + float(ln.luong_cong) + float(ln.chuyen_can) + float(ln.allowance)
                           + float(ln.khoan) + float(getattr(ln, "khoan_km", 0) or 0)
                           + float(ln.ot_pay) + float(ln.night_pay)
                           + float(getattr(ln, "night_premium_pay", 0) or 0)
                           + ca_mien
                           + float(ln.other_bonus)
                           + float(ln.thuong_5s) + float(ln.thuong_doanh_so)
                           + float(ln.thuong_thanh_tich) + float(ln.phep_nam)
                           + float(ln.tra_dong_phuc) + float(ln.dieu_chinh_luong))
        ln.gross = gross_pre
        ln.thu_nhap_chiu_thue = _round(max(0.0, gross_pre - mien_ngoai_danh_muc - comp_exempt))
        # ĐOÀN PHÍ — PHẢI TÍNH TRƯỚC KHỐI TNCN. Từ 12/08/2026 thuế TRỪ đoàn phí, nên thứ tự này
        # là bắt buộc: để nguyên chỗ cũ (sau TNCN) thì thuế ăn số đoàn phí CŨ và "Sửa 1 ô" ra khác
        # "Tính lại". Công thức chép ĐÚNG `_compute`: insurance_base × tỷ lệ.
        #
        sal_cd = self.payroll.current_salary(ln.employee_id, date.today())
        la_doan_vien = bool(getattr(sal_cd, "union_member", False)) if sal_cd else False
        ln.cong_doan = 0.0 if (ln.is_probation or not la_doan_vien) else _round(
            float(ln.insurance_base) * float(getattr(self.get_params(), "cong_doan_rate", 0) or 0))

        # TNCN: reset về tự tính (pit_manual=False) / ghi đè tay (pit) / else cập nhật auto theo gross mới.
        if pit_manual is False:
            self._apply_auto_pit(ln)
            ln.pit_manual = False
        elif pit is not None:
            ln.pit = _round(pit)
            ln.pit_manual = True
        elif not ln.pit_manual:
            self._apply_auto_pit(ln)
        # Điều 102: GỘP tất cả phạt chi tiết + vi_pham + trừ lỗi khoán CHUNG 1 trần 30% — DÙNG
        # CHUNG `_capped_penalty` với `_compute` (LƯU RAW từng cột, không capped).
        phat_total = (float(ln.vi_pham) + float(ln.di_tre) + float(ln.dt_vuot_troi)
                      + float(ln.phat_bien_ban) + float(ln.phat_5s_dong_phuc))
        phat_eff = _capped_penalty(
            gross_pre=gross_pre, bhxh=float(ln.bhxh), pit=float(ln.pit), phat_total=phat_total,
            khoan_defect=self._khoan_defect_for(period, ln.employee_id),
            # PHẢI truyền y hệt `_compute`, nếu không "Sửa 1 ô" và "Tính lại" ra hai số khác nhau.
            cap_pct=getattr(self.get_params(), "phat_cap_pct", 0.30),
        )
        ln.gross = max(0.0, _round(gross_pre - phat_eff))   # sàn 0 — xem ghi chú ở `_compute`
        # `comp_deduct` = khoản danh mục loại TRỪ. v1 quên trừ ở đường "Sửa 1 ô" ⇒ sửa một ô là
        # khấu trừ biến mất, ra số khác "Tính lại".
        ln.net_pay = _round(max(0.0, float(ln.gross) - float(ln.bhxh) - float(ln.cong_doan)
                                - float(ln.pit) - float(ln.advance_total)
                                - float(getattr(ln, "luong_dot_1_total", 0) or 0)
                                - comp_deduct))
        ln.updated_at = datetime.now(timezone.utc)
        saved = self.payroll.update_line(ln)
        self._audit(actor, "payroll_update_line", f"payroll_line:{ln.id}", "sửa ô tay")
        return saved

    def ly_do_chua_chot_duoc(self, year: int, month: int) -> str | None:
        """Vì sao CHƯA chốt được bảng lương tháng này. `None` = chốt được.

        NGUỒN DUY NHẤT của luật: `lock_period` hỏi để chặn, `GET /table` hỏi để giao diện tắt nút
        + hiện băng cảnh báo. Trả thẳng CÂU CHỮ chứ không trả cờ bool, vì số lý do sẽ còn tăng —
        mỗi lý do thêm một bool là giao diện phải if/else lại từ đầu, và câu chữ trôi khác nhau
        giữa hai nơi. Máy chủ nói một câu, màn hình chỉ việc hiện.

        HAI LÝ DO HIỆN CÓ, cả hai đều là mắt xích của vòng khoá công ⇄ lương:

        **L1 — kỳ công chưa chốt.** Trước 12/08/2026 chuỗi chỉ chặn chiều LÙI (lương đã chốt thì
        không mở lại kỳ công); chiều ĐI TẮT bỏ ngỏ — tính lương → chốt → chi tiền mà kỳ công chưa
        từng chốt, tức lương chạy trên số LIVE, và số live vẫn sửa được SAU KHI TIỀN ĐÃ RA.

        **L8 — ảnh chụp đã cũ so với thực tế.** Kỳ công chốt rồi mà thợ vẫn bấm tiếp (chấm công
        GPS KHÔNG hỏi kỳ công — cố ý, chặn thợ đi làm thật vì lý do sổ sách là sai vai). Chốt lương
        lúc này là đóng băng một tấm ảnh đã thiếu.

        **L11 — còn phiếu tạm ứng treo.** Tiền mặt ĐÃ RA khỏi két mà chưa được ghi vào lương.
        Không có ảnh chụp nào che chỗ này: số tạm ứng nướng thẳng vào dòng lương lúc "Tính lại".

        **L4 — bảng lương cũ hơn ảnh chụp.** Kẽ hở còn lại của L1::

            9h tính lương → 10h ai đó chấm bù → 11h chốt công → 12h chốt lương

        Dòng lương lúc 12h VẪN là số của 9h. KHÔNG tự tính lại hộ ở bước chốt: tự tính lại là khoá
        con số mà HCNS chưa từng nhìn thấy. Bắt họ bấm "Tính lại" rồi tự đọc lại.

        Mốc miễn trừ (`AP_DUNG_CHOT_CONG_TRUOC_TU`) tính sẵn ở đây, giao diện không chép lại luật.
        """
        year, month = int(year), int(month)

        # L11 đứng NGOÀI mốc miễn trừ, khác mọi lý do còn lại. Mốc đó sinh ra vì tháng cũ không có
        # dòng kỳ công nào để mà chốt — áp ngược là khoá chết những kỳ lương cũ. Tạm ứng thì không
        # dính gì tới chuỗi chốt công: nó là tiền mặt đã ra khỏi két, tháng nào cũng đúng, và luôn
        # gỡ được bằng một cú duyệt/từ chối chứ không phải đi lục đơn từ đời nào.
        treo = self.payroll.count_pending_advances_in_period(year, month)
        if treo:
            return (f"Còn {treo} phiếu tạm ứng tháng {month:02d}/{year} chưa duyệt — duyệt hoặc "
                    "từ chối hết rồi bấm “Tính lại”, nếu không khoản đã ứng sẽ không được trừ vào "
                    "lương tháng này.")

        if (year, month) < AP_DUNG_CHOT_CONG_TRUOC_TU or self.attendance is None:
            return None

        chot_luc = self.attendance.ky_cong_chot_luc(year, month)
        if chot_luc is None:
            return (f"Kỳ công {month:02d}/{year} chưa chốt — số công còn sửa được thì chưa khoá "
                    "bảng lương. Sang màn Chấm công → Bảng công tháng → Chốt kỳ công trước.")

        # L8 — kỳ công ĐÃ chốt nhưng thực tế vẫn chạy tiếp sau đó.
        # Chốt công là CHỤP ẢNH bảng công; Lương đọc ảnh. Lượt bấm ghi vào sau lúc chụp KHÔNG có
        # trong ảnh ⇒ chốt lương lúc này là đóng băng một tấm ảnh đã thiếu.
        # Hay gặp nhất: chốt công vào CHIỀU ngày cuối tháng — phần đuôi ngày hôm đó và trọn ca đêm
        # bấm sau lúc chốt, tháng nào cũng lặp lại.
        # Màn Chấm công đã có dải cảnh báo cho chuyện này (L3), nhưng nó chỉ NÓI và nói ở màn
        # khác; người chốt lương không nhìn thấy. Đây là đầu CHẶN.
        sau_chot = self.attendance.so_luot_bam_sau_chot(year, month)
        if sau_chot:
            return (f"Kỳ công {month:02d}/{year} đã chốt nhưng có {sau_chot} lượt bấm ghi vào SAU "
                    "lúc chốt — ảnh chụp không có mấy lượt đó nên bảng lương cũng chưa tính. "
                    "Sang màn Chấm công mở lại kỳ công rồi chốt lại, sau đó bấm “Tính lại”.")

        period = self.payroll.get_period_by_ym(year, month)
        if period is None:
            return None          # chưa có bảng lương thì cũng chưa có gì để chốt
        tinh_luc = getattr(period, "generated_at", None)
        if tinh_luc is None or _as_utc(tinh_luc) < chot_luc:
            return (f"Bảng lương đang là số tính TRƯỚC lúc chốt kỳ công {month:02d}/{year} — "
                    "bấm “Tính lại” rồi mới chốt, nếu không là khoá con số đã lạc hậu.")

        # L7 — có người ĂN LƯƠNG mà KHÔNG có trong ảnh chụp kỳ công.
        # Ảnh chụp lấy danh sách NV tại THỜI ĐIỂM chốt công. Hồ sơ nhập sau đó (HCNS vào sổ muộn
        # cho người đã đi làm cả tháng) không có dòng nào ⇒ `metrics_map` rỗng ⇒ 0 công ⇒ tháng đó
        # họ mất trắng. Chặn ở đây vì đường sửa DUY NHẤT là mở lại rồi chốt lại kỳ công — Tính lại
        # bao nhiêu lần cũng không sinh thêm dòng vào ảnh chụp.
        thieu = self._nguoi_thieu_trong_anh_chup(period, year, month)
        if thieu:
            ten = ", ".join(thieu[:3]) + (f" và {len(thieu) - 3} người nữa" if len(thieu) > 3 else "")
            return (f"{len(thieu)} người có bảng lương nhưng KHÔNG có trong ảnh chụp kỳ công "
                    f"{month:02d}/{year} nên đang tính 0 công ({ten}). Hồ sơ vào sổ sau lúc chốt "
                    "công — mở lại kỳ công rồi chốt lại, sau đó Tính lại bảng lương.")
        return None

    def _nguoi_thieu_trong_anh_chup(self, period, year: int, month: int) -> list[str]:
        """Tên những NV có dòng lương mà ảnh chụp kỳ công không có.

        LỌC THEO `hire_date`: người tuyển tháng SAU vẫn có thể đã nằm trong hồ sơ và được
        `generate` sinh dòng 0 công — họ vắng mặt trong ảnh chụp là ĐÚNG, không phải lỗi. Bỏ bộ
        lọc này là chặn nhầm mỗi lần HCNS nhập trước hồ sơ người sắp vào làm."""
        co_trong_anh = set(self.attendance.metrics_map(year, month))
        cuoi_thang = date(year, month, monthrange(year, month)[1])
        thieu: list[str] = []
        for ln in self.payroll.list_lines(period.id):
            if ln.employee_id in co_trong_anh:
                continue
            emp = self.employees.get_by_id(ln.employee_id)
            if emp is None or (emp.hire_date is not None and emp.hire_date > cuoi_thang):
                continue
            thieu.append(emp.full_name or f"NV #{emp.id}")
        return thieu

    def lock_period(self, *, year, month, actor):
        period = self.payroll.get_period_by_ym(year, month)
        if period is None:
            raise PayrollNotFound("Chưa có bảng lương tháng này.")
        if period.status != PERIOD_DRAFT:
            raise PayrollValidationError("Chỉ chốt được kỳ đang nháp.")
        ly_do = self.ly_do_chua_chot_duoc(year, month)
        if ly_do:
            raise PayrollValidationError(ly_do)
        p = self.payroll.update_period(
            period, status=PERIOD_LOCKED, locked_at=datetime.now(timezone.utc),
            locked_by=getattr(actor, "id", None),
        )
        self._audit(actor, "payroll_lock", f"payroll_period:{p.id}", f"{int(month)}/{int(year)}")
        return p

    def reopen_period(self, *, year, month, actor):
        period = self.payroll.get_period_by_ym(year, month)
        if period is None:
            raise PayrollNotFound("Chưa có bảng lương tháng này.")
        if period.status == PERIOD_PAID:
            raise PayrollValidationError("Kỳ đã chi — hủy đã chi trước khi mở lại.")
        # TỰ THU HỒI PHIẾU khi mở lại kỳ: mở lại nghĩa là số sắp đổi. Để phiếu mở là NLĐ đang đọc
        # một con số không còn đúng — mà họ không có cách nào biết.
        p = self.payroll.update_period(period, status=PERIOD_DRAFT, locked_at=None, locked_by=None,
                                       cong_bo_luc=None, dong_phieu_luc=None)
        self._audit(actor, "payroll_reopen", f"payroll_period:{p.id}", f"{int(month)}/{int(year)}")
        return p

    def pay_period(self, *, year, month, actor, note=None):
        """Đánh dấu kỳ lương ĐÃ CHI — chỉ khi đã CHỐT (locked)."""
        period = self.payroll.get_period_by_ym(year, month)
        if period is None:
            raise PayrollNotFound("Chưa có bảng lương tháng này.")
        if period.status != PERIOD_LOCKED:
            raise PayrollValidationError("Chỉ đánh dấu đã chi khi kỳ đã CHỐT.")
        p = self.payroll.update_period(
            period, status=PERIOD_PAID, paid_at=datetime.now(timezone.utc),
            paid_by=getattr(actor, "id", None),
        )
        detail = f"{int(month)}/{int(year)}" + (f" · {note}" if note else "")
        self._audit(actor, "payroll_paid", f"payroll_period:{p.id}", detail)
        return p

    def unpay_period(self, *, year, month, actor, note=None):
        """Hủy đã chi — về CHỐT (locked). Ghi lý do vào nhật ký nếu có."""
        period = self.payroll.get_period_by_ym(year, month)
        if period is None:
            raise PayrollNotFound("Chưa có bảng lương tháng này.")
        if period.status != PERIOD_PAID:
            raise PayrollValidationError("Kỳ chưa ở trạng thái đã chi.")
        p = self.payroll.update_period(period, status=PERIOD_LOCKED, paid_at=None, paid_by=None)
        detail = f"{int(month)}/{int(year)}" + (f" · {note}" if note else "")
        self._audit(actor, "payroll_unpaid", f"payroll_period:{p.id}", detail)
        return p

    # --- self-service phiếu lương -------------------------------------------

    def _cho_phat(self, employee_id: int, ky_dang_xem: set[tuple[int, int]], bay_gio) -> dict | None:
        """Kỳ lương MỚI NHẤT của NV mà họ CHƯA được xem — trả về để giao diện nói đúng lý do.

        ⚠️ CHỈ tháng + trạng thái, TUYỆT ĐỐI không kèm một con số tiền nào. Cả cửa công bố sinh ra
        để NLĐ không đọc số chưa chốt; đẩy dòng lương ra rồi để giao diện tự ẩn là mở DevTools
        đọc được, cửa công bố thành hình thức.

        Dùng lại `latest_line_for_employee` — hàm này thành CODE CHẾT từ 12/08/2026 khi cửa công
        bố ra đời, nay sống lại đúng một việc: hỏi "có phiếu không" mà không hỏi "bao nhiêu tiền".
        """
        ln = self.payroll.latest_line_for_employee(employee_id)
        if ln is None:
            return None                      # chưa từng có bảng lương nào → câu mặc định
        p = self.payroll.get_period(ln.period_id)
        if p is None or (int(p.year), int(p.month)) in ky_dang_xem:
            return None                      # kỳ mới nhất đang xem được rồi → không có gì để báo
        mo = _as_utc(p.cong_bo_luc) if p.cong_bo_luc is not None else None
        dong = _as_utc(p.dong_phieu_luc) if p.dong_phieu_luc is not None else None
        if mo is None:
            tinh_trang = "chua_phat"         # chốt xong nhưng chưa ai bấm Công bố
        elif mo > bay_gio:
            tinh_trang = "hen_gio"           # đã hẹn, chưa tới giờ mở
        elif dong is not None and dong <= bay_gio:
            tinh_trang = "da_dong"           # từng phát, cửa sổ đã khép
        else:
            return None                      # đang mở thật → đã nằm trong `ky_dang_xem` ở trên
        return {"year": int(p.year), "month": int(p.month),
                "tinh_trang": tinh_trang, "mo_luc": mo}

    def my_payslip(self, *, user, year=None, month=None):
        """Phiếu lương của CHÍNH NV đăng nhập — chỉ trả kỳ ĐÃ CÔNG BỐ và ĐÃ TỚI GIỜ.

        ⚠️ Trước 12/08/2026 hàm này trả thẳng dòng lương của kỳ mới nhất, KHÔNG lọc gì: HCNS vừa
        bấm "Tính lại", số còn đang soát, thợ đã mở điện thoại xem được — rồi HCNS sửa tiếp, số
        đổi, không ai báo. Nay phải qua cửa công bố.

        Chủ chốt chọn ĐƯỜNG 2 (12/08/2026): KHÔNG thêm ô quyền nào. Phiếu lương là tiền của chính
        người ta nên ai cũng được xem của mình; thứ cần kiểm soát là THỜI ĐIỂM, không phải AI.

        TỪ 17/08/2026 nhận thêm `year`/`month` để NLĐ tra lại tháng cũ (`docs/prd-phieu-luong-tu-
        phuc-vu.md`). Bỏ trống ⇒ kỳ mới nhất đang mở ⇒ HÀNH VI Y HỆT TRƯỚC, client cũ không sửa
        vẫn chạy. Chủ chốt: cửa sổ mở–đóng là công tắc DUY NHẤT, không thêm trần "12 tháng gần
        nhất" — đã có giờ đóng rồi, thêm trần cứng là hai chỗ cùng quyết một việc."""
        emp = self.employees.get_by_user_id(user.id)
        if emp is None:
            return {"has_employee": False, "employee_name": None, "line": None, "period": None,
                    "ky_xem_duoc": [], "cho_phat": None}
        bay_gio = datetime.now(timezone.utc)
        ky_list = self.payroll.published_periods_for_employee(emp.id, bay_gio)
        if year is not None and month is not None:
            ln = self.payroll.published_line_for_employee(emp.id, bay_gio, int(year), int(month))
        else:
            ln = self.payroll.latest_published_line_for_employee(emp.id, bay_gio)
        period = self.payroll.get_period(ln.period_id) if ln else None
        return {
            "has_employee": True, "employee_name": emp.full_name, "line": ln, "period": period,
            "ky_xem_duoc": [{"year": int(p.year), "month": int(p.month),
                             "dong_phieu_luc": p.dong_phieu_luc} for p in ky_list],
            "cho_phat": self._cho_phat(
                emp.id, {(int(p.year), int(p.month)) for p in ky_list}, bay_gio),
        }

    # --- công bố phiếu lương ------------------------------------------------

    def cong_bo_phieu(self, *, year, month, actor, luc=None, den=None):
        """Phát phiếu lương cho NLĐ theo MỘT CỬA SỔ mở–đóng.

        `luc=None` ⇒ mở NGAY. `den=None` ⇒ mở không thời hạn. NV thấy phiếu khi
        `cong_bo_luc <= bây giờ < dong_phieu_luc`.

        CHỈ CÔNG BỐ ĐƯỢC KỲ ĐÃ CHỐT — kỳ nháp thì số chưa đóng băng, phát ra là mời người ta đọc
        một con số sắp khác. Đây chính là cái bịt lỗ "NV xem được phiếu nháp"."""
        period = self.payroll.get_period_by_ym(year, month)
        if period is None:
            raise PayrollNotFound("Chưa có bảng lương tháng này.")
        if period.status == PERIOD_DRAFT:
            raise PayrollValidationError(
                f"Bảng lương {int(month):02d}/{int(year)} còn là bản nháp — chốt xong mới phát "
                "phiếu được. Phát bây giờ là để người lao động đọc con số sắp đổi."
            )
        moc = _as_utc(luc) if luc is not None else datetime.now(timezone.utc)
        het = _as_utc(den) if den is not None else None
        if het is not None and het <= moc:
            raise PayrollValidationError(
                "Giờ đóng phải sau giờ mở. Bỏ trống ô đóng nếu muốn mở không thời hạn."
            )
        p = self.payroll.update_period(period, cong_bo_luc=moc, dong_phieu_luc=het)
        self._audit(actor, "payroll_cong_bo", f"payroll_period:{p.id}",
                    f"{int(month)}/{int(year)} · {moc.isoformat()}"
                    + (f" → {het.isoformat()}" if het else " → không thời hạn"))
        return p

    def thu_hoi_phieu(self, *, year, month, actor):
        """Rút phiếu lương lại — NV thôi thấy ngay lập tức."""
        period = self.payroll.get_period_by_ym(year, month)
        if period is None:
            raise PayrollNotFound("Chưa có bảng lương tháng này.")
        p = self.payroll.update_period(period, cong_bo_luc=None, dong_phieu_luc=None)
        self._audit(actor, "payroll_thu_hoi", f"payroll_period:{p.id}", f"{int(month)}/{int(year)}")
        return p

    def ky_min_chon_duoc(self) -> str:
        """Tháng SỚM NHẤT còn lập được phiếu tạm ứng, dạng "YYYY-MM".

        = tháng liền sau kỳ lương đã chốt/đã chi muộn nhất. Chưa kỳ nào khoá ⇒ lùi 12 tháng
        (chặn gõ nhầm năm, không chặn việc thật).

        Vì sao trả một MỐC chứ không trả danh sách kỳ: ô chọn của trình duyệt
        (`<input type="month">`) chỉ nhận `min`/`max`, KHÔNG bỏ trống được tháng ở giữa. Mà kỳ
        lương vốn khoá theo thứ tự thời gian nên một mốc là đủ diễn tả."""
        p = self.payroll.latest_closed_period()
        if p is None:
            t = date.today()
            nam, thang = (t.year - 1, t.month) if t.month else (t.year - 1, 1)
            return f"{nam:04d}-{thang:02d}"
        nam, thang = int(p.year), int(p.month) + 1
        if thang > 12:
            nam, thang = nam + 1, 1
        return f"{nam:04d}-{thang:02d}"

    def my_advances(self, *, user):
        emp = self.employees.get_by_user_id(user.id)
        if emp is None:
            return {"has_employee": False, "items": [], "luong_dot_1": 0.0,
                    "ky_min_chon_duoc": self.ky_min_chon_duoc()}
        # Mức "Lương trả 1 lần" hiện hành — để FE điền sẵn khi NV tự xin phiếu đợt 1 (NV không có
        # quyền đọc hồ sơ lương nên phải trả kèm ở đây).
        sal = self.payroll.current_salary(emp.id, date.today())
        return {
            "has_employee": True,
            "items": self.payroll.list_advances_by_employee(emp.id),
            "luong_dot_1": float(getattr(sal, "luong_dot_1", 0) or 0),
            # NV KHÔNG có quyền đọc `/periods` (đòi `luong:read`) nên không tự biết kỳ nào đã
            # khoá — phải trả kèm ở đây, cùng lối với `luong_dot_1` ngay trên.
            "ky_min_chon_duoc": self.ky_min_chon_duoc(),
        }
