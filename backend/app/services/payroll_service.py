"""Payroll (Lương) business logic — Phase 1 lương thời gian.

Engine tính 1 dòng lương/NV/kỳ (xem docs/spec-luong.md):
  mức lương (manual base_amount HOẶC tra salary_rate_rules theo nhóm/bậc/thâm niên×giới)
  → luong_cong = mức × %thử_việc × (công thực / công chuẩn)     [công lấy từ Chấm công]
  → gross = luong_cong + chuyên_cần(đủ công) + phụ_cấp + thưởng − vi_phạm
  → bhxh = mức_đóng_BH × 10.5% (KHÔNG prorate) ; pit nhập tay
  → net = gross − bhxh − pit − tổng_tạm_ứng(đã duyệt)
"""
from __future__ import annotations

from datetime import date, datetime, timezone

from ..models.employee import STATUS_PROBATION, STATUS_RESIGNED
from ..models.payroll import (
    ADV_APPROVED,
    ADV_CANCELLED,
    ADV_PENDING,
    ADV_REJECTED,
    AMOUNT_MANUAL,
    BAND_GT10,
    BAND_LT1,
    BAND_Y1_5,
    BAND_Y5_10,
    PERIOD_DRAFT,
    PERIOD_LOCKED,
    PERIOD_PAID,
)


class PayrollError(Exception):
    """Base cho lỗi nghiệp vụ lương."""


class PayrollValidationError(PayrollError):
    pass


class PayrollNotFound(PayrollError):
    pass


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


class PayrollService:
    def __init__(self, payroll, employees, attendance, audit=None, piece=None) -> None:
        self.payroll = payroll
        self.employees = employees
        self.attendance = attendance   # AttendanceService — nguồn số CÔNG
        self.piece = piece             # PieceWorkService — nguồn tiền KHOÁN (nhịp 2)
        self.audit = audit

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
            "bhtn_rate", "deduction_self", "deduction_dependent", "chuyen_can_default",
            "standard_hours_per_day", "ot_multiplier", "night_pct", "bh_base_cap", "bhtn_base_cap",
        }
        data = {k: v for k, v in fields.items() if k in allowed and v is not None}
        data["updated_at"] = datetime.now(timezone.utc)
        return self.payroll.update_params(p, **data)

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

    def _auto_pit(self, *, gross, bhxh, ot_pay, night_pay, dependents_count, params, brackets):
        """Trả (thu nhập tính thuế, thuế TNCN). Miễn TOÀN BỘ tiền tăng ca + ca đêm (Luật 109/2025);
        trừ BHXH đã đóng + giảm trừ bản thân + giảm trừ người phụ thuộc."""
        assessable = float(gross) - float(ot_pay) - float(night_pay)   # thu nhập chịu thuế
        deduction = (float(params.deduction_self)
                     + float(params.deduction_dependent) * int(dependents_count or 0))
        taxable = max(0.0, assessable - float(bhxh) - deduction)
        return taxable, _round(_pit_amount(taxable, brackets))

    def _apply_auto_pit(self, ln) -> None:
        """Tính lại TNCN tự động cho 1 dòng (theo gross/bhxh/OT/đêm hiện tại + người phụ thuộc)."""
        emp = self.employees.get_by_id(ln.employee_id)
        tx, pit = self._auto_pit(
            gross=ln.gross, bhxh=ln.bhxh, ot_pay=ln.ot_pay, night_pay=ln.night_pay,
            dependents_count=getattr(emp, "dependents_count", 0),
            params=self.get_params(), brackets=self.get_pit_brackets(),
        )
        ln.pit = pit
        ln.pit_taxable = tx

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

    def _resolve_salary(self, employee, salary, params, on: date) -> dict:
        """Ra {monthly, chuyen_can_amt, source} cho 1 NV tại kỳ. manual → base_amount;
        ngược lại tra rule theo nhóm/bậc/thâm niên×giới."""
        if salary is not None and salary.amount_mode == AMOUNT_MANUAL and salary.base_amount is not None:
            return {"monthly": float(salary.base_amount),
                    "chuyen_can_amt": float(params.chuyen_can_default), "source": "manual"}
        band = _seniority_band(employee.hire_date, on)
        rule = self._lookup_rule(
            payroll_group=employee.payroll_group, pay_grade_key=employee.pay_grade_key,
            seniority_band=band, gender=employee.gender, on=on,
        )
        if rule is not None:
            cc = float(rule.chuyen_can) if rule.chuyen_can is not None else float(params.chuyen_can_default)
            return {"monthly": float(rule.monthly_amount), "chuyen_can_amt": cc, "source": "rule"}
        return {"monthly": 0.0, "chuyen_can_amt": float(params.chuyen_can_default), "source": "none"}

    # --- employee_salaries (khai báo / điều chỉnh) --------------------------

    def list_salaries(self, employee_id: int):
        return self.payroll.list_salaries(employee_id)

    def set_salary(self, *, employee_id, actor, effective_from, amount_mode="rule",
                   base_amount=None, insurance_base=None, allowance=0, note=None):
        """Khai báo/điều chỉnh lương = thêm 1 bản ghi hiệu lực (giữ lịch sử)."""
        emp = self.employees.get_by_id(employee_id)
        if emp is None:
            raise PayrollNotFound("Không tìm thấy nhân viên.")
        if effective_from is None:
            raise PayrollValidationError("Thiếu ngày hiệu lực.")
        if amount_mode == AMOUNT_MANUAL and base_amount is None:
            raise PayrollValidationError("Chế độ nhập tay cần mức lương cụ thể.")
        return self.payroll.create_salary(
            employee_id=employee_id, effective_from=effective_from, amount_mode=amount_mode,
            base_amount=base_amount, insurance_base=insurance_base, allowance=allowance or 0,
            note=note, created_by=getattr(actor, "id", None),
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
        return {
            "employee_id": employee_id,
            "monthly": res["monthly"],
            "source": res["source"],
            "chuyen_can": res["chuyen_can_amt"],
            "allowance": float(salary.allowance) if salary else 0.0,
            "insurance_base": float(salary.insurance_base) if (salary and salary.insurance_base is not None) else res["monthly"],
        }

    # --- advances (tạm ứng) -------------------------------------------------

    def create_advance(self, *, employee_id, actor, period_year, period_month,
                        advance_date, amount, reason=None):
        emp = self.employees.get_by_id(employee_id)
        if emp is None:
            raise PayrollNotFound("Không tìm thấy nhân viên.")
        if amount is None or float(amount) <= 0:
            raise PayrollValidationError("Số tiền tạm ứng phải > 0.")
        return self.payroll.create_advance(
            employee_id=employee_id, period_year=period_year, period_month=period_month,
            advance_date=advance_date, amount=amount, reason=reason,
            status=ADV_PENDING, created_by=getattr(actor, "id", None),
        )

    def list_advances(self, *, year, month, status=None):
        return self.payroll.list_advances(year=year, month=month, status=status)

    def advances_by_employee(self, employee_id: int):
        return self.payroll.list_advances_by_employee(employee_id)

    def decide_advance(self, *, advance_id, actor, approve: bool, note=None):
        a = self.payroll.get_advance(advance_id)
        if a is None:
            raise PayrollNotFound("Không tìm thấy đề nghị tạm ứng.")
        if a.status != ADV_PENDING:
            raise PayrollValidationError("Đề nghị đã được xử lý.")
        return self.payroll.update_advance(
            a, status=ADV_APPROVED if approve else ADV_REJECTED,
            decided_by=getattr(actor, "id", None), decided_at=datetime.now(timezone.utc),
            decision_note=note,
        )

    def cancel_advance(self, *, advance_id, actor):
        a = self.payroll.get_advance(advance_id)
        if a is None:
            raise PayrollNotFound("Không tìm thấy đề nghị tạm ứng.")
        if a.status not in (ADV_PENDING, ADV_APPROVED):
            raise PayrollValidationError("Không thể hủy đề nghị này.")
        return self.payroll.update_advance(a, status=ADV_CANCELLED)

    # --- engine tính 1 dòng -------------------------------------------------

    def _compute(self, *, employee, salary, params, actual_cong, standard_cong,
                 vi_pham=0.0, other_bonus=0.0, khoan=0.0,
                 ot_minutes=0, night_days=0, brackets=None, on: date) -> dict:
        is_probation = employee.status == STATUS_PROBATION
        ratio = float(params.probation_ratio) if is_probation else 1.0
        res = self._resolve_salary(employee, salary, params, on)
        monthly = res["monthly"]
        eff_monthly = monthly * ratio  # mức tháng thực (đã tính %thử việc)

        std = float(standard_cong) or 1.0
        daily_rate = eff_monthly / std                       # đơn giá 1 công
        luong_cong = eff_monthly * (float(actual_cong) / std)
        chuyen_can = res["chuyen_can_amt"] if float(actual_cong) >= float(standard_cong) else 0.0
        allowance = float(salary.allowance) if salary else 0.0

        # Tăng ca (hệ số phẳng) + phụ cấp ca đêm — KHÔNG prorate theo công (tính trên đơn giá chuẩn).
        hours_per_day = float(getattr(params, "standard_hours_per_day", 8) or 8)
        hourly_rate = daily_rate / hours_per_day if hours_per_day else 0.0
        ot_pay = _round(hourly_rate * (float(ot_minutes) / 60.0)
                        * float(getattr(params, "ot_multiplier", 1.5) or 0))
        night_pay = _round(float(night_days) * daily_rate
                           * float(getattr(params, "night_pct", 0) or 0))

        gross = (luong_cong + chuyen_can + allowance + float(khoan)
                 + ot_pay + night_pay + float(other_bonus) - float(vi_pham))

        # BHXH: thử việc KHÔNG đóng (HĐ thử việc, Đ2 Luật BHXH); áp trần RIÊNG BHXH/BHYT vs BHTN.
        if is_probation:
            insurance_base = 0.0
            bhxh = 0.0
        else:
            if salary is not None and salary.insurance_base is not None:
                insurance_base = float(salary.insurance_base)
            else:
                insurance_base = eff_monthly  # mặc định đóng trên mức tháng, KHÔNG prorate
            bh_cap = float(getattr(params, "bh_base_cap", 0) or 0)
            bhtn_cap = float(getattr(params, "bhtn_base_cap", 0) or 0)
            bh_base = min(insurance_base, bh_cap) if bh_cap > 0 else insurance_base
            bhtn_base = min(insurance_base, bhtn_cap) if bhtn_cap > 0 else insurance_base
            bhxh = (bh_base * (float(params.bhxh_rate) + float(params.bhyt_rate))
                    + bhtn_base * float(params.bhtn_rate))

        gross_r = _round(gross)
        bhxh_r = _round(bhxh)
        # TNCN tự tính (7→5 bậc lũy tiến) — miễn toàn bộ OT+ca đêm, trừ BHXH + giảm trừ gia cảnh.
        if brackets is None:
            brackets = self.get_pit_brackets()
        dependents = int(getattr(employee, "dependents_count", 0) or 0)
        pit_taxable, pit_auto = self._auto_pit(
            gross=gross_r, bhxh=bhxh_r, ot_pay=ot_pay, night_pay=night_pay,
            dependents_count=dependents, params=params, brackets=brackets,
        )

        return {
            "is_probation": is_probation,
            "monthly_salary": _round(monthly),
            "luong_cong": _round(luong_cong),
            "chuyen_can": _round(chuyen_can),
            "allowance": _round(allowance),
            "khoan": _round(khoan),
            "ot_minutes": int(ot_minutes),
            "ot_pay": ot_pay,
            "night_days": int(night_days),
            "night_pay": night_pay,
            "vi_pham": _round(vi_pham),
            "other_bonus": _round(other_bonus),
            "gross": gross_r,
            "insurance_base": _round(insurance_base),
            "bhxh": bhxh_r,
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
        period = self.payroll.get_period_by_ym(year, month)
        params = self.get_params()
        if period is None:
            period = self.payroll.create_period(
                year=year, month=month, status=PERIOD_DRAFT,
                standard_cong=params.standard_cong_default, created_by=getattr(actor, "id", None),
            )
        if period.status != PERIOD_DRAFT:
            raise PayrollLocked("Kỳ lương đã chốt/đã chi — mở lại trước khi tính lại.")

        on = date(int(year), int(month), 1)
        metrics_map = self.attendance.metrics_map(year, month)   # {emp: {cong, ot_minutes, night_days}}
        advance_map = self.payroll.approved_advance_map(year, month)
        salary_map = self.payroll.latest_salaries_map(on)
        khoan_map = self.piece.khoan_map(year, month) if self.piece is not None else {}
        brackets = self.get_pit_brackets()
        std = float(period.standard_cong)

        employees = self.employees.list_scoped_all(scope=scope, actor=actor)
        for emp in employees:
            if emp.status == STATUS_RESIGNED:
                continue
            existing = self.payroll.get_line_by_pe(period.id, emp.id)
            vi_pham = float(existing.vi_pham) if existing else 0.0
            other_bonus = float(existing.other_bonus) if existing else 0.0
            note = existing.note if existing else None

            salary = salary_map.get(emp.id)
            m = metrics_map.get(emp.id) or {}   # NV không chấm công → rỗng (KHÔNG KeyError)
            actual_cong = float(m.get("cong", 0.0))
            ot_minutes = int(m.get("ot_minutes", 0))
            night_days = int(m.get("night_days", 0))
            khoan = khoan_map.get(emp.id, 0.0)
            vals = self._compute(
                employee=emp, salary=salary, params=params, actual_cong=actual_cong,
                standard_cong=std, vi_pham=vi_pham, other_bonus=other_bonus, khoan=khoan,
                ot_minutes=ot_minutes, night_days=night_days, brackets=brackets, on=on,
            )
            # TNCN: GIỮ số HCNS đã ghi đè tay (pit_manual); ngược lại dùng số tự tính.
            if existing is not None and existing.pit_manual:
                pit_eff, pit_manual = float(existing.pit), True
            else:
                pit_eff, pit_manual = vals["pit"], False
            advance_total = _round(advance_map.get(emp.id, 0.0))
            net = vals["gross"] - vals["bhxh"] - pit_eff - advance_total

            fields = dict(
                is_probation=vals["is_probation"], actual_cong=actual_cong, standard_cong=std,
                monthly_salary=vals["monthly_salary"], luong_cong=vals["luong_cong"],
                chuyen_can=vals["chuyen_can"], allowance=vals["allowance"], khoan=vals["khoan"],
                ot_minutes=vals["ot_minutes"], ot_pay=vals["ot_pay"],
                night_days=vals["night_days"], night_pay=vals["night_pay"],
                vi_pham=vals["vi_pham"], other_bonus=vals["other_bonus"], gross=vals["gross"],
                insurance_base=vals["insurance_base"], bhxh=vals["bhxh"],
                pit=pit_eff, pit_manual=pit_manual, pit_taxable=vals["pit_taxable"],
                advance_total=advance_total, net_pay=_round(net), note=note,
                updated_at=datetime.now(timezone.utc),
            )
            if existing:
                self.payroll.update_line(existing, **fields)
            else:
                self.payroll.create_line(period_id=period.id, employee_id=emp.id, **fields)
        self._audit(actor, "payroll_generate", f"payroll_period:{period.id}", f"{int(month)}/{int(year)}")
        return period

    def get_table(self, *, year, month):
        """Kỳ lương + các dòng (kèm thông tin NV) cho FE. None nếu chưa tạo."""
        period = self.payroll.get_period_by_ym(year, month)
        if period is None:
            return None
        lines = self.payroll.list_lines(period.id)
        return {"period": period, "lines": lines}

    def update_line(self, *, line_id, actor, vi_pham=None, other_bonus=None, pit=None,
                    pit_manual=None, monthly_override=None, note=None):
        """Sửa ô tay 1 dòng (chỉ khi kỳ draft) → tính lại gross/TNCN/net."""
        ln = self.payroll.get_line(line_id)
        if ln is None:
            raise PayrollNotFound("Không tìm thấy dòng lương.")
        period = self.payroll.get_period(ln.period_id)
        if period is None or period.status != PERIOD_DRAFT:
            raise PayrollLocked("Kỳ lương đã chốt/đã chi — không sửa được.")

        if vi_pham is not None:
            ln.vi_pham = _round(vi_pham)
        if other_bonus is not None:
            ln.other_bonus = _round(other_bonus)
        if monthly_override is not None:
            # sửa tay mức tháng → tính lại lương công theo tỷ lệ công hiện có.
            ln.monthly_salary = _round(monthly_override)
            std = float(ln.standard_cong) or 1.0
            ln.luong_cong = _round(float(ln.monthly_salary) * (float(ln.actual_cong) / std))
        if note is not None:
            ln.note = note

        ln.gross = _round(float(ln.luong_cong) + float(ln.chuyen_can) + float(ln.allowance)
                          + float(ln.khoan) + float(ln.ot_pay) + float(ln.night_pay)
                          + float(ln.other_bonus) - float(ln.vi_pham))
        # TNCN: reset về tự tính (pit_manual=False) / ghi đè tay (pit) / else cập nhật auto theo gross mới.
        if pit_manual is False:
            self._apply_auto_pit(ln)
            ln.pit_manual = False
        elif pit is not None:
            ln.pit = _round(pit)
            ln.pit_manual = True
        elif not ln.pit_manual:
            self._apply_auto_pit(ln)
        ln.net_pay = _round(float(ln.gross) - float(ln.bhxh) - float(ln.pit) - float(ln.advance_total))
        ln.updated_at = datetime.now(timezone.utc)
        saved = self.payroll.update_line(ln)
        self._audit(actor, "payroll_update_line", f"payroll_line:{ln.id}", "sửa ô tay")
        return saved

    def lock_period(self, *, year, month, actor):
        period = self.payroll.get_period_by_ym(year, month)
        if period is None:
            raise PayrollNotFound("Chưa có bảng lương tháng này.")
        if period.status != PERIOD_DRAFT:
            raise PayrollValidationError("Chỉ chốt được kỳ đang nháp.")
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
        p = self.payroll.update_period(period, status=PERIOD_DRAFT, locked_at=None, locked_by=None)
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

    def my_payslip(self, *, user):
        emp = self.employees.get_by_user_id(user.id)
        if emp is None:
            return {"has_employee": False, "employee_name": None, "line": None, "period": None}
        ln = self.payroll.latest_line_for_employee(emp.id)
        period = self.payroll.get_period(ln.period_id) if ln else None
        return {"has_employee": True, "employee_name": emp.full_name, "line": ln, "period": period}

    def my_advances(self, *, user):
        emp = self.employees.get_by_user_id(user.id)
        if emp is None:
            return {"has_employee": False, "items": []}
        return {"has_employee": True, "items": self.payroll.list_advances_by_employee(emp.id)}
