"""Lương routes (module `luong`, Phase 1 — lương thời gian).

- Cấu hình (params/quy tắc), lương nhân viên, tạm ứng, bảng lương tháng: gated `luong`.
- Phiếu lương / tạm ứng của tôi (me): chỉ cần đăng nhập + có hồ sơ NV (self-service).
"""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status

from ..deps import (
    CurrentUser,
    get_department_repository,
    get_employee_repository,
    get_payroll_service,
    require_permission,
)
from ..models.user import User
from ..repositories.employee_repo import EmployeeRepository
from ..repositories.rbac_repo import DepartmentRepository
from ..schemas.payroll import (
    AdvanceDecisionIn,
    AdvanceIn,
    AdvanceOut,
    AdvancesOut,
    GenerateIn,
    LineOut,
    LineUpdateIn,
    MyAdvancesOut,
    ParamsIn,
    ParamsOut,
    PayslipOut,
    PeriodOut,
    PeriodsOut,
    RuleIn,
    RuleOut,
    RulesOut,
    SalariesOut,
    SalaryIn,
    SalaryOut,
    SalaryPreviewOut,
    TableOut,
)
from ..services.payroll_service import (
    PayrollError,
    PayrollLocked,
    PayrollNotFound,
    PayrollService,
    PayrollValidationError,
)

router = APIRouter(prefix="/api/luong", tags=["luong"])

MODULE = "luong"

Service = Annotated[PayrollService, Depends(get_payroll_service)]
Employees = Annotated[EmployeeRepository, Depends(get_employee_repository)]
Departments = Annotated[DepartmentRepository, Depends(get_department_repository)]


def _raise(exc: Exception) -> None:
    if isinstance(exc, PayrollNotFound):
        raise HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, PayrollLocked):
        raise HTTPException(status_code=409, detail=str(exc))
    if isinstance(exc, PayrollValidationError):
        raise HTTPException(status_code=400, detail=str(exc))
    raise exc


def _lines_out(lines, employees: EmployeeRepository, departments: DepartmentRepository) -> list[LineOut]:
    dept_names = {d.id: d.name for d in departments.list_all()} if lines else {}
    emp_map = {}
    for eid in {ln.employee_id for ln in lines}:
        emp = employees.get_by_id(eid)
        if emp is not None:
            emp_map[eid] = emp
    out: list[LineOut] = []
    for ln in lines:
        o = LineOut.model_validate(ln)
        emp = emp_map.get(ln.employee_id)
        if emp is not None:
            o.employee_code = emp.code
            o.employee_name = emp.full_name
            o.payroll_group = emp.payroll_group
            o.bank_account = emp.bank_account
            o.bank_name = emp.bank_name
            o.department_name = dept_names.get(emp.department_id)
        out.append(o)
    return out


def _adv_out(advs, employees: EmployeeRepository) -> list[AdvanceOut]:
    names = {}
    for eid in {a.employee_id for a in advs}:
        emp = employees.get_by_id(eid)
        if emp is not None:
            names[eid] = emp.full_name
    res = []
    for a in advs:
        o = AdvanceOut.model_validate(a)
        o.employee_name = names.get(a.employee_id)
        res.append(o)
    return res


# --- cấu hình: params + quy tắc ---------------------------------------------


@router.get("/params", response_model=ParamsOut)
def get_params(svc: Service, user: Annotated[User, Depends(require_permission(MODULE, "read"))]) -> ParamsOut:
    return ParamsOut.model_validate(svc.get_params())


@router.put("/params", response_model=ParamsOut)
def update_params(body: ParamsIn, svc: Service,
                  user: Annotated[User, Depends(require_permission(MODULE, "update"))]) -> ParamsOut:
    return ParamsOut.model_validate(svc.update_params(**body.model_dump(exclude_none=True)))


@router.get("/rules", response_model=RulesOut)
def list_rules(svc: Service, user: Annotated[User, Depends(require_permission(MODULE, "read"))]) -> RulesOut:
    return RulesOut(items=[RuleOut.model_validate(r) for r in svc.list_rules()])


@router.post("/rules", response_model=RuleOut, status_code=status.HTTP_201_CREATED)
def create_rule(body: RuleIn, svc: Service,
                user: Annotated[User, Depends(require_permission(MODULE, "create"))]) -> RuleOut:
    try:
        r = svc.create_rule(**body.model_dump())
    except PayrollError as exc:
        _raise(exc)
    return RuleOut.model_validate(r)


@router.put("/rules/{rule_id}", response_model=RuleOut)
def update_rule(rule_id: int, body: RuleIn, svc: Service,
                user: Annotated[User, Depends(require_permission(MODULE, "update"))]) -> RuleOut:
    try:
        r = svc.update_rule(rule_id, **body.model_dump())
    except PayrollError as exc:
        _raise(exc)
    return RuleOut.model_validate(r)


@router.delete("/rules/{rule_id}", status_code=204)
def delete_rule(rule_id: int, svc: Service,
                user: Annotated[User, Depends(require_permission(MODULE, "delete"))]):
    try:
        svc.delete_rule(rule_id)
    except PayrollError as exc:
        _raise(exc)


# --- lương nhân viên (khai báo + điều chỉnh) --------------------------------


@router.get("/salaries/{employee_id}", response_model=SalariesOut)
def list_salaries(employee_id: int, svc: Service, employees: Employees,
                  user: Annotated[User, Depends(require_permission(MODULE, "read"))]) -> SalariesOut:
    emp = employees.get_by_id(employee_id)
    items = [SalaryOut.model_validate(s) for s in svc.list_salaries(employee_id)]
    return SalariesOut(employee_id=employee_id,
                       employee_name=emp.full_name if emp else None, items=items)


@router.get("/salaries/{employee_id}/preview", response_model=SalaryPreviewOut)
def preview_salary(employee_id: int, svc: Service,
                   user: Annotated[User, Depends(require_permission(MODULE, "read"))]) -> SalaryPreviewOut:
    try:
        return SalaryPreviewOut(**svc.salary_preview(employee_id))
    except PayrollError as exc:
        _raise(exc)


@router.post("/salaries/{employee_id}", response_model=SalaryOut, status_code=status.HTTP_201_CREATED)
def set_salary(employee_id: int, body: SalaryIn, svc: Service,
               user: Annotated[User, Depends(require_permission(MODULE, "update"))]) -> SalaryOut:
    try:
        s = svc.set_salary(employee_id=employee_id, actor=user, effective_from=body.effective_from,
                           amount_mode=body.amount_mode, base_amount=body.base_amount,
                           insurance_base=body.insurance_base, allowance=body.allowance, note=body.note)
    except PayrollError as exc:
        _raise(exc)
    return SalaryOut.model_validate(s)


@router.delete("/salaries/item/{salary_id}", status_code=204)
def delete_salary(salary_id: int, svc: Service,
                  user: Annotated[User, Depends(require_permission(MODULE, "update"))]):
    try:
        svc.delete_salary(salary_id)
    except PayrollError as exc:
        _raise(exc)


# --- tạm ứng ----------------------------------------------------------------


@router.get("/advances", response_model=AdvancesOut)
def list_advances(svc: Service, employees: Employees,
                  user: Annotated[User, Depends(require_permission(MODULE, "read"))],
                  year: int = Query(...), month: int = Query(...),
                  status_filter: str | None = Query(default=None, alias="status")) -> AdvancesOut:
    advs = svc.list_advances(year=year, month=month, status=status_filter)
    return AdvancesOut(items=_adv_out(advs, employees))


@router.post("/advances", response_model=AdvanceOut, status_code=status.HTTP_201_CREATED)
def create_advance(body: AdvanceIn, svc: Service, employees: Employees,
                   user: Annotated[User, Depends(require_permission(MODULE, "create"))]) -> AdvanceOut:
    try:
        a = svc.create_advance(employee_id=body.employee_id, actor=user, period_year=body.period_year,
                               period_month=body.period_month, advance_date=body.advance_date,
                               amount=body.amount, reason=body.reason)
    except PayrollError as exc:
        _raise(exc)
    return _adv_out([a], employees)[0]


@router.post("/advances/{advance_id}/approve", response_model=AdvanceOut)
def approve_advance(advance_id: int, body: AdvanceDecisionIn, svc: Service, employees: Employees,
                    user: Annotated[User, Depends(require_permission(MODULE, "update"))]) -> AdvanceOut:
    try:
        a = svc.decide_advance(advance_id=advance_id, actor=user, approve=True, note=body.note)
    except PayrollError as exc:
        _raise(exc)
    return _adv_out([a], employees)[0]


@router.post("/advances/{advance_id}/reject", response_model=AdvanceOut)
def reject_advance(advance_id: int, body: AdvanceDecisionIn, svc: Service, employees: Employees,
                   user: Annotated[User, Depends(require_permission(MODULE, "update"))]) -> AdvanceOut:
    try:
        a = svc.decide_advance(advance_id=advance_id, actor=user, approve=False, note=body.note)
    except PayrollError as exc:
        _raise(exc)
    return _adv_out([a], employees)[0]


@router.post("/advances/{advance_id}/cancel", response_model=AdvanceOut)
def cancel_advance(advance_id: int, svc: Service, employees: Employees,
                   user: Annotated[User, Depends(require_permission(MODULE, "update"))]) -> AdvanceOut:
    try:
        a = svc.cancel_advance(advance_id=advance_id, actor=user)
    except PayrollError as exc:
        _raise(exc)
    return _adv_out([a], employees)[0]


@router.get("/advances/me", response_model=MyAdvancesOut)
def my_advances(svc: Service, employees: Employees, user: CurrentUser) -> MyAdvancesOut:
    res = svc.my_advances(user=user)
    return MyAdvancesOut(has_employee=res["has_employee"], items=_adv_out(res["items"], employees))


# --- bảng lương tháng -------------------------------------------------------


@router.get("/periods", response_model=PeriodsOut)
def list_periods(svc: Service, user: Annotated[User, Depends(require_permission(MODULE, "read"))]) -> PeriodsOut:
    return PeriodsOut(items=[PeriodOut.model_validate(p) for p in svc.list_periods()])


@router.get("/table", response_model=TableOut)
def get_table(svc: Service, employees: Employees, departments: Departments,
              user: Annotated[User, Depends(require_permission(MODULE, "read"))],
              year: int = Query(...), month: int = Query(...)) -> TableOut:
    data = svc.get_table(year=year, month=month)
    if data is None:
        return TableOut(period=None, lines=[])
    return TableOut(period=PeriodOut.model_validate(data["period"]),
                    lines=_lines_out(data["lines"], employees, departments))


@router.post("/generate", response_model=TableOut)
def generate(body: GenerateIn, svc: Service, employees: Employees, departments: Departments,
             user: Annotated[User, Depends(require_permission(MODULE, "create"))]) -> TableOut:
    try:
        svc.generate(year=body.year, month=body.month, actor=user)
    except PayrollError as exc:
        _raise(exc)
    data = svc.get_table(year=body.year, month=body.month)
    return TableOut(period=PeriodOut.model_validate(data["period"]),
                    lines=_lines_out(data["lines"], employees, departments))


@router.put("/lines/{line_id}", response_model=LineOut)
def update_line(line_id: int, body: LineUpdateIn, svc: Service, employees: Employees, departments: Departments,
                user: Annotated[User, Depends(require_permission(MODULE, "update"))]) -> LineOut:
    try:
        ln = svc.update_line(line_id=line_id, actor=user, vi_pham=body.vi_pham,
                             other_bonus=body.other_bonus, pit=body.pit,
                             monthly_override=body.monthly_override, note=body.note)
    except PayrollError as exc:
        _raise(exc)
    return _lines_out([ln], employees, departments)[0]


@router.post("/lock", response_model=PeriodOut)
def lock_period(body: GenerateIn, svc: Service,
                user: Annotated[User, Depends(require_permission(MODULE, "update"))]) -> PeriodOut:
    try:
        p = svc.lock_period(year=body.year, month=body.month, actor=user)
    except PayrollError as exc:
        _raise(exc)
    return PeriodOut.model_validate(p)


@router.post("/reopen", response_model=PeriodOut)
def reopen_period(body: GenerateIn, svc: Service,
                  user: Annotated[User, Depends(require_permission(MODULE, "update"))]) -> PeriodOut:
    try:
        p = svc.reopen_period(year=body.year, month=body.month, actor=user)
    except PayrollError as exc:
        _raise(exc)
    return PeriodOut.model_validate(p)


# --- self-service -----------------------------------------------------------


@router.get("/payslip/me", response_model=PayslipOut)
def my_payslip(svc: Service, employees: Employees, departments: Departments, user: CurrentUser) -> PayslipOut:
    res = svc.my_payslip(user=user)
    line = None
    if res["line"] is not None:
        line = _lines_out([res["line"]], employees, departments)[0]
    period = PeriodOut.model_validate(res["period"]) if res["period"] is not None else None
    return PayslipOut(has_employee=res["has_employee"], employee_name=res["employee_name"],
                      period=period, line=line)
