"""Lương routes (module `luong`, Phase 1 — lương thời gian).

- Cấu hình (params/quy tắc), lương nhân viên, tạm ứng, bảng lương tháng: gated `luong`.
- Phiếu lương / tạm ứng của tôi (me): chỉ cần đăng nhập + có hồ sơ NV (self-service).
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status

from ..deps import (
    CurrentUser,
    get_authorization_service,
    get_department_repository,
    get_employee_repository,
    get_payroll_service,
    get_piece_work_service,
    get_user_repository,
    require_any_permission,
    require_permission,
)
from ..models.user import User
from ..realtime import hub
from ..services.rbac_service import AuthorizationService
from ..repositories.employee_repo import EmployeeRepository
from ..repositories.rbac_repo import DepartmentRepository
from ..repositories.user_repo import UserRepository
from ..schemas.payroll import (
    AdvanceDecisionIn,
    AdvanceIn,
    AdvanceOut,
    AdvancesOut,
    DeptComponentOut,
    DeptComponentsIn,
    DeptComponentsOut,
    GenerateIn,
    LatePenaltyBracketIn,
    LatePenaltyBracketOut,
    LatePenaltyBracketsOut,
    AdvanceQuotaOut,
    InsuranceLineOut,
    LineOut,
    LineUpdateIn,
    MyAdvanceIn,
    MyAdvancesOut,
    ParamsIn,
    ParamsOut,
    PayslipOut,
    PeriodPayIn,
    PitBracketIn,
    PitBracketOut,
    PitBracketsOut,
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
from ..schemas.piece_work import RateIn, RateOut, RatesOut
from ..services.payroll_service import (
    PayrollError,
    PayrollLocked,
    PayrollNotFound,
    PayrollService,
    PayrollValidationError,
)
from ..services.piece_work_service import (
    PieceWorkError,
    PieceWorkNotFound,
    PieceWorkService,
    PieceWorkValidationError,
)

router = APIRouter(prefix="/api/luong", tags=["luong"])

MODULE = "luong"
ConfigViewer = Annotated[
    User,
    Depends(require_any_permission((MODULE, "view_salary"), (MODULE, "update"))),
]

Service = Annotated[PayrollService, Depends(get_payroll_service)]
PieceService = Annotated[PieceWorkService, Depends(get_piece_work_service)]
Employees = Annotated[EmployeeRepository, Depends(get_employee_repository)]
Users = Annotated[UserRepository, Depends(get_user_repository)]
Departments = Annotated[DepartmentRepository, Depends(get_department_repository)]
Authz = Annotated[AuthorizationService, Depends(get_authorization_service)]


def _raise(exc: Exception) -> None:
    if isinstance(exc, (PayrollNotFound, PieceWorkNotFound)):
        raise HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, PayrollLocked):
        raise HTTPException(status_code=409, detail=str(exc))
    if isinstance(exc, (PayrollValidationError, PieceWorkValidationError)):
        raise HTTPException(status_code=400, detail=str(exc))
    raise exc


def _pct(rate) -> str:
    """0.015 → '1,5' (bỏ số 0 thừa, dấu phẩy thập phân kiểu VN) cho nhãn 'BHYT 1,5%'."""
    return f"{float(rate) * 100:g}".replace(".", ",")


def _insurance_lines(ln, params) -> list[InsuranceLineOut]:
    """Tách TỔNG bảo hiểm đã đóng băng (`ln.bhxh`) thành 3 dòng BHXH / BHYT / BHTN cho phiếu lương.

    Dùng ĐÚNG công thức của `_compute` (trần BHXH+BHYT khác trần BHTN). Phần lệch do làm tròn — hoặc
    do tỷ lệ đã đổi sau khi kỳ được chốt — DỒN vào dòng cuối (BHTN), nên 3 dòng LUÔN cộng đúng bằng
    `ln.bhxh`: TỔNG TRỪ trên phiếu không bao giờ lệch THỰC NHẬN.
    """
    total = round(float(ln.bhxh or 0))
    base = float(ln.insurance_base or 0)
    bh_cap = float(getattr(params, "bh_base_cap", 0) or 0)
    tn_cap = float(getattr(params, "bhtn_base_cap", 0) or 0)
    base_y = min(base, bh_cap) if bh_cap > 0 else base
    base_tn = min(base, tn_cap) if tn_cap > 0 else base
    bhxh = round(base_y * float(params.bhxh_rate)) if total else 0
    bhyt = round(base_y * float(params.bhyt_rate)) if total else 0
    bhtn = total - bhxh - bhyt          # dồn phần dư → tổng luôn khớp
    return [
        InsuranceLineOut(label=f"BHXH {_pct(params.bhxh_rate)}%", amount=float(bhxh)),
        InsuranceLineOut(label=f"BHYT {_pct(params.bhyt_rate)}%", amount=float(bhyt)),
        InsuranceLineOut(label=f"BHTN {_pct(params.bhtn_rate)}%", amount=float(bhtn)),
    ]


def _lines_out(lines, employees: EmployeeRepository, departments: DepartmentRepository,
               svc: PayrollService | None = None) -> list[LineOut]:
    dept_names = {d.id: d.name for d in departments.list_all()} if lines else {}
    # Tỷ lệ + trần BH: lấy MỘT lần cho cả mẻ. Không có `svc` (đường xuất Excel) → bỏ qua phần tách.
    params = svc.get_params() if svc is not None else None
    emp_map = {}
    for eid in {ln.employee_id for ln in lines}:
        emp = employees.get_by_id(eid)
        if emp is not None:
            emp_map[eid] = emp
    out: list[LineOut] = []
    for ln in lines:
        o = LineOut.model_validate(ln)
        o.ca_pay = float(ln.night_pay)     # alias FE v2 — CÙNG một số với night_pay
        o.night_premium_pay = float(getattr(ln, "night_premium_pay", 0) or 0)
        # "Phụ cấp khác" = phần còn lại của TỔNG phụ cấp sau khi tách 2 khoản khai ở tổ →
        # 3 dòng trên phiếu cộng lại đúng bằng `allowance` (dòng lương cũ: khác = allowance).
        o.phu_cap_khac = max(0.0, float(ln.allowance) - float(ln.phu_cap_tham_nien))
        if params is not None:
            o.insurance_lines = _insurance_lines(ln, params)
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


def _adv_out(advs, employees: EmployeeRepository,
             departments: DepartmentRepository | None = None) -> list[AdvanceOut]:
    dept_names = {d.id: d.name for d in departments.list_all()} if (departments is not None and advs) else {}
    emp_map = {}
    for eid in {a.employee_id for a in advs}:
        emp = employees.get_by_id(eid)
        if emp is not None:
            emp_map[eid] = emp
    res = []
    for a in advs:
        o = AdvanceOut.model_validate(a)
        emp = emp_map.get(a.employee_id)
        if emp is not None:
            o.employee_name = emp.full_name
            o.bank_account = emp.bank_account
            o.bank_name = emp.bank_name
            o.department_name = dept_names.get(emp.department_id)
        res.append(o)
    return res


# --- real-time: đề nghị/duyệt tạm ứng đẩy tức thì (bám hub SSE) -------------


def _notify_advance_pending(name: str | None) -> None:
    """Có đề nghị tạm ứng mới/đổi → tín hiệu mọi client refetch badge (người duyệt nhận)."""
    hub.broadcast({"type": "advance_pending_changed", "code": name})


def _notify_advance_decision(a, employees: EmployeeRepository, decision: str) -> None:
    """Kế toán duyệt/từ chối → đẩy tới ĐÚNG nhân viên đề nghị (nếu tài khoản đã gắn hồ sơ)."""
    emp = employees.get_by_id(a.employee_id)
    if emp is not None and emp.user_id is not None:
        hub.publish(emp.user_id, {"type": "advance_decision", "decision": decision,
                                  "code": emp.full_name})


# --- cấu hình: params + quy tắc ---------------------------------------------


@router.get("/params", response_model=ParamsOut)
def get_params(svc: Service, user: ConfigViewer) -> ParamsOut:
    return ParamsOut.model_validate(svc.get_params())


@router.put("/params", response_model=ParamsOut)
def update_params(body: ParamsIn, svc: Service,
                  user: Annotated[User, Depends(require_permission(MODULE, "update"))]) -> ParamsOut:
    return ParamsOut.model_validate(svc.update_params(**body.model_dump(exclude_none=True)))


@router.get("/rules", response_model=RulesOut)
def list_rules(svc: Service, user: ConfigViewer) -> RulesOut:
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


# --- Cấu hình lương: thành phần lương theo BỘ PHẬN (Tab 2) ------------------


@router.get("/dept-components/{dept_id}", response_model=DeptComponentsOut)
def get_dept_components(dept_id: int, svc: Service,
                        user: ConfigViewer) -> DeptComponentsOut:
    items = [DeptComponentOut(**c) for c in svc.dept_components(dept_id)]
    return DeptComponentsOut(department_id=dept_id, items=items)


@router.put("/dept-components/{dept_id}", response_model=DeptComponentsOut)
def set_dept_components(dept_id: int, body: DeptComponentsIn, svc: Service,
                        user: Annotated[User, Depends(require_permission(MODULE, "update"))]) -> DeptComponentsOut:
    try:
        rows = svc.set_dept_components(department_id=dept_id,
                                       items=[i.model_dump() for i in body.items], actor=user)
    except PayrollError as exc:
        _raise(exc)
    return DeptComponentsOut(department_id=dept_id, items=[DeptComponentOut(**c) for c in rows])


# --- biểu thuế TNCN (sửa được) ----------------------------------------------


@router.get("/pit-brackets", response_model=PitBracketsOut)
def list_pit_brackets(svc: Service, user: ConfigViewer) -> PitBracketsOut:
    return PitBracketsOut(items=[PitBracketOut.model_validate(b) for b in svc.get_pit_brackets()])


@router.post("/pit-brackets", response_model=PitBracketOut, status_code=status.HTTP_201_CREATED)
def create_pit_bracket(body: PitBracketIn, svc: Service,
                       user: Annotated[User, Depends(require_permission(MODULE, "update"))]) -> PitBracketOut:
    try:
        b = svc.create_pit_bracket(seq=body.seq, up_to=body.up_to, rate=body.rate)
    except PayrollError as exc:
        _raise(exc)
    return PitBracketOut.model_validate(b)


@router.put("/pit-brackets/{bracket_id}", response_model=PitBracketOut)
def update_pit_bracket(bracket_id: int, body: PitBracketIn, svc: Service,
                       user: Annotated[User, Depends(require_permission(MODULE, "update"))]) -> PitBracketOut:
    try:
        b = svc.update_pit_bracket(bracket_id, seq=body.seq, up_to=body.up_to, rate=body.rate)
    except PayrollError as exc:
        _raise(exc)
    return PitBracketOut.model_validate(b)


@router.delete("/pit-brackets/{bracket_id}", status_code=204)
def delete_pit_bracket(bracket_id: int, svc: Service,
                       user: Annotated[User, Depends(require_permission(MODULE, "update"))]):
    try:
        svc.delete_pit_bracket(bracket_id)
    except PayrollError as exc:
        _raise(exc)


# --- bảng phạt đi trễ / về sớm (sửa được) -----------------------------------


@router.get("/late-penalty-brackets", response_model=LatePenaltyBracketsOut)
def list_late_penalty_brackets(svc: Service, user: ConfigViewer) -> LatePenaltyBracketsOut:
    return LatePenaltyBracketsOut(
        items=[LatePenaltyBracketOut.model_validate(b) for b in svc.get_late_penalty_brackets()]
    )


@router.post("/late-penalty-brackets", response_model=LatePenaltyBracketOut,
             status_code=status.HTTP_201_CREATED)
def create_late_penalty_bracket(body: LatePenaltyBracketIn, svc: Service,
                                user: Annotated[User, Depends(require_permission(MODULE, "update"))]) -> LatePenaltyBracketOut:
    try:
        b = svc.create_late_penalty_bracket(
            seq=body.seq, up_to_minute=body.up_to_minute, amount=body.amount)
    except PayrollError as exc:
        _raise(exc)
    return LatePenaltyBracketOut.model_validate(b)


@router.put("/late-penalty-brackets/{bracket_id}", response_model=LatePenaltyBracketOut)
def update_late_penalty_bracket(bracket_id: int, body: LatePenaltyBracketIn, svc: Service,
                                user: Annotated[User, Depends(require_permission(MODULE, "update"))]) -> LatePenaltyBracketOut:
    try:
        b = svc.update_late_penalty_bracket(
            bracket_id, seq=body.seq, up_to_minute=body.up_to_minute, amount=body.amount)
    except PayrollError as exc:
        _raise(exc)
    return LatePenaltyBracketOut.model_validate(b)


@router.delete("/late-penalty-brackets/{bracket_id}", status_code=204)
def delete_late_penalty_bracket(bracket_id: int, svc: Service,
                                user: Annotated[User, Depends(require_permission(MODULE, "update"))]):
    try:
        svc.delete_late_penalty_bracket(bracket_id)
    except PayrollError as exc:
        _raise(exc)


# --- lương nhân viên (khai báo + điều chỉnh) --------------------------------


@router.get("/salaries/{employee_id}", response_model=SalariesOut)
def list_salaries(employee_id: int, svc: Service, employees: Employees,
                  users: Users, user: ConfigViewer) -> SalariesOut:
    emp = employees.get_by_id(employee_id)
    rows = svc.list_salaries(employee_id)
    today = date.today()
    actor_cache: dict[int, str | None] = {}
    items = []
    for index, row in enumerate(rows):
        newer = rows[index - 1] if index > 0 else None
        effective_to = newer.effective_from - timedelta(days=1) if newer is not None else None
        out = SalaryOut.model_validate(row)
        out.effective_to = effective_to
        out.is_current = row.effective_from <= today and (
            effective_to is None or effective_to >= today
        )
        # Người điều chỉnh (cho nhật ký "ai sửa"): tra tên từ created_by, cache trong 1 lần list.
        if row.created_by is not None:
            if row.created_by not in actor_cache:
                u = users.get_by_id(row.created_by)
                actor_cache[row.created_by] = (u.name or u.username) if u is not None else None
            out.actor_name = actor_cache[row.created_by]
        items.append(out)
    return SalariesOut(employee_id=employee_id,
                       employee_name=emp.full_name if emp else None, items=items)


@router.get("/salaries/{employee_id}/preview", response_model=SalaryPreviewOut)
def preview_salary(employee_id: int, svc: Service,
                   user: ConfigViewer) -> SalaryPreviewOut:
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
                           insurance_base=body.insurance_base, allowance=body.allowance, note=body.note,
                           chuyen_can=body.chuyen_can,
                           luong_vi_tri=body.luong_vi_tri, luong_trach_nhiem=body.luong_trach_nhiem,
                           phu_cap_ca=body.phu_cap_ca, phu_cap_tham_nien=body.phu_cap_tham_nien,
                           insurance_elsewhere=body.insurance_elsewhere,
                           union_member=body.union_member)
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
def list_advances(svc: Service, employees: Employees, departments: Departments,
                  user: Annotated[User, Depends(require_permission(MODULE, "read"))],
                  year: int = Query(...), month: int = Query(...),
                  status_filter: str | None = Query(default=None, alias="status")) -> AdvancesOut:
    advs = svc.list_advances(year=year, month=month, status=status_filter)
    return AdvancesOut(items=_adv_out(advs, employees, departments))


@router.post("/advances", response_model=AdvanceOut, status_code=status.HTTP_201_CREATED)
def create_advance(body: AdvanceIn, svc: Service, employees: Employees, departments: Departments,
                   user: Annotated[User, Depends(require_permission(MODULE, "create"))]) -> AdvanceOut:
    try:
        a = svc.create_advance(employee_id=body.employee_id, actor=user, period_year=body.period_year,
                               period_month=body.period_month, advance_date=body.advance_date,
                               amount=body.amount, reason=body.reason)
    except PayrollError as exc:
        _raise(exc)
    out = _adv_out([a], employees, departments)[0]
    _notify_advance_pending(out.employee_name)
    return out


@router.post("/advances/{advance_id}/approve", response_model=AdvanceOut)
def approve_advance(advance_id: int, body: AdvanceDecisionIn, svc: Service, employees: Employees,
                    departments: Departments,
                    user: Annotated[User, Depends(require_permission(MODULE, "update"))]) -> AdvanceOut:
    try:
        a = svc.decide_advance(advance_id=advance_id, actor=user, approve=True, note=body.note)
    except PayrollError as exc:
        _raise(exc)
    _notify_advance_decision(a, employees, "approved")
    return _adv_out([a], employees, departments)[0]


@router.post("/advances/{advance_id}/reject", response_model=AdvanceOut)
def reject_advance(advance_id: int, body: AdvanceDecisionIn, svc: Service, employees: Employees,
                   departments: Departments,
                   user: Annotated[User, Depends(require_permission(MODULE, "update"))]) -> AdvanceOut:
    try:
        a = svc.decide_advance(advance_id=advance_id, actor=user, approve=False, note=body.note)
    except PayrollError as exc:
        _raise(exc)
    _notify_advance_decision(a, employees, "rejected")
    return _adv_out([a], employees, departments)[0]


@router.post("/advances/{advance_id}/cancel", response_model=AdvanceOut)
def cancel_advance(advance_id: int, svc: Service, employees: Employees, departments: Departments,
                   user: Annotated[User, Depends(require_permission(MODULE, "update"))]) -> AdvanceOut:
    try:
        a = svc.cancel_advance(advance_id=advance_id, actor=user)
    except PayrollError as exc:
        _raise(exc)
    return _adv_out([a], employees, departments)[0]


@router.get("/advances/me", response_model=MyAdvancesOut)
def my_advances(svc: Service, employees: Employees, departments: Departments,
                user: CurrentUser) -> MyAdvancesOut:
    res = svc.my_advances(user=user)
    return MyAdvancesOut(has_employee=res["has_employee"],
                         items=_adv_out(res["items"], employees, departments))


@router.post("/advances/me", response_model=AdvanceOut, status_code=status.HTTP_201_CREATED)
def create_my_advance(body: MyAdvanceIn, svc: Service, employees: Employees,
                      departments: Departments, user: CurrentUser) -> AdvanceOut:
    """Nhân viên TỰ lập đề nghị tạm ứng cho chính mình → pending → kế toán duyệt.
    Chỉ cần đăng nhập + có hồ sơ (không cần quyền luong:create)."""
    emp = employees.get_by_user_id(user.id)
    if emp is None:
        raise HTTPException(status_code=400, detail="Tài khoản chưa gắn hồ sơ nhân sự.")
    try:
        a = svc.create_advance(employee_id=emp.id, actor=user, period_year=body.period_year,
                               period_month=body.period_month, advance_date=body.advance_date,
                               amount=body.amount, reason=body.reason)
    except PayrollError as exc:
        _raise(exc)
    out = _adv_out([a], employees, departments)[0]
    _notify_advance_pending(out.employee_name)
    return out


@router.get("/advances/quota", response_model=AdvanceQuotaOut)
def my_advance_quota(svc: Service, employees: Employees, user: CurrentUser,
                     year: int = Query(...), month: int = Query(ge=1, le=12)) -> AdvanceQuotaOut:
    """Hạn mức tạm ứng CÒN LẠI của chính tôi trong kỳ — để form hiện "còn được ứng X đ" TRƯỚC khi gõ.
    Dùng chung `advance_quota()` với chỗ CHẶN nên số trên màn luôn khớp số backend áp dụng."""
    emp = employees.get_by_user_id(user.id)
    if emp is None:
        raise HTTPException(status_code=400, detail="Tài khoản chưa gắn hồ sơ nhân sự.")
    try:
        return AdvanceQuotaOut(**svc.advance_quota(employee_id=emp.id, year=year, month=month))
    except PayrollError as exc:
        _raise(exc)


@router.get("/advances/notify-summary")
def advance_notify_summary(svc: Service, authz: Authz, user: CurrentUser) -> dict:
    """Badge real-time cho Tạm ứng: `pending_approval_count` = số đề nghị đang chờ duyệt.
    Chỉ >0 với người có quyền duyệt (luong:update); nhân viên thường → 0 (chỉ nhận toast quyết định)."""
    can_approve = authz.can(user, MODULE, "update")
    return {"pending_approval_count": svc.count_pending_advances() if can_approve else 0}


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
                    lines=_lines_out(data["lines"], employees, departments, svc))


@router.post("/generate", response_model=TableOut)
def generate(body: GenerateIn, svc: Service, employees: Employees, departments: Departments,
             user: Annotated[User, Depends(require_permission(MODULE, "create"))]) -> TableOut:
    try:
        svc.generate(year=body.year, month=body.month, actor=user)
    except PayrollError as exc:
        _raise(exc)
    data = svc.get_table(year=body.year, month=body.month)
    return TableOut(period=PeriodOut.model_validate(data["period"]),
                    lines=_lines_out(data["lines"], employees, departments, svc))


@router.put("/lines/{line_id}", response_model=LineOut)
def update_line(line_id: int, body: LineUpdateIn, svc: Service, employees: Employees, departments: Departments,
                user: Annotated[User, Depends(require_permission(MODULE, "update"))]) -> LineOut:
    try:
        ln = svc.update_line(line_id=line_id, actor=user, vi_pham=body.vi_pham,
                             other_bonus=body.other_bonus, pit=body.pit, pit_manual=body.pit_manual,
                             di_tre_manual=body.di_tre_manual,
                             monthly_override=body.monthly_override, note=body.note,
                             thuong_5s=body.thuong_5s, thuong_doanh_so=body.thuong_doanh_so,
                             thuong_thanh_tich=body.thuong_thanh_tich, phep_nam=body.phep_nam,
                             tra_dong_phuc=body.tra_dong_phuc, dieu_chinh_luong=body.dieu_chinh_luong,
                             di_tre=body.di_tre, dt_vuot_troi=body.dt_vuot_troi,
                             phat_bien_ban=body.phat_bien_ban, phat_5s_dong_phuc=body.phat_5s_dong_phuc,
                             kpi_percent=body.kpi_percent)
    except PayrollError as exc:
        _raise(exc)
    return _lines_out([ln], employees, departments, svc)[0]


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


@router.post("/pay", response_model=PeriodOut)
def pay_period(body: PeriodPayIn, svc: Service,
               user: Annotated[User, Depends(require_permission(MODULE, "update"))]) -> PeriodOut:
    try:
        p = svc.pay_period(year=body.year, month=body.month, actor=user, note=body.note)
    except PayrollError as exc:
        _raise(exc)
    return PeriodOut.model_validate(p)


@router.post("/unpay", response_model=PeriodOut)
def unpay_period(body: PeriodPayIn, svc: Service,
                 user: Annotated[User, Depends(require_permission(MODULE, "update"))]) -> PeriodOut:
    try:
        p = svc.unpay_period(year=body.year, month=body.month, actor=user, note=body.note)
    except PayrollError as exc:
        _raise(exc)
    return PeriodOut.model_validate(p)


# --- xuất file .xlsx (bảng lương + chuyển khoản) ----------------------------

_XLSX_MEDIA = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _xlsx_response(content: bytes, filename: str) -> Response:
    return Response(content=content, media_type=_XLSX_MEDIA,
                    headers={"Content-Disposition": f'attachment; filename="{filename}"'})


def _build_table_xlsx(year: int, month: int, lines) -> bytes:
    from io import BytesIO

    from openpyxl import Workbook  # lazy import: thiếu dep chỉ hỏng endpoint này, không sập app
    wb = Workbook()
    ws = wb.active
    ws.title = f"Luong {month:02d}-{year}"
    ws.append(["Mã", "Họ tên", "Phòng/Tổ", "Loại", "Công", "Lương công", "Chuyên cần", "Phụ cấp",
               "Khoán", "Tăng ca", "Ca đêm", "Ca đêm (giờ×hệ số)", "Vi phạm", "Thưởng", "Tổng", "BHXH", "TNCN",
               "Tạm ứng", "Thực lĩnh"])
    for l in lines:
        ws.append([l.employee_code or "", l.employee_name or "", l.department_name or "",
                   "Thử việc" if l.is_probation else "Chính thức", float(l.actual_cong),
                   int(l.luong_cong), int(l.chuyen_can), int(l.allowance), int(l.khoan),
                   int(l.ot_pay), int(l.night_pay), int(getattr(l, "night_premium_pay", 0) or 0),
                   int(l.vi_pham), int(l.other_bonus),
                   int(l.gross), int(l.bhxh), int(l.pit), int(l.advance_total), int(l.net_pay)])
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _build_bank_xlsx(year: int, month: int, lines) -> bytes:
    from io import BytesIO

    from openpyxl import Workbook
    wb = Workbook()
    ws = wb.active
    ws.title = "Chuyen khoan"
    ws.append(["Mã", "Họ tên", "Số tài khoản", "Ngân hàng", "Số tiền", "Nội dung"])
    for l in lines:
        if int(l.net_pay) <= 0:
            continue   # NV net ≤ 0 (tạm ứng vượt lương) → không đưa vào file chuyển khoản
        ws.append([l.employee_code or "", l.employee_name or "", l.bank_account or "",
                   l.bank_name or "", int(l.net_pay), f"Luong T{month:02d}/{year} - {l.employee_code or ''}"])
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


@router.get("/export.xlsx")
def export_table_xlsx(svc: Service, employees: Employees, departments: Departments,
                      user: Annotated[User, Depends(require_permission(MODULE, "read"))],
                      year: int = Query(...), month: int = Query(ge=1, le=12)) -> Response:
    data = svc.get_table(year=year, month=month)
    if data is None:
        raise HTTPException(status_code=404, detail="Chưa có bảng lương tháng này.")
    lines = _lines_out(data["lines"], employees, departments)
    return _xlsx_response(_build_table_xlsx(year, month, lines), f"bang-luong-{year}-{month:02d}.xlsx")


@router.get("/bank.xlsx")
def export_bank_xlsx(svc: Service, employees: Employees, departments: Departments,
                     user: Annotated[User, Depends(require_permission(MODULE, "read"))],
                     year: int = Query(...), month: int = Query(ge=1, le=12)) -> Response:
    data = svc.get_table(year=year, month=month)
    if data is None:
        raise HTTPException(status_code=404, detail="Chưa có bảng lương tháng này.")
    lines = _lines_out(data["lines"], employees, departments)
    return _xlsx_response(_build_bank_xlsx(year, month, lines), f"chuyen-khoan-{year}-{month:02d}.xlsx")


# --- self-service -----------------------------------------------------------


@router.get("/payslip/me", response_model=PayslipOut)
def my_payslip(svc: Service, employees: Employees, departments: Departments, user: CurrentUser) -> PayslipOut:
    res = svc.my_payslip(user=user)
    line = None
    if res["line"] is not None:
        line = _lines_out([res["line"]], employees, departments, svc)[0]
    period = PeriodOut.model_validate(res["period"]) if res["period"] is not None else None
    return PayslipOut(has_employee=res["has_employee"], employee_name=res["employee_name"],
                      period=period, line=line)


# --- Lương khoán (nhịp 2) ---------------------------------------------------


@router.get("/khoan/rates", response_model=RatesOut)
def list_rates(svc: PieceService, user: Annotated[User, Depends(require_permission(MODULE, "read"))],
               department_id: int | None = None) -> RatesOut:
    return RatesOut(items=[RateOut.model_validate(r) for r in svc.list_rates(department_id=department_id)])


@router.post("/khoan/rates", response_model=RateOut, status_code=status.HTTP_201_CREATED)
def create_rate(body: RateIn, svc: PieceService,
                user: Annotated[User, Depends(require_permission(MODULE, "create"))]) -> RateOut:
    try:
        return RateOut.model_validate(svc.create_rate(**body.model_dump()))
    except PieceWorkError as exc:
        _raise(exc)


@router.put("/khoan/rates/{rate_id}", response_model=RateOut)
def update_rate(rate_id: int, body: RateIn, svc: PieceService,
                user: Annotated[User, Depends(require_permission(MODULE, "update"))]) -> RateOut:
    try:
        return RateOut.model_validate(svc.update_rate(rate_id, **body.model_dump()))
    except PieceWorkError as exc:
        _raise(exc)


@router.delete("/khoan/rates/{rate_id}", status_code=204)
def delete_rate(rate_id: int, svc: PieceService,
                user: Annotated[User, Depends(require_permission(MODULE, "delete"))]):
    try:
        svc.delete_rate(rate_id)
    except PieceWorkError as exc:
        _raise(exc)
