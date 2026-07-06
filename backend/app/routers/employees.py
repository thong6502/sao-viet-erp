"""Hồ sơ nhân sự (nhan_su) routes — lát #1.

Thin HTTP shell over EmployeeService. Every route is guarded by
`require_permission('nhan_su', <action>)`; list/detail narrow to the caller's data scope
(own/department/all) resolved from their role. Stage changes (trạng thái / điều chuyển /
nâng bậc) go through `/transitions` so each writes a Quá trình công tác event.
"""
from __future__ import annotations

import secrets
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
    get_audit_repository,
    get_authorization_service,
    get_department_repository,
    get_employee_service,
    get_user_repository,
    require_permission,
)
from ..models.user import User
from ..repositories.audit_repo import AuditLogRepository
from ..repositories.rbac_repo import DepartmentRepository
from ..repositories.user_repo import UserRepository
from ..schemas.employee import (
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
    LinkAccountIn,
    TransitionIn,
    UserOption,
)
from ..services.employee_service import (
    EmployeeError,
    EmployeeForbidden,
    EmployeeNotFound,
    EmployeeService,
    EmployeeValidationError,
)
from ..services.rbac_service import AuthorizationService

router = APIRouter(prefix="/api/employees", tags=["employees"])

MODULE = "nhan_su"

# Uploaded HR files live under <backend>/static/hr and are served read-only at /static.
_STATIC_DIR = Path(__file__).resolve().parents[2] / "static"

Service = Annotated[EmployeeService, Depends(get_employee_service)]
Authz = Annotated[AuthorizationService, Depends(get_authorization_service)]
Users = Annotated[UserRepository, Depends(get_user_repository)]
Depts = Annotated[DepartmentRepository, Depends(get_department_repository)]
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


def _row(employee, dept_names: dict[int, str], user_names: dict[int, str]) -> EmployeeRow:
    row = EmployeeRow.model_validate(employee)
    if employee.department_id is not None:
        row.department_name = dept_names.get(employee.department_id)
    if employee.user_id is not None:
        row.account_username = user_names.get(employee.user_id)
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

    return EmployeeListOut(
        items=[_row(e, names, unames) for e in rows],
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
    user: Annotated[User, Depends(require_permission(MODULE, "read"))],
) -> EmployeeMetaOut:
    """Dropdown data: departments + login accounts not yet linked to any employee."""
    dept_opts = [DepartmentOption(id=d.id, name=d.name) for d in depts.list_all()]
    linked = {e.user_id for e in svc.list_scoped_all(scope="all", actor=user) if e.user_id is not None}
    unlinked = [
        UserOption(id=u.id, username=u.username, name=u.name or u.username)
        for u in users.list_all()
        if u.id not in linked
    ]
    return EmployeeMetaOut(departments=dept_opts, unlinked_users=unlinked)


# --- create -----------------------------------------------------------------


@router.post("", response_model=EmployeeCreateOut, status_code=status.HTTP_201_CREATED)
def create_employee(
    body: EmployeeCreate,
    svc: Service,
    depts: Depts,
    users: Users,
    user: Annotated[User, Depends(require_permission(MODULE, "create"))],
) -> EmployeeCreateOut:
    data = body.model_dump()
    account = data.pop("account", None)
    department_id = data.pop("department_id")
    status_in = data.pop("status")
    hire_date = data.pop("hire_date")
    try:
        employee, dup_nid, dup_si = svc.create_employee(
            actor=user, department_id=department_id, status=status_in,
            hire_date=hire_date, fields=data,
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
    return EmployeeCreateOut(
        employee=_full(employee, depts, users),
        duplicate_national_id=_dup(dup_nid),
        duplicate_social_insurance=_dup(dup_si),
        account_username=account_username,
    )


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
    return _full(employee, depts, users)


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
        )
    except EmployeeError as exc:
        _raise(exc)
    return EmployeeUpdateOut(
        employee=_full(employee, depts, users),
        duplicate_national_id=_dup(dup_nid),
        duplicate_social_insurance=_dup(dup_si),
    )


# --- transitions (stage changes) -------------------------------------------


@router.post("/{employee_id}/transitions", response_model=EmployeeOut)
def apply_transition(
    employee_id: int,
    body: TransitionIn,
    svc: Service,
    authz: Authz,
    depts: Depts,
    users: Users,
    user: Annotated[User, Depends(require_permission(MODULE, "update"))],
) -> EmployeeOut:
    try:
        employee = svc.apply_transition(
            employee_id=employee_id, scope=_scope_for(authz, user), actor=user,
            kind=body.kind, effective_date=body.effective_date, note=body.note,
            new_department_id=body.new_department_id, new_job_grade=body.new_job_grade,
            new_position=body.new_position, resign_reason=body.resign_reason,
        )
    except EmployeeError as exc:
        _raise(exc)
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
def link_account(
    employee_id: int,
    body: LinkAccountIn,
    svc: Service,
    authz: Authz,
    depts: Depts,
    users: Users,
    user: Annotated[User, Depends(require_permission(MODULE, "update"))],
) -> EmployeeOut:
    try:
        employee = svc.link_account(
            employee_id=employee_id, scope=_scope_for(authz, user), actor=user,
            user_id=body.user_id,
        )
    except EmployeeError as exc:
        _raise(exc)
    return _full(employee, depts, users)


@router.delete("/{employee_id}/account", response_model=EmployeeOut)
def unlink_account(
    employee_id: int,
    svc: Service,
    authz: Authz,
    depts: Depts,
    users: Users,
    user: Annotated[User, Depends(require_permission(MODULE, "update"))],
) -> EmployeeOut:
    try:
        employee = svc.unlink_account(
            employee_id=employee_id, scope=_scope_for(authz, user), actor=user,
        )
    except EmployeeError as exc:
        _raise(exc)
    return _full(employee, depts, users)
