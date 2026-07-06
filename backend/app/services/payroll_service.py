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


class PayrollService:
    def __init__(self, payroll, employees, attendance, audit=None) -> None:
        self.payroll = payroll
        self.employees = employees
        self.attendance = attendance   # AttendanceService — nguồn số CÔNG
        self.audit = audit

    # --- params -------------------------------------------------------------

    def get_params(self):
        """Tham số lương — tự tạo 1 dòng mặc định nếu chưa có."""
        p = self.payroll.get_params()
        if p is None:
            p = self.payroll.create_params()
        return p

    def update_params(self, **fields):
        p = self.get_params()
        allowed = {
            "standard_cong_default", "probation_ratio", "bhxh_rate", "bhyt_rate",
            "bhtn_rate", "deduction_self", "deduction_dependent", "chuyen_can_default",
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
                 vi_pham=0.0, other_bonus=0.0, pit=0.0, on: date) -> dict:
        is_probation = employee.status == STATUS_PROBATION
        ratio = float(params.probation_ratio) if is_probation else 1.0
        res = self._resolve_salary(employee, salary, params, on)
        monthly = res["monthly"]
        eff_monthly = monthly * ratio  # mức tháng thực (đã tính %thử việc)

        std = float(standard_cong) or 1.0
        luong_cong = eff_monthly * (float(actual_cong) / std)
        chuyen_can = res["chuyen_can_amt"] if float(actual_cong) >= float(standard_cong) else 0.0
        allowance = float(salary.allowance) if salary else 0.0

        gross = luong_cong + chuyen_can + allowance + float(other_bonus) - float(vi_pham)

        if salary is not None and salary.insurance_base is not None:
            insurance_base = float(salary.insurance_base)
        else:
            insurance_base = eff_monthly  # mặc định đóng trên mức tháng, KHÔNG prorate
        bh_rate = float(params.bhxh_rate) + float(params.bhyt_rate) + float(params.bhtn_rate)
        bhxh = insurance_base * bh_rate

        return {
            "is_probation": is_probation,
            "monthly_salary": _round(monthly),
            "luong_cong": _round(luong_cong),
            "chuyen_can": _round(chuyen_can),
            "allowance": _round(allowance),
            "vi_pham": _round(vi_pham),
            "other_bonus": _round(other_bonus),
            "gross": _round(gross),
            "insurance_base": _round(insurance_base),
            "bhxh": _round(bhxh),
            "pit": _round(pit),
        }

    # --- periods / bảng lương tháng -----------------------------------------

    def list_periods(self):
        return self.payroll.list_periods()

    def _cong_map(self, year: int, month: int) -> dict[int, float]:
        """{employee_id → số công} từ Bảng công tháng (total_cong, fallback total_days)."""
        ts = self.attendance.monthly_timesheet(year=year, month=month)
        out: dict[int, float] = {}
        for r in ts["rows"]:
            cong = r.get("total_cong")
            out[r["employee_id"]] = float(cong if cong is not None else r.get("total_days") or 0)
        return out

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
        if period.status == PERIOD_LOCKED:
            raise PayrollLocked("Kỳ lương đã chốt — mở lại trước khi tính lại.")

        on = date(int(year), int(month), 1)
        cong_map = self._cong_map(year, month)
        advance_map = self.payroll.approved_advance_map(year, month)
        salary_map = self.payroll.latest_salaries_map(on)
        std = float(period.standard_cong)

        employees = self.employees.list_scoped_all(scope=scope, actor=actor)
        for emp in employees:
            if emp.status == STATUS_RESIGNED:
                continue
            existing = self.payroll.get_line_by_pe(period.id, emp.id)
            vi_pham = float(existing.vi_pham) if existing else 0.0
            other_bonus = float(existing.other_bonus) if existing else 0.0
            pit = float(existing.pit) if existing else 0.0
            note = existing.note if existing else None

            salary = salary_map.get(emp.id)
            actual_cong = cong_map.get(emp.id, 0.0)
            vals = self._compute(
                employee=emp, salary=salary, params=params, actual_cong=actual_cong,
                standard_cong=std, vi_pham=vi_pham, other_bonus=other_bonus, pit=pit, on=on,
            )
            advance_total = _round(advance_map.get(emp.id, 0.0))
            net = vals["gross"] - vals["bhxh"] - vals["pit"] - advance_total

            fields = dict(
                is_probation=vals["is_probation"], actual_cong=actual_cong, standard_cong=std,
                monthly_salary=vals["monthly_salary"], luong_cong=vals["luong_cong"],
                chuyen_can=vals["chuyen_can"], allowance=vals["allowance"], vi_pham=vals["vi_pham"],
                other_bonus=vals["other_bonus"], gross=vals["gross"], insurance_base=vals["insurance_base"],
                bhxh=vals["bhxh"], pit=vals["pit"], advance_total=advance_total, net_pay=_round(net),
                note=note, updated_at=datetime.now(timezone.utc),
            )
            if existing:
                self.payroll.update_line(existing, **fields)
            else:
                self.payroll.create_line(period_id=period.id, employee_id=emp.id, **fields)
        return period

    def get_table(self, *, year, month):
        """Kỳ lương + các dòng (kèm thông tin NV) cho FE. None nếu chưa tạo."""
        period = self.payroll.get_period_by_ym(year, month)
        if period is None:
            return None
        lines = self.payroll.list_lines(period.id)
        return {"period": period, "lines": lines}

    def update_line(self, *, line_id, actor, vi_pham=None, other_bonus=None, pit=None,
                    monthly_override=None, note=None):
        """Sửa ô tay 1 dòng (chỉ khi kỳ draft) → tính lại gross/net."""
        ln = self.payroll.get_line(line_id)
        if ln is None:
            raise PayrollNotFound("Không tìm thấy dòng lương.")
        period = self.payroll.get_period(ln.period_id)
        if period is None or period.status == PERIOD_LOCKED:
            raise PayrollLocked("Kỳ lương đã chốt — không sửa được.")

        if vi_pham is not None:
            ln.vi_pham = _round(vi_pham)
        if other_bonus is not None:
            ln.other_bonus = _round(other_bonus)
        if pit is not None:
            ln.pit = _round(pit)
        if monthly_override is not None:
            # sửa tay mức tháng → tính lại lương công theo tỷ lệ công hiện có.
            ln.monthly_salary = _round(monthly_override)
            std = float(ln.standard_cong) or 1.0
            ln.luong_cong = _round(float(ln.monthly_salary) * (float(ln.actual_cong) / std))
        if note is not None:
            ln.note = note

        ln.gross = _round(float(ln.luong_cong) + float(ln.chuyen_can) + float(ln.allowance)
                          + float(ln.other_bonus) - float(ln.vi_pham))
        ln.net_pay = _round(float(ln.gross) - float(ln.bhxh) - float(ln.pit) - float(ln.advance_total))
        ln.updated_at = datetime.now(timezone.utc)
        return self.payroll.update_line(ln)

    def lock_period(self, *, year, month, actor):
        period = self.payroll.get_period_by_ym(year, month)
        if period is None:
            raise PayrollNotFound("Chưa có bảng lương tháng này.")
        if period.status == PERIOD_LOCKED:
            raise PayrollValidationError("Kỳ lương đã chốt rồi.")
        return self.payroll.update_period(
            period, status=PERIOD_LOCKED, locked_at=datetime.now(timezone.utc),
            locked_by=getattr(actor, "id", None),
        )

    def reopen_period(self, *, year, month, actor):
        period = self.payroll.get_period_by_ym(year, month)
        if period is None:
            raise PayrollNotFound("Chưa có bảng lương tháng này.")
        return self.payroll.update_period(period, status=PERIOD_DRAFT, locked_at=None, locked_by=None)

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
