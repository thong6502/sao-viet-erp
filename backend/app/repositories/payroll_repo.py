"""Payroll (Lương) data access — the ONLY layer touching the DB for payroll tables.
No business rules (those live in PayrollService)."""
from __future__ import annotations

from datetime import date

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ..models.payroll import (
    ADV_APPROVED,
    ADV_PENDING,
    DepartmentSalaryComponent,
    EmployeeSalary,
    LatePenaltyBracket,
    PayrollLine,
    PayrollParams,
    PayrollPeriod,
    PitTaxBracket,
    SalaryAdvance,
    SalaryRateRule,
)


class PayrollRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    # --- params (singleton) -------------------------------------------------

    def get_params(self) -> PayrollParams | None:
        return self.db.execute(select(PayrollParams).order_by(PayrollParams.id).limit(1)).scalars().first()

    def create_params(self, **fields) -> PayrollParams:
        p = PayrollParams(**fields)
        self.db.add(p)
        self.db.commit()
        self.db.refresh(p)
        return p

    def update_params(self, p: PayrollParams, **fields) -> PayrollParams:
        for k, v in fields.items():
            setattr(p, k, v)
        self.db.commit()
        self.db.refresh(p)
        return p

    # --- salary_rate_rules --------------------------------------------------

    def list_rules(self, *, active_only: bool = False) -> list[SalaryRateRule]:
        stmt = select(SalaryRateRule)
        if active_only:
            stmt = stmt.where(SalaryRateRule.is_active.is_(True))
        return list(self.db.execute(stmt.order_by(SalaryRateRule.payroll_group, SalaryRateRule.id)).scalars())

    def get_rule(self, rule_id: int) -> SalaryRateRule | None:
        return self.db.get(SalaryRateRule, rule_id)

    def create_rule(self, **fields) -> SalaryRateRule:
        r = SalaryRateRule(**fields)
        self.db.add(r)
        self.db.commit()
        self.db.refresh(r)
        return r

    def update_rule(self, r: SalaryRateRule, **fields) -> SalaryRateRule:
        for k, v in fields.items():
            setattr(r, k, v)
        self.db.commit()
        self.db.refresh(r)
        return r

    def delete_rule(self, r: SalaryRateRule) -> None:
        self.db.delete(r)
        self.db.commit()

    # --- pit_tax_brackets (biểu thuế TNCN, sửa được) ------------------------

    def list_pit_brackets(self) -> list[PitTaxBracket]:
        return list(self.db.execute(select(PitTaxBracket).order_by(PitTaxBracket.seq, PitTaxBracket.id)).scalars())

    def get_pit_bracket(self, bracket_id: int) -> PitTaxBracket | None:
        return self.db.get(PitTaxBracket, bracket_id)

    def create_pit_bracket(self, **fields) -> PitTaxBracket:
        b = PitTaxBracket(**fields)
        self.db.add(b)
        self.db.commit()
        self.db.refresh(b)
        return b

    def update_pit_bracket(self, b: PitTaxBracket, **fields) -> PitTaxBracket:
        for k, v in fields.items():
            setattr(b, k, v)
        self.db.commit()
        self.db.refresh(b)
        return b

    def delete_pit_bracket(self, b: PitTaxBracket) -> None:
        self.db.delete(b)
        self.db.commit()

    # --- late_penalty_brackets (bảng phạt trễ/sớm, sửa được) ----------------

    def list_late_penalty_brackets(self) -> list[LatePenaltyBracket]:
        return list(self.db.execute(
            select(LatePenaltyBracket).order_by(LatePenaltyBracket.seq, LatePenaltyBracket.id)
        ).scalars())

    def get_late_penalty_bracket(self, bracket_id: int) -> LatePenaltyBracket | None:
        return self.db.get(LatePenaltyBracket, bracket_id)

    def create_late_penalty_bracket(self, **fields) -> LatePenaltyBracket:
        b = LatePenaltyBracket(**fields)
        self.db.add(b)
        self.db.commit()
        self.db.refresh(b)
        return b

    def update_late_penalty_bracket(self, b: LatePenaltyBracket, **fields) -> LatePenaltyBracket:
        for k, v in fields.items():
            setattr(b, k, v)
        self.db.commit()
        self.db.refresh(b)
        return b

    def delete_late_penalty_bracket(self, b: LatePenaltyBracket) -> None:
        self.db.delete(b)
        self.db.commit()

    # --- department_salary_components (thành phần lương theo BỘ PHẬN) -------

    def list_dept_components(self, department_id: int) -> list[DepartmentSalaryComponent]:
        return list(
            self.db.execute(
                select(DepartmentSalaryComponent)
                .where(DepartmentSalaryComponent.department_id == department_id)
                .order_by(DepartmentSalaryComponent.id)
            ).scalars()
        )

    def get_dept_component(self, department_id: int, key: str) -> DepartmentSalaryComponent | None:
        return self.db.execute(
            select(DepartmentSalaryComponent).where(
                DepartmentSalaryComponent.department_id == department_id,
                DepartmentSalaryComponent.component_key == key,
            )
        ).scalars().first()

    def upsert_dept_component(self, *, department_id: int, component_key: str,
                              **fields) -> DepartmentSalaryComponent:
        """UNIQUE(department_id, component_key) → có thì cập nhật, chưa có thì tạo."""
        row = self.get_dept_component(department_id, component_key)
        if row is None:
            row = DepartmentSalaryComponent(
                department_id=department_id, component_key=component_key, **fields
            )
            self.db.add(row)
        else:
            for k, v in fields.items():
                setattr(row, k, v)
        self.db.commit()
        self.db.refresh(row)
        return row

    # --- employee_salaries (versioned) --------------------------------------

    def list_salaries(self, employee_id: int) -> list[EmployeeSalary]:
        """Toàn bộ lịch sử lương của 1 NV, mới nhất trước."""
        return list(
            self.db.execute(
                select(EmployeeSalary)
                .where(EmployeeSalary.employee_id == employee_id)
                .order_by(EmployeeSalary.effective_from.desc(), EmployeeSalary.id.desc())
            ).scalars()
        )

    def current_salary(self, employee_id: int, on: date) -> EmployeeSalary | None:
        """Bản lương hiện hành cho ngày `on` = effective_from lớn nhất ≤ on."""
        return (
            self.db.execute(
                select(EmployeeSalary)
                .where(EmployeeSalary.employee_id == employee_id, EmployeeSalary.effective_from <= on)
                .order_by(EmployeeSalary.effective_from.desc(), EmployeeSalary.id.desc())
                .limit(1)
            ).scalars().first()
        )

    def latest_salaries_map(self, on: date) -> dict[int, EmployeeSalary]:
        """{employee_id → bản lương hiện hành ≤ on} cho toàn bộ NV (1 query, để tính cả bảng)."""
        rows = list(
            self.db.execute(
                select(EmployeeSalary)
                .where(EmployeeSalary.effective_from <= on)
                .order_by(EmployeeSalary.employee_id, EmployeeSalary.effective_from.asc(), EmployeeSalary.id.asc())
            ).scalars()
        )
        out: dict[int, EmployeeSalary] = {}
        for s in rows:  # asc order → cái sau ghi đè = hiện hành
            out[s.employee_id] = s
        return out

    def get_salary(self, salary_id: int) -> EmployeeSalary | None:
        return self.db.get(EmployeeSalary, salary_id)

    def salary_on_date(self, employee_id: int, effective_from: date) -> EmployeeSalary | None:
        return self.db.execute(
            select(EmployeeSalary).where(
                EmployeeSalary.employee_id == employee_id,
                EmployeeSalary.effective_from == effective_from,
            )
        ).scalars().first()

    def create_salary(self, **fields) -> EmployeeSalary:
        s = EmployeeSalary(**fields)
        self.db.add(s)
        self.db.commit()
        self.db.refresh(s)
        return s

    def update_salary(self, salary: EmployeeSalary, **fields) -> EmployeeSalary:
        for key, value in fields.items():
            setattr(salary, key, value)
        self.db.commit()
        self.db.refresh(salary)
        return salary

    def delete_salary(self, s: EmployeeSalary) -> None:
        self.db.delete(s)
        self.db.commit()

    # --- salary_advances ----------------------------------------------------

    def create_advance(self, **fields) -> SalaryAdvance:
        a = SalaryAdvance(**fields)
        self.db.add(a)
        self.db.commit()
        self.db.refresh(a)
        return a

    def get_advance(self, advance_id: int) -> SalaryAdvance | None:
        return self.db.get(SalaryAdvance, advance_id)

    def update_advance(self, a: SalaryAdvance, **fields) -> SalaryAdvance:
        for k, v in fields.items():
            setattr(a, k, v)
        self.db.commit()
        self.db.refresh(a)
        return a

    def list_advances(self, *, year: int, month: int, status: str | None = None) -> list[SalaryAdvance]:
        stmt = select(SalaryAdvance).where(
            SalaryAdvance.period_year == year, SalaryAdvance.period_month == month
        )
        if status is not None:
            stmt = stmt.where(SalaryAdvance.status == status)
        return list(self.db.execute(stmt.order_by(SalaryAdvance.advance_date.desc(), SalaryAdvance.id.desc())).scalars())

    def count_advances_by_status(self, status: str) -> int:
        """Đếm tạm ứng theo trạng thái (mọi kỳ) — nuôi badge real-time 'chờ duyệt'."""
        return self.db.execute(
            select(func.count()).select_from(SalaryAdvance).where(SalaryAdvance.status == status)
        ).scalar_one()

    def count_pending_advances_in_period(self, year: int, month: int) -> int:
        """Số phiếu tạm ứng / lương đợt 1 CÒN CHỜ DUYỆT của ĐÚNG kỳ đó — guard chốt lương.

        KHÁC `count_advances_by_status` (đếm mọi kỳ, nuôi badge): chốt lương là việc của một
        tháng, phiếu treo tháng khác không liên quan.

        Vì sao phải chặn (chủ chốt 15/08/2026): tiền tạm ứng được nướng THẲNG vào dòng lương lúc
        bấm "Tính lại" — không có ảnh chụp nào che như bên chấm công. Duyệt phiếu SAU khi chốt
        lương thì khoản trừ không bao giờ xảy ra: tiền mặt đã đưa cho thợ mà lương vẫn trả đủ.
        """
        return int(self.db.execute(
            select(func.count()).select_from(SalaryAdvance).where(
                SalaryAdvance.status == ADV_PENDING,
                SalaryAdvance.period_year == year,
                SalaryAdvance.period_month == month,
            )
        ).scalar_one())

    def advance_code_exists(self, code: str) -> bool:
        """Kiểm mã tạm ứng đã tồn tại chưa — để sinh mã ngẫu nhiên không trùng."""
        return self.db.execute(
            select(func.count()).select_from(SalaryAdvance).where(SalaryAdvance.code == code)
        ).scalar_one() > 0

    def list_advances_by_employee(self, employee_id: int, *, limit: int = 100) -> list[SalaryAdvance]:
        return list(
            self.db.execute(
                select(SalaryAdvance)
                .where(SalaryAdvance.employee_id == employee_id)
                .order_by(SalaryAdvance.advance_date.desc(), SalaryAdvance.id.desc())
                .limit(limit)
            ).scalars()
        )

    def approved_advance_map(self, year: int, month: int, *,
                             kind: str | None = None) -> dict[int, float]:
        """{employee_id → tổng ĐÃ DUYỆT của kỳ} — để trừ vào bảng lương. `kind` lọc loại phiếu
        (tam_ung / luong_dot_1); None = mọi loại."""
        stmt = select(SalaryAdvance.employee_id, func.sum(SalaryAdvance.amount)).where(
            SalaryAdvance.period_year == year,
            SalaryAdvance.period_month == month,
            SalaryAdvance.status == ADV_APPROVED,
        )
        if kind is not None:
            stmt = stmt.where(SalaryAdvance.kind == kind)
        rows = self.db.execute(stmt.group_by(SalaryAdvance.employee_id)).all()
        return {emp_id: float(total or 0) for emp_id, total in rows}

    # --- payroll_periods ----------------------------------------------------

    def get_period(self, period_id: int) -> PayrollPeriod | None:
        return self.db.get(PayrollPeriod, period_id)

    def get_period_by_ym(self, year: int, month: int) -> PayrollPeriod | None:
        return (
            self.db.execute(
                select(PayrollPeriod).where(PayrollPeriod.year == year, PayrollPeriod.month == month)
            ).scalars().first()
        )

    def create_period(self, **fields) -> PayrollPeriod:
        p = PayrollPeriod(**fields)
        self.db.add(p)
        self.db.commit()
        self.db.refresh(p)
        return p

    def update_period(self, p: PayrollPeriod, **fields) -> PayrollPeriod:
        for k, v in fields.items():
            setattr(p, k, v)
        self.db.commit()
        self.db.refresh(p)
        return p

    def list_periods(self, *, limit: int = 36) -> list[PayrollPeriod]:
        return list(
            self.db.execute(
                select(PayrollPeriod).order_by(PayrollPeriod.year.desc(), PayrollPeriod.month.desc()).limit(limit)
            ).scalars()
        )

    # --- payroll_lines ------------------------------------------------------

    def list_lines(self, period_id: int) -> list[PayrollLine]:
        return list(
            self.db.execute(
                select(PayrollLine).where(PayrollLine.period_id == period_id).order_by(PayrollLine.id)
            ).scalars()
        )

    def get_line(self, line_id: int) -> PayrollLine | None:
        return self.db.get(PayrollLine, line_id)

    def get_line_by_pe(self, period_id: int, employee_id: int) -> PayrollLine | None:
        return (
            self.db.execute(
                select(PayrollLine).where(
                    PayrollLine.period_id == period_id, PayrollLine.employee_id == employee_id
                )
            ).scalars().first()
        )

    def create_line(self, **fields) -> PayrollLine:
        ln = PayrollLine(**fields)
        self.db.add(ln)
        self.db.commit()
        self.db.refresh(ln)
        return ln

    def update_line(self, ln: PayrollLine, **fields) -> PayrollLine:
        for k, v in fields.items():
            setattr(ln, k, v)
        self.db.commit()
        self.db.refresh(ln)
        return ln

    def delete_lines_for_period(self, period_id: int) -> None:
        for ln in self.list_lines(period_id):
            self.db.delete(ln)
        self.db.commit()

    def latest_line_for_employee(self, employee_id: int) -> PayrollLine | None:
        """Dòng lương gần nhất (kỳ mới nhất) của 1 NV — cho phiếu lương self-service."""
        return (
            self.db.execute(
                select(PayrollLine)
                .join(PayrollPeriod, PayrollLine.period_id == PayrollPeriod.id)
                .where(PayrollLine.employee_id == employee_id)
                .order_by(PayrollPeriod.year.desc(), PayrollPeriod.month.desc())
                .limit(1)
            ).scalars().first()
        )

    @staticmethod
    def _dieu_kien_xem_phieu(bay_gio) -> tuple:
        """Bộ lọc "kỳ này NLĐ được xem chưa" — MỘT chỗ, BA câu truy vấn cùng dùng.

        `cong_bo_luc <= bay_gio < dong_phieu_luc` là chỗ "hẹn giờ" tự chạy — không cần job nền.
        Cả mở lẫn đóng đều chỉ là phép so ngày lúc ĐỌC.

        Tách ra vì từ 17/08/2026 có ba đường hỏi cùng một câu (kỳ mới nhất · kỳ chỉ định · danh
        sách kỳ). Chép lại ba lần thì lần sau đổi luật công bố là sót một chỗ, mà chỗ sót đó
        chính là chỗ để lọt SỐ TIỀN của kỳ chưa phát."""
        return (
            PayrollPeriod.cong_bo_luc.is_not(None),
            PayrollPeriod.cong_bo_luc <= bay_gio,
            # Hết hạn xem thì thôi hiện. NULL = mở không thời hạn.
            or_(PayrollPeriod.dong_phieu_luc.is_(None),
                PayrollPeriod.dong_phieu_luc > bay_gio),
        )

    def latest_published_line_for_employee(self, employee_id: int, bay_gio) -> PayrollLine | None:
        """Dòng lương gần nhất của 1 NV trong các kỳ ĐÃ CÔNG BỐ và ĐÃ TỚI GIỜ.

        Lọc ngay trong câu truy vấn chứ không lấy kỳ mới nhất rồi kiểm sau: kỳ tháng 8 chưa công bố
        mà tháng 7 đã công bố thì NV phải thấy PHIẾU THÁNG 7, không phải "không có phiếu nào".

        Đây là nhánh MẶC ĐỊNH (không chỉ định tháng) — mở màn là thấy phiếu mới nhất."""
        return (
            self.db.execute(
                select(PayrollLine)
                .join(PayrollPeriod, PayrollLine.period_id == PayrollPeriod.id)
                .where(PayrollLine.employee_id == employee_id,
                       *self._dieu_kien_xem_phieu(bay_gio))
                .order_by(PayrollPeriod.year.desc(), PayrollPeriod.month.desc())
                .limit(1)
            ).scalars().first()
        )

    def published_line_for_employee(self, employee_id: int, bay_gio,
                                    year: int, month: int) -> PayrollLine | None:
        """Dòng lương của 1 NV ở ĐÚNG kỳ được chỉ định — nếu kỳ đó đang cho xem.

        ⚠️ Tháng do NLĐ gửi lên phải đi qua CHÍNH bộ lọc công bố, không phải lọc thêm sau khi đã
        lấy dòng ra. Gõ tay `?year=2026&month=3` cho kỳ chưa phát thì câu này trả None — không có
        đường nào để một con số của kỳ chưa phát rời khỏi máy chủ."""
        return (
            self.db.execute(
                select(PayrollLine)
                .join(PayrollPeriod, PayrollLine.period_id == PayrollPeriod.id)
                .where(PayrollLine.employee_id == employee_id,
                       PayrollPeriod.year == int(year),
                       PayrollPeriod.month == int(month),
                       *self._dieu_kien_xem_phieu(bay_gio))
            ).scalars().first()
        )

    def published_periods_for_employee(self, employee_id: int, bay_gio) -> list[PayrollPeriod]:
        """MỌI kỳ mà NV này đang được xem phiếu, mới → cũ (17/08/2026).

        Khác `latest_published_line_for_employee` đúng một điểm: KHÔNG `limit(1)`. Trước đó hệ
        thống lọc ra đủ các kỳ rồi ném hết chỉ giữ một, nên tháng 7 phát "không thời hạn" vẫn biến
        mất ngay khi phát tháng 8 — muốn cho xem lại phải THU HỒI tháng 8, tức cắt phiếu hiện tại
        của cả công ty. Bỏ `limit(1)` là ô "giờ đóng" mới thành công tắc lịch sử đúng nghĩa.

        JOIN sang dòng lương để chỉ trả kỳ mà NV này THỰC SỰ có phiếu — người vào làm tháng 8
        không phải thấy tháng 7 rỗng trong danh sách chọn."""
        return list(
            self.db.execute(
                select(PayrollPeriod)
                .join(PayrollLine, PayrollLine.period_id == PayrollPeriod.id)
                .where(PayrollLine.employee_id == employee_id,
                       *self._dieu_kien_xem_phieu(bay_gio))
                .order_by(PayrollPeriod.year.desc(), PayrollPeriod.month.desc())
            ).scalars().all()
        )
