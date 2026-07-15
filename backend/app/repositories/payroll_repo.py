"""Payroll (Lương) data access — the ONLY layer touching the DB for payroll tables.
No business rules (those live in PayrollService)."""
from __future__ import annotations

from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models.payroll import (
    ADV_APPROVED,
    EmployeeSalary,
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

    def create_salary(self, **fields) -> EmployeeSalary:
        s = EmployeeSalary(**fields)
        self.db.add(s)
        self.db.commit()
        self.db.refresh(s)
        return s

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

    def list_advances_by_employee(self, employee_id: int, *, limit: int = 100) -> list[SalaryAdvance]:
        return list(
            self.db.execute(
                select(SalaryAdvance)
                .where(SalaryAdvance.employee_id == employee_id)
                .order_by(SalaryAdvance.advance_date.desc(), SalaryAdvance.id.desc())
                .limit(limit)
            ).scalars()
        )

    def approved_advance_map(self, year: int, month: int) -> dict[int, float]:
        """{employee_id → tổng tạm ứng ĐÃ DUYỆT của kỳ} — để trừ vào bảng lương."""
        rows = self.db.execute(
            select(SalaryAdvance.employee_id, func.sum(SalaryAdvance.amount))
            .where(
                SalaryAdvance.period_year == year,
                SalaryAdvance.period_month == month,
                SalaryAdvance.status == ADV_APPROVED,
            )
            .group_by(SalaryAdvance.employee_id)
        ).all()
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
