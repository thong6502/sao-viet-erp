"""Chấm công GPS routes (module `nhan_su`, lát Chấm công).

- Cấu hình điểm chấm công + xem toàn bộ log: gated on `nhan_su` (HR).
- Tự chấm công (me/status, check, me/logs): chỉ cần đăng nhập + có hồ sơ NV nối tài khoản
  (self-service, không cần quyền module) — công nhân dùng tài khoản của mình.
"""
from __future__ import annotations

import csv
import io
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status

from ..deps import (
    CurrentUser,
    get_attendance_service,
    get_department_repository,
    get_employee_repository,
    require_permission,
)
from ..models.user import User
from ..repositories.employee_repo import EmployeeRepository
from ..repositories.rbac_repo import DepartmentRepository
from ..schemas.attendance import (
    AttendanceLogOut,
    AttendanceLogsOut,
    CheckIn,
    CheckResultOut,
    MyStatusOut,
    NearestLocationOut,
    TimesheetDay,
    TimesheetOut,
    TimesheetRow,
    WorkLocationIn,
    WorkLocationOut,
    WorkLocationsOut,
)
from ..services.attendance_service import (
    AttendanceError,
    AttendanceNotFound,
    AttendanceService,
    AttendanceValidationError,
    NoLinkedEmployee,
)

router = APIRouter(prefix="/api/attendance", tags=["attendance"])

MODULE = "nhan_su"

Service = Annotated[AttendanceService, Depends(get_attendance_service)]
Employees = Annotated[EmployeeRepository, Depends(get_employee_repository)]
Depts = Annotated[DepartmentRepository, Depends(get_department_repository)]


def _raise(exc: Exception) -> None:
    if isinstance(exc, AttendanceNotFound):
        raise HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, (AttendanceValidationError, NoLinkedEmployee)):
        raise HTTPException(status_code=400, detail=str(exc))
    raise exc


def _log_out(log, emp_names: dict[int, str], loc_names: dict[int, str]) -> AttendanceLogOut:
    out = AttendanceLogOut.model_validate(log)
    out.employee_name = emp_names.get(log.employee_id)
    if log.work_location_id is not None:
        out.location_name = loc_names.get(log.work_location_id)
    return out


# --- work locations (HR) ----------------------------------------------------


@router.get("/locations", response_model=WorkLocationsOut)
def list_locations(
    svc: Service,
    user: Annotated[User, Depends(require_permission(MODULE, "read"))],
) -> WorkLocationsOut:
    return WorkLocationsOut(items=[WorkLocationOut.model_validate(l) for l in svc.list_locations()])


@router.post("/locations", response_model=WorkLocationOut, status_code=status.HTTP_201_CREATED)
def create_location(
    body: WorkLocationIn,
    svc: Service,
    user: Annotated[User, Depends(require_permission(MODULE, "create"))],
) -> WorkLocationOut:
    try:
        loc = svc.create_location(
            actor=user, name=body.name, latitude=body.latitude, longitude=body.longitude,
            radius_m=body.radius_m, note=body.note,
        )
    except AttendanceError as exc:
        _raise(exc)
    return WorkLocationOut.model_validate(loc)


@router.put("/locations/{location_id}", response_model=WorkLocationOut)
def update_location(
    location_id: int,
    body: WorkLocationIn,
    svc: Service,
    user: Annotated[User, Depends(require_permission(MODULE, "update"))],
) -> WorkLocationOut:
    try:
        loc = svc.update_location(
            actor=user, location_id=location_id, name=body.name, latitude=body.latitude,
            longitude=body.longitude, radius_m=body.radius_m, note=body.note, is_active=body.is_active,
        )
    except AttendanceError as exc:
        _raise(exc)
    return WorkLocationOut.model_validate(loc)


@router.delete("/locations/{location_id}", status_code=204)
def delete_location(
    location_id: int,
    svc: Service,
    user: Annotated[User, Depends(require_permission(MODULE, "delete"))],
):
    try:
        svc.delete_location(actor=user, location_id=location_id)
    except AttendanceError as exc:
        _raise(exc)


# --- self check-in (authenticated + linked employee) ------------------------


@router.get("/me/status", response_model=MyStatusOut)
def my_status(svc: Service, user: CurrentUser) -> MyStatusOut:
    st = svc.my_status(user=user)
    last = st.get("last_check")
    return MyStatusOut(
        has_employee=st["has_employee"],
        employee_name=st.get("employee_name"),
        next_action=st.get("next_action"),
        last_check=AttendanceLogOut.model_validate(last) if last is not None else None,
        locations_configured=st["locations_configured"],
    )


@router.post("/check", response_model=CheckResultOut)
def check(body: CheckIn, svc: Service, user: CurrentUser) -> CheckResultOut:
    try:
        res = svc.check(user=user, latitude=body.latitude, longitude=body.longitude)
    except AttendanceError as exc:
        _raise(exc)
    nearest = res["nearest_location"]
    return CheckResultOut(
        success=res["success"],
        within_range=res["within_range"],
        check_type=res["check_type"],
        distance_m=res["distance_m"],
        nearest_location=(NearestLocationOut(id=nearest.id, name=nearest.name, radius_m=nearest.radius_m)
                          if nearest is not None else None),
        message=res["message"],
        log=AttendanceLogOut.model_validate(res["log"]) if res["log"] is not None else None,
    )


@router.get("/me/logs", response_model=AttendanceLogsOut)
def my_logs(svc: Service, user: CurrentUser) -> AttendanceLogsOut:
    try:
        logs = svc.my_logs(user=user)
    except AttendanceError as exc:
        _raise(exc)
    loc_names = {l.id: l.name for l in svc.list_locations()}
    name = svc.my_status(user=user).get("employee_name")
    emp_names = {logs[0].employee_id: name} if logs else {}
    return AttendanceLogsOut(items=[_log_out(l, emp_names, loc_names) for l in logs])


# --- all logs (HR) ----------------------------------------------------------


@router.get("/logs", response_model=AttendanceLogsOut)
def list_logs(
    svc: Service,
    employees: Employees,
    user: Annotated[User, Depends(require_permission(MODULE, "read"))],
    employee_id: int | None = Query(default=None),
) -> AttendanceLogsOut:
    logs = svc.list_logs(employee_id=employee_id)
    loc_names = {l.id: l.name for l in svc.list_locations()}
    emp_names: dict[int, str] = {}
    for eid in {l.employee_id for l in logs}:
        emp = employees.get_by_id(eid)
        if emp is not None:
            emp_names[eid] = emp.full_name
    return AttendanceLogsOut(items=[_log_out(l, emp_names, loc_names) for l in logs])


# --- bảng công tháng (HR) ---------------------------------------------------


def _timesheet_rows(svc: AttendanceService, depts: DepartmentRepository, data: dict) -> list[TimesheetRow]:
    dept_names: dict[int, str] = {}
    rows: list[TimesheetRow] = []
    for r in data["rows"]:
        dn = None
        did = r["department_id"]
        if did is not None:
            if did not in dept_names:
                d = depts.get_by_id(did)
                dept_names[did] = d.name if d is not None else ""
            dn = dept_names[did] or None
        rows.append(TimesheetRow(
            employee_id=r["employee_id"], employee_code=r["employee_code"],
            employee_name=r["employee_name"], department_id=did, department_name=dn,
            days={k: TimesheetDay(**v) for k, v in r["days"].items()},
            total_days=r["total_days"], total_hours=r["total_hours"],
        ))
    return rows


@router.get("/timesheet", response_model=TimesheetOut)
def timesheet(
    svc: Service,
    depts: Depts,
    user: Annotated[User, Depends(require_permission(MODULE, "read"))],
    year: int = Query(ge=2000, le=2100),
    month: int = Query(ge=1, le=12),
    department_id: int | None = Query(default=None),
) -> TimesheetOut:
    try:
        data = svc.monthly_timesheet(year=year, month=month, department_id=department_id)
    except AttendanceError as exc:
        _raise(exc)
    return TimesheetOut(
        year=data["year"], month=data["month"], days_in_month=data["days_in_month"],
        rows=_timesheet_rows(svc, depts, data),
    )


@router.get("/timesheet.csv")
def timesheet_csv(
    svc: Service,
    depts: Depts,
    user: Annotated[User, Depends(require_permission(MODULE, "read"))],
    year: int = Query(ge=2000, le=2100),
    month: int = Query(ge=1, le=12),
    department_id: int | None = Query(default=None),
) -> Response:
    try:
        data = svc.monthly_timesheet(year=year, month=month, department_id=department_id)
    except AttendanceError as exc:
        _raise(exc)
    rows = _timesheet_rows(svc, depts, data)
    n = data["days_in_month"]

    buf = io.StringIO()
    buf.write("﻿")  # BOM để Excel đọc đúng tiếng Việt
    w = csv.writer(buf)
    w.writerow(["Mã", "Họ tên", "Phòng/Tổ", *[str(d) for d in range(1, n + 1)], "Số công", "Tổng giờ"])
    for r in rows:
        cells = []
        for d in range(1, n + 1):
            day = r.days.get(str(d))
            cells.append(f"{day.hours:g}h" if (day and day.hours is not None) else ("có" if day else ""))
        w.writerow([r.employee_code, r.employee_name, r.department_name or "",
                    *cells, r.total_days, f"{r.total_hours:g}"])
    return Response(
        content=buf.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="bang-cong-{year}-{month:02d}.csv"'},
    )
