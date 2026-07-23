"""Hồ sơ nhân sự (nhan_su) routes — lát #1.

Thin HTTP shell over EmployeeService. Every route is guarded by
`require_permission('nhan_su', <action>)`; list/detail narrow to the caller's data scope
(own/department/all) resolved from their role. Stage changes (trạng thái / điều chuyển /
nâng bậc) go through `/transitions` so each writes a Quá trình công tác event.
"""
from __future__ import annotations

import secrets
from datetime import date, timedelta
from pathlib import Path
from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    UploadFile,
    status,
)

from ..deps import (
    CurrentUser,
    get_audit_repository,
    get_authorization_service,
    get_department_repository,
    get_employee_service,
    get_payroll_service,
    get_role_repository,
    get_user_repository,
    require_any_permission,
    require_permission,
)
from ..models.user import User
from ..repositories.audit_repo import AuditLogRepository
from ..repositories.rbac_repo import DepartmentRepository, RoleRepository
from ..repositories.user_repo import UserRepository
from ..schemas.employee import (
    AccountIn,
    AssignShiftIn,
    AttachmentOut,
    AttachmentsOut,
    DepartmentOption,
    DuplicateRef,
    EmployeeActivityOut,
    EmployeeActivityRowOut,
    EmployeeCreate,
    EmployeeCreateOut,
    EmployeeEventOut,
    EmployeeEventsOut,
    EmployeeKpis,
    EmployeeListOut,
    EmployeeMetaOut,
    EmployeeOut,
    EmployeeRow,
    EmployeeUpdate,
    EmployeeUpdateOut,
    MyContactIn,
    MyProfileOut,
    RequestDecisionIn,
    RoleOption,
    ShiftAssignmentOut,
    ShiftAssignmentsOut,
    TransitionIn,
    UpdateRequestIn,
    UpdateRequestOut,
    UpdateRequestsOut,
    UserOption,
)
from ..services.employee_service import (
    EmployeeError,
    EmployeeForbidden,
    EmployeeNotFound,
    EmployeeService,
    EmployeeValidationError,
    SENSITIVE_FIELDS,
)
from ..services.rbac_service import AuthorizationService
from ..services.payroll_service import PayrollError, PayrollService

router = APIRouter(prefix="/api/employees", tags=["employees"])

MODULE = "nhan_su"

# Uploaded HR files live under <backend>/static/hr and are served read-only at /static.
_STATIC_DIR = Path(__file__).resolve().parents[2] / "static"

Service = Annotated[EmployeeService, Depends(get_employee_service)]
Payroll = Annotated[PayrollService, Depends(get_payroll_service)]
Authz = Annotated[AuthorizationService, Depends(get_authorization_service)]
Users = Annotated[UserRepository, Depends(get_user_repository)]
Depts = Annotated[DepartmentRepository, Depends(get_department_repository)]
Roles = Annotated[RoleRepository, Depends(get_role_repository)]
Audit = Annotated[AuditLogRepository, Depends(get_audit_repository)]


def _scope_for(authz: AuthorizationService, user: User) -> str:
    """The caller's data scope on nhan_su (own/department/all). Defaults to `own`."""
    return authz.scope_for(user, MODULE) or "own"


def _raise(exc: Exception) -> None:
    if isinstance(exc, EmployeeNotFound):
        raise HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, EmployeeForbidden):
        raise HTTPException(status_code=403, detail=str(exc))
    if isinstance(exc, EmployeeValidationError):
        raise HTTPException(status_code=400, detail=str(exc))
    raise exc


def _dept_names(depts: DepartmentRepository, ids: set[int]) -> dict[int, str]:
    out: dict[int, str] = {}
    for did in ids:
        d = depts.get_by_id(did)
        if d is not None:
            out[did] = d.name
    return out


def _user_names(users: UserRepository, ids: set[int]) -> dict[int, str]:
    out: dict[int, str] = {}
    for uid in ids:
        u = users.get_by_id(uid)
        if u is not None:
            out[uid] = u.username
    return out


def _role_names(
    users: UserRepository, roles: RoleRepository, ids: set[int]
) -> dict[int, str]:
    """user_id → tên Vai trò (RBAC) của tài khoản, để hiện làm "Chức danh" ở list nhân sự."""
    out: dict[int, str] = {}
    for uid in ids:
        u = users.get_by_id(uid)
        if u is not None and u.role_id is not None:
            r = roles.get_by_id(u.role_id)
            if r is not None:
                out[uid] = r.name
    return out


def _row(
    employee,
    dept_names: dict[int, str],
    user_names: dict[int, str],
    role_names: dict[int, str] | None = None,
) -> EmployeeRow:
    row = EmployeeRow.model_validate(employee)
    if employee.department_id is not None:
        row.department_name = dept_names.get(employee.department_id)
    if employee.user_id is not None:
        row.account_username = user_names.get(employee.user_id)
        if role_names is not None:
            row.role_name = role_names.get(employee.user_id)
    return row


def _full(employee, depts: DepartmentRepository, users: UserRepository) -> EmployeeOut:
    out = EmployeeOut.model_validate(employee)
    if employee.department_id is not None:
        d = depts.get_by_id(employee.department_id)
        out.department_name = d.name if d is not None else None
    if employee.user_id is not None:
        u = users.get_by_id(employee.user_id)
        out.account_username = u.username if u is not None else None
    return out


# Dữ liệu nhạy cảm — DÙNG CHUNG danh sách với service (che khi đọc + gác khi ghi, N5).
_SALARY_FIELDS = SENSITIVE_FIELDS


def _mask_salary(out: EmployeeOut) -> EmployeeOut:
    for f in _SALARY_FIELDS:
        setattr(out, f, None)
    return out


def _dup(employee) -> DuplicateRef | None:
    if employee is None:
        return None
    return DuplicateRef(id=employee.id, code=employee.code, full_name=employee.full_name)


# --- list + meta ------------------------------------------------------------


@router.get("", response_model=EmployeeListOut)
def list_employees(
    svc: Service,
    authz: Authz,
    users: Users,
    depts: Depts,
    roles: Roles,
    user: Annotated[User, Depends(require_permission(MODULE, "read"))],
    q: str | None = Query(default=None),
    department_id: int | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
    has_account: bool | None = Query(default=None),
    sort: str = Query(default="code"),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=200),
) -> EmployeeListOut:
    scope = _scope_for(authz, user)
    rows, total = svc.list_employees(
        scope=scope, actor=user, q=q, department_id=department_id, status=status_filter,
        has_account=has_account, sort=sort, page=page, size=size,
    )
    dept_ids = {e.department_id for e in rows if e.department_id is not None}
    user_ids = {e.user_id for e in rows if e.user_id is not None}
    names = _dept_names(depts, dept_ids)
    unames = _user_names(users, user_ids)
    rnames = _role_names(users, roles, user_ids)

    return EmployeeListOut(
        items=[_row(e, names, unames, rnames) for e in rows],
        total=total, page=page, size=size,
        kpis=_kpis(svc.list_scoped_all(scope=scope, actor=user)),
    )


def _kpis(book) -> EmployeeKpis:
    from datetime import date, timedelta

    soon = date.today() + timedelta(days=30)
    return EmployeeKpis(
        total=len(book),
        active=sum(1 for e in book if e.status == "active"),
        probation=sum(1 for e in book if e.status == "probation"),
        on_leave=sum(1 for e in book if e.status == "on_leave"),
        resigned=sum(1 for e in book if e.status == "resigned"),
        probation_ending_soon=sum(
            1 for e in book
            if e.status == "probation" and e.probation_end_date is not None
            and date.today() <= e.probation_end_date <= soon
        ),
    )


@router.get("/meta", response_model=EmployeeMetaOut)
def get_meta(
    svc: Service,
    users: Users,
    depts: Depts,
    roles: Roles,
    user: Annotated[User, Depends(require_permission(MODULE, "read"))],
) -> EmployeeMetaOut:
    """Dropdown data: departments + roles + login accounts not yet linked to any employee."""
    departments = depts.list_all()
    dept_opts = [DepartmentOption(id=d.id, name=d.name) for d in departments]
    linked = {e.user_id for e in svc.list_scoped_all(scope="all", actor=user) if e.user_id is not None}
    unlinked = [
        UserOption(id=u.id, username=u.username, name=u.name or u.username)
        for u in users.list_all()
        if u.id not in linked
    ]
    # Vai trò gắn tài khoản (wizard + tab Tài khoản & Quyền). Role thuộc 1 phòng ban nên gom
    # theo từng phòng; số phòng nhỏ nên vòng lặp này rẻ.
    role_opts = [
        RoleOption(id=r.id, name=r.name, department_id=r.department_id)
        for d in departments
        for r in roles.list_by_department(d.id)
    ]
    return EmployeeMetaOut(
        departments=dept_opts, unlinked_users=unlinked, roles=role_opts
    )


# --- create -----------------------------------------------------------------


@router.post("", response_model=EmployeeCreateOut, status_code=status.HTTP_201_CREATED)
def create_employee(
    body: EmployeeCreate,
    svc: Service,
    payroll_svc: Payroll,
    authz: Authz,
    depts: Depts,
    users: Users,
    user: Annotated[User, Depends(require_permission(MODULE, "create"))],
) -> EmployeeCreateOut:
    data = body.model_dump()
    account = data.pop("account", None)
    initial_salary = data.pop("initial_salary", None)
    department_id = data.pop("department_id")
    status_in = data.pop("status")
    hire_date = data.pop("hire_date")
    if initial_salary is not None:
        if not authz.can(user, "luong", "update"):
            raise HTTPException(
                status_code=403,
                detail="Ban khong co quyen khai muc luong ban dau cho nhan vien.",
            )
        effective_from = initial_salary.get("effective_from") or hire_date or date.today()
        if hire_date is not None and effective_from < hire_date:
            raise HTTPException(
                status_code=400,
                detail="Ngay hieu luc luong khong duoc truoc ngay vao lam.",
            )
        initial_salary["effective_from"] = effective_from
    try:
        employee, dup_nid, dup_si = svc.create_employee(
            actor=user, department_id=department_id, status=status_in,
            hire_date=hire_date, fields=data,
            can_edit_salary=authz.can(user, MODULE, "edit_salary"),
        )
        if initial_salary is not None:
            payroll_svc.set_salary(
                employee_id=employee.id,
                actor=user,
                amount_mode="manual",
                **initial_salary,
            )
        account_username = None
        if account and account.get("username"):
            employee, _ = svc.create_account(
                employee_id=employee.id, scope="all", actor=user,
                username=account["username"], password=account["password"],
                name=account.get("name"), role_id=account.get("role_id"),
            )
            account_username = account["username"]
    except EmployeeError as exc:
        _raise(exc)
    except PayrollError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None
    return EmployeeCreateOut(
        employee=_full(employee, depts, users),
        duplicate_national_id=_dup(dup_nid),
        duplicate_social_insurance=_dup(dup_si),
        account_username=account_username,
    )


# --- self-service "Hồ sơ của tôi" (chỉ cần đăng nhập; KHÔNG cần quyền nhan_su) ------
# Phải khai TRƯỚC route "/{employee_id}" để "me" không bị hiểu là id.

# Field nội bộ HCNS — ẩn khỏi self-view của chính nhân viên.
_MY_HIDDEN = ("note", "payroll_group", "pay_grade_key")


def _my_out(employee, depts: DepartmentRepository, users: UserRepository) -> EmployeeOut:
    out = _full(employee, depts, users)
    for f in _MY_HIDDEN:
        setattr(out, f, None)
    return out


@router.get("/me", response_model=MyProfileOut)
def my_profile(svc: Service, depts: Depts, users: Users, user: CurrentUser) -> MyProfileOut:
    emp = svc.my_employee(user=user)
    if emp is None:
        return MyProfileOut(has_employee=False, employee=None)
    return MyProfileOut(has_employee=True, employee=_my_out(emp, depts, users))


@router.put("/me", response_model=MyProfileOut)
def update_my_profile(body: MyContactIn, svc: Service, depts: Depts, users: Users, user: CurrentUser) -> MyProfileOut:
    try:
        emp = svc.update_my_contact(user=user, fields=body.model_dump(exclude_unset=True))
    except EmployeeError as exc:
        _raise(exc)
    return MyProfileOut(has_employee=True, employee=_my_out(emp, depts, users))


@router.get("/me/events", response_model=EmployeeEventsOut)
def my_events(svc: Service, users: Users, user: CurrentUser) -> EmployeeEventsOut:
    items = []
    for ev in svc.my_events(user=user):
        row = EmployeeEventOut.model_validate(ev)
        if ev.actor_user_id is not None:
            u = users.get_by_id(ev.actor_user_id)
            row.actor_name = (u.name or u.username) if u is not None else None
        items.append(row)
    return EmployeeEventsOut(items=items)


@router.get("/me/attachments", response_model=AttachmentsOut)
def my_attachments(svc: Service, user: CurrentUser) -> AttachmentsOut:
    return AttachmentsOut(items=[AttachmentOut.model_validate(a) for a in svc.my_attachments(user=user)])


def _req_out(req, emp_names: dict[int, str]) -> UpdateRequestOut:
    out = UpdateRequestOut.model_validate(req)
    out.employee_name = emp_names.get(req.employee_id)
    return out


@router.post("/me/update-requests", response_model=UpdateRequestOut, status_code=201)
def create_my_request(body: UpdateRequestIn, svc: Service, user: CurrentUser) -> UpdateRequestOut:
    try:
        req = svc.create_update_request(user=user, changes=body.changes, reason=body.reason)
    except EmployeeError as exc:
        _raise(exc)
    return UpdateRequestOut.model_validate(req)


@router.get("/me/update-requests", response_model=UpdateRequestsOut)
def my_requests(svc: Service, user: CurrentUser) -> UpdateRequestsOut:
    return UpdateRequestsOut(items=[UpdateRequestOut.model_validate(r) for r in svc.my_update_requests(user=user)])


# --- HCNS duyệt yêu cầu cập nhật (quyền chi tiết `approve`) ------------------


@router.get("/update-requests", response_model=UpdateRequestsOut)
def list_requests(svc: Service, users: Users,
                  user: Annotated[User, Depends(require_permission(MODULE, "read"))],
                  status_filter: str | None = Query(default=None, alias="status")) -> UpdateRequestsOut:
    reqs = svc.list_update_requests(status=status_filter)
    emp_names: dict[int, str] = {}
    for eid in {r.employee_id for r in reqs}:
        emp = svc.employees.get_by_id(eid)
        if emp is not None:
            emp_names[eid] = emp.full_name
    return UpdateRequestsOut(items=[_req_out(r, emp_names) for r in reqs])


@router.post("/update-requests/{request_id}/approve", response_model=UpdateRequestOut)
def approve_request(request_id: int, body: RequestDecisionIn, svc: Service, authz: Authz,
                    user: Annotated[User, Depends(require_permission(MODULE, "approve"))]) -> UpdateRequestOut:
    try:
        req = svc.decide_update_request(request_id=request_id, actor=user, approve=True, note=body.note,
                                        can_edit_salary=authz.can(user, MODULE, "edit_salary"))
    except EmployeeError as exc:
        _raise(exc)
    return UpdateRequestOut.model_validate(req)


@router.post("/update-requests/{request_id}/reject", response_model=UpdateRequestOut)
def reject_request(request_id: int, body: RequestDecisionIn, svc: Service,
                   user: Annotated[User, Depends(require_permission(MODULE, "approve"))]) -> UpdateRequestOut:
    try:
        req = svc.decide_update_request(request_id=request_id, actor=user, approve=False, note=body.note)
    except EmployeeError as exc:
        _raise(exc)
    return UpdateRequestOut.model_validate(req)


# --- detail / edit ----------------------------------------------------------


@router.get("/{employee_id}", response_model=EmployeeOut)
def get_employee(
    employee_id: int,
    svc: Service,
    authz: Authz,
    depts: Depts,
    users: Users,
    user: Annotated[User, Depends(require_permission(MODULE, "read"))],
) -> EmployeeOut:
    try:
        employee = svc.get_employee(employee_id=employee_id, scope=_scope_for(authz, user), actor=user)
    except EmployeeError as exc:
        _raise(exc)
    out = _full(employee, depts, users)
    if not authz.can(user, MODULE, "view_salary"):
        _mask_salary(out)
    return out


@router.put("/{employee_id}", response_model=EmployeeUpdateOut)
def update_employee(
    employee_id: int,
    body: EmployeeUpdate,
    svc: Service,
    authz: Authz,
    depts: Depts,
    users: Users,
    user: Annotated[User, Depends(require_permission(MODULE, "update"))],
) -> EmployeeUpdateOut:
    try:
        employee, dup_nid, dup_si = svc.update_employee(
            employee_id=employee_id, scope=_scope_for(authz, user), actor=user,
            fields=body.model_dump(),
            can_edit_salary=authz.can(user, MODULE, "edit_salary"),
        )
    except EmployeeError as exc:
        _raise(exc)
    return EmployeeUpdateOut(
        employee=_full(employee, depts, users),
        duplicate_national_id=_dup(dup_nid),
        duplicate_social_insurance=_dup(dup_si),
    )


@router.put("/{employee_id}/shift")
def assign_default_shift(
    employee_id: int,
    body: AssignShiftIn,
    svc: Service,
    authz: Authz,
    user: Annotated[User, Depends(require_permission(MODULE, "update"))],
) -> dict:
    """Gán ca mặc định cho NV (an toàn, chỉ đụng default_shift_id) — panel Gán ca ở Chấm công."""
    try:
        emp, assignment = svc.set_default_shift(
            employee_id=employee_id, scope=_scope_for(authz, user), actor=user,
            shift_id=body.default_shift_id, effective_from=body.effective_from,
        )
    except EmployeeError as exc:
        _raise(exc)
    return {
        "ok": True,
        "employee_id": emp.id,
        "default_shift_id": emp.default_shift_id,
        "assignment_id": assignment.id,
        "effective_from": assignment.effective_from,
    }


@router.get("/{employee_id}/shift-history", response_model=ShiftAssignmentsOut)
def list_shift_history(
    employee_id: int,
    svc: Service,
    authz: Authz,
    user: Annotated[User, Depends(require_permission(MODULE, "read"))],
) -> ShiftAssignmentsOut:
    try:
        rows = svc.list_shift_assignments(
            employee_id=employee_id, scope=_scope_for(authz, user), actor=user
        )
    except EmployeeError as exc:
        _raise(exc)

    today = date.today()
    items: list[ShiftAssignmentOut] = []
    for index, row in enumerate(rows):
        newer = rows[index - 1] if index > 0 else None
        effective_to = newer.effective_from - timedelta(days=1) if newer is not None else None
        out = ShiftAssignmentOut.model_validate(row)
        out.effective_to = effective_to
        out.is_current = row.effective_from <= today and (
            effective_to is None or effective_to >= today
        )
        items.append(out)
    return ShiftAssignmentsOut(employee_id=employee_id, items=items)


# --- transitions (stage changes) -------------------------------------------


@router.post("/{employee_id}/transitions", response_model=EmployeeOut)
def apply_transition(
    employee_id: int,
    body: TransitionIn,
    svc: Service,
    payroll_svc: Payroll,
    authz: Authz,
    depts: Depts,
    users: Users,
    user: Annotated[User, Depends(require_permission(MODULE, "update"))],
) -> EmployeeOut:
    try:
        current = svc.get_employee(
            employee_id=employee_id, scope=_scope_for(authz, user), actor=user
        )
        employee = svc.apply_transition(
            employee_id=employee_id, scope=_scope_for(authz, user), actor=user,
            kind=body.kind, effective_date=body.effective_date, note=body.note,
            new_department_id=body.new_department_id, new_job_grade=body.new_job_grade,
            new_position=body.new_position, resign_reason=body.resign_reason,
        )
    except EmployeeError as exc:
        _raise(exc)
    except PayrollError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None
    return _full(employee, depts, users)


# --- Quá trình công tác + Nhật ký ------------------------------------------


@router.get("/{employee_id}/events", response_model=EmployeeEventsOut)
def list_events(
    employee_id: int,
    svc: Service,
    authz: Authz,
    users: Users,
    user: Annotated[User, Depends(require_permission(MODULE, "read"))],
) -> EmployeeEventsOut:
    try:
        events = svc.list_events(employee_id=employee_id, scope=_scope_for(authz, user), actor=user)
    except EmployeeError as exc:
        _raise(exc)
    items = []
    for ev in events:
        row = EmployeeEventOut.model_validate(ev)
        if ev.actor_user_id is not None:
            u = users.get_by_id(ev.actor_user_id)
            row.actor_name = (u.name or u.username) if u is not None else None
        items.append(row)
    return EmployeeEventsOut(items=items)


@router.get("/{employee_id}/activity", response_model=EmployeeActivityOut)
def list_activity(
    employee_id: int,
    svc: Service,
    authz: Authz,
    users: Users,
    audit: Audit,
    user: Annotated[User, Depends(require_permission(MODULE, "read"))],
) -> EmployeeActivityOut:
    # Access check (also 404/403 for unknown/out-of-scope) before reading the log.
    try:
        svc.get_employee(employee_id=employee_id, scope=_scope_for(authz, user), actor=user)
    except EmployeeError as exc:
        _raise(exc)
    rows = audit.list_by_target(f"employee:{employee_id}")
    items = []
    for a in rows:
        actor_name = None
        if a.actor_user_id is not None:
            u = users.get_by_id(a.actor_user_id)
            actor_name = (u.name or u.username) if u is not None else None
        items.append(EmployeeActivityRowOut(
            action=a.action, target=a.target, detail=a.detail,
            actor_name=actor_name, created_at=a.created_at,
        ))
    return EmployeeActivityOut(items=items)


# --- attachments ------------------------------------------------------------


@router.get("/{employee_id}/attachments", response_model=AttachmentsOut)
def list_attachments(
    employee_id: int,
    svc: Service,
    authz: Authz,
    user: Annotated[User, Depends(require_permission(MODULE, "read"))],
) -> AttachmentsOut:
    try:
        atts = svc.list_attachments(employee_id=employee_id, scope=_scope_for(authz, user), actor=user)
    except EmployeeError as exc:
        _raise(exc)
    return AttachmentsOut(items=[AttachmentOut.model_validate(a) for a in atts])


@router.post("/{employee_id}/attachments", response_model=AttachmentOut, status_code=201)
def upload_attachment(
    employee_id: int,
    svc: Service,
    authz: Authz,
    user: Annotated[User, Depends(require_permission(MODULE, "update"))],
    file: UploadFile = File(...),
    doc_kind: str = Form(default="khac"),
) -> AttachmentOut:
    scope = _scope_for(authz, user)
    # Access check first so we don't write a file for an inaccessible employee.
    try:
        svc.get_employee(employee_id=employee_id, scope=scope, actor=user)
    except EmployeeError as exc:
        _raise(exc)

    safe_name = Path(file.filename or "file").name
    token = secrets.token_hex(4)
    dest_dir = _STATIC_DIR / "hr" / str(employee_id)
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"{token}_{safe_name}"
    with dest.open("wb") as f:
        f.write(file.file.read())
    file_url = f"/static/hr/{employee_id}/{token}_{safe_name}"

    try:
        att = svc.add_attachment(
            employee_id=employee_id, scope=scope, actor=user, doc_kind=doc_kind,
            file_name=safe_name, file_url=file_url, file_type=file.content_type,
        )
    except EmployeeError as exc:
        _raise(exc)
    return AttachmentOut.model_validate(att)


@router.delete("/{employee_id}/attachments/{attachment_id}", status_code=204)
def delete_attachment(
    employee_id: int,
    attachment_id: int,
    svc: Service,
    authz: Authz,
    user: Annotated[User, Depends(require_permission(MODULE, "update"))],
):
    try:
        svc.delete_attachment(
            employee_id=employee_id, scope=_scope_for(authz, user), actor=user,
            attachment_id=attachment_id,
        )
    except EmployeeError as exc:
        _raise(exc)


# --- account link -----------------------------------------------------------


@router.post("/{employee_id}/account", response_model=EmployeeOut)
def attach_account(
    employee_id: int,
    body: AccountIn,
    svc: Service,
    authz: Authz,
    depts: Depts,
    users: Users,
    user: Annotated[User, Depends(require_permission(MODULE, "update"))],
) -> EmployeeOut:
    """Gắn tài khoản cho hồ sơ: TẠO MỚI (`username`+`password`) — đường chính vì mọi tài
    khoản phải sinh ra từ một hồ sơ; hoặc LIÊN KẾT tài khoản có sẵn (`user_id`) để dọn
    tài khoản mồ côi cũ."""
    scope = _scope_for(authz, user)
    try:
        if body.user_id is not None:
            employee = svc.link_account(
                employee_id=employee_id, scope=scope, actor=user, user_id=body.user_id,
            )
        elif (body.username or "").strip():
            employee, _ = svc.create_account(
                employee_id=employee_id, scope=scope, actor=user,
                username=body.username or "", password=body.password or "",
                role_id=body.role_id,
            )
        else:
            raise HTTPException(
                status_code=400, detail="Cần `username` (tạo mới) hoặc `user_id` (liên kết)."
            )
    except EmployeeError as exc:
        _raise(exc)
    return _full(employee, depts, users)


# GỠ `DELETE /{employee_id}/account` (gỡ liên kết): mọi tài khoản phải thuộc một hồ sơ, nên
# gỡ liên kết = đẻ ra tài khoản mồ côi = vi phạm luật. Muốn chặn một người thì KHÓA tài khoản
# (`PUT /api/users/{id}/active`); người nghỉ việc thì login tự chặn theo trạng thái hồ sơ.
# `POST /{employee_id}/account` (liên kết) GIỮ LẠI — đường dọn các tài khoản mồ côi cũ.
