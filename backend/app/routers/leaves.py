"""Nghỉ phép routes (module `nhan_su`).

- Loại nghỉ (types) + xem toàn bộ đơn + duyệt/từ chối: gated on `nhan_su` (HR).
- Tự tạo/hủy/xem đơn của mình (me): chỉ cần đăng nhập + có hồ sơ NV (self-service).
"""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status

from ..deps import (
    CurrentUser,
    get_authorization_service,
    get_employee_repository,
    get_leave_service,
    require_permission,
)
from ..models.user import User
from ..repositories.employee_repo import EmployeeRepository
from ..schemas.leave import (
    LeaveDecisionIn,
    LeaveRequestIn,
    LeaveRequestOut,
    LeaveRequestsOut,
    LeaveTypeIn,
    LeaveTypeOut,
    LeaveTypesOut,
    MyLeaveOut,
)
from ..services.leave_service import (
    LeaveError,
    LeaveForbidden,
    LeaveNotFound,
    LeaveService,
    LeaveValidationError,
    NoLinkedEmployee,
)
from ..services.rbac_service import AuthorizationService

router = APIRouter(prefix="/api/leaves", tags=["leaves"])

MODULE = "nhan_su"

Service = Annotated[LeaveService, Depends(get_leave_service)]
Employees = Annotated[EmployeeRepository, Depends(get_employee_repository)]
Authz = Annotated[AuthorizationService, Depends(get_authorization_service)]


def _raise(exc: Exception) -> None:
    if isinstance(exc, LeaveNotFound):
        raise HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, LeaveForbidden):
        raise HTTPException(status_code=403, detail=str(exc))
    if isinstance(exc, (LeaveValidationError, NoLinkedEmployee)):
        raise HTTPException(status_code=400, detail=str(exc))
    raise exc


def _req_out(r, emp_names: dict[int, str], type_map: dict) -> LeaveRequestOut:
    out = LeaveRequestOut.model_validate(r)
    out.employee_name = emp_names.get(r.employee_id)
    lt = type_map.get(r.leave_type_id)
    if lt is not None:
        out.leave_type_name = lt.name
        out.is_paid = lt.is_paid
    return out


def _resolve(svc: LeaveService, employees: EmployeeRepository, reqs: list):
    type_map = {t.id: t for t in svc.list_types()}
    emp_names: dict[int, str] = {}
    for eid in {r.employee_id for r in reqs}:
        emp = employees.get_by_id(eid)
        if emp is not None:
            emp_names[eid] = emp.full_name
    return [_req_out(r, emp_names, type_map) for r in reqs]


# --- leave types (HR) -------------------------------------------------------


@router.get("/types", response_model=LeaveTypesOut)
def list_types(svc: Service, user: Annotated[User, Depends(require_permission(MODULE, "read"))]) -> LeaveTypesOut:
    return LeaveTypesOut(items=[LeaveTypeOut.model_validate(t) for t in svc.list_types()])


@router.post("/types", response_model=LeaveTypeOut, status_code=status.HTTP_201_CREATED)
def create_type(body: LeaveTypeIn, svc: Service,
                user: Annotated[User, Depends(require_permission(MODULE, "create"))]) -> LeaveTypeOut:
    try:
        t = svc.create_type(actor=user, name=body.name, is_paid=body.is_paid,
                            annual_quota=body.annual_quota, note=body.note)
    except LeaveError as exc:
        _raise(exc)
    return LeaveTypeOut.model_validate(t)


@router.put("/types/{type_id}", response_model=LeaveTypeOut)
def update_type(type_id: int, body: LeaveTypeIn, svc: Service,
                user: Annotated[User, Depends(require_permission(MODULE, "update"))]) -> LeaveTypeOut:
    try:
        t = svc.update_type(actor=user, type_id=type_id, name=body.name, is_paid=body.is_paid,
                            annual_quota=body.annual_quota, note=body.note, is_active=body.is_active)
    except LeaveError as exc:
        _raise(exc)
    return LeaveTypeOut.model_validate(t)


@router.delete("/types/{type_id}", status_code=204)
def delete_type(type_id: int, svc: Service,
                user: Annotated[User, Depends(require_permission(MODULE, "delete"))]):
    try:
        svc.delete_type(actor=user, type_id=type_id)
    except LeaveError as exc:
        _raise(exc)


# --- self (authenticated + linked employee) ---------------------------------


@router.post("", response_model=LeaveRequestOut, status_code=status.HTTP_201_CREATED)
def create_request(body: LeaveRequestIn, svc: Service, employees: Employees, user: CurrentUser) -> LeaveRequestOut:
    try:
        r = svc.create_request(actor=user, leave_type_id=body.leave_type_id,
                               start_date=body.start_date, end_date=body.end_date, reason=body.reason)
    except LeaveError as exc:
        _raise(exc)
    return _resolve(svc, employees, [r])[0]


@router.get("/me", response_model=MyLeaveOut)
def my_requests(svc: Service, employees: Employees, user: CurrentUser) -> MyLeaveOut:
    if not svc.has_employee(user=user):
        return MyLeaveOut(has_employee=False, employee_name=None, items=[])
    reqs = svc.my_requests(user=user)
    name = None
    if reqs:
        emp = employees.get_by_id(reqs[0].employee_id)
        name = emp.full_name if emp is not None else None
    return MyLeaveOut(has_employee=True, employee_name=name, items=_resolve(svc, employees, reqs))


@router.post("/{request_id}/cancel", response_model=LeaveRequestOut)
def cancel_request(request_id: int, svc: Service, employees: Employees, authz: Authz, user: CurrentUser) -> LeaveRequestOut:
    is_hr = authz.can(user, MODULE, "update")
    try:
        r = svc.cancel(actor=user, request_id=request_id, is_hr=is_hr)
    except LeaveError as exc:
        _raise(exc)
    return _resolve(svc, employees, [r])[0]


# --- all + decisions (HR) ---------------------------------------------------


@router.get("", response_model=LeaveRequestsOut)
def list_requests(svc: Service, employees: Employees,
                  user: Annotated[User, Depends(require_permission(MODULE, "read"))],
                  status_filter: str | None = Query(default=None, alias="status")) -> LeaveRequestsOut:
    reqs = svc.list_requests(status=status_filter)
    return LeaveRequestsOut(items=_resolve(svc, employees, reqs))


@router.post("/{request_id}/approve", response_model=LeaveRequestOut)
def approve_request(request_id: int, body: LeaveDecisionIn, svc: Service, employees: Employees,
                    user: Annotated[User, Depends(require_permission(MODULE, "update"))]) -> LeaveRequestOut:
    try:
        r = svc.approve(actor=user, request_id=request_id, note=body.note)
    except LeaveError as exc:
        _raise(exc)
    return _resolve(svc, employees, [r])[0]


@router.post("/{request_id}/reject", response_model=LeaveRequestOut)
def reject_request(request_id: int, body: LeaveDecisionIn, svc: Service, employees: Employees,
                   user: Annotated[User, Depends(require_permission(MODULE, "update"))]) -> LeaveRequestOut:
    try:
        r = svc.reject(actor=user, request_id=request_id, note=body.note)
    except LeaveError as exc:
        _raise(exc)
    return _resolve(svc, employees, [r])[0]
