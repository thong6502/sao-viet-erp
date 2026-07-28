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
    get_authorization_service,
    get_department_repository,
    get_employee_repository,
    require_permission,
)
from ..models.user import User
from ..repositories.employee_repo import EmployeeRepository
from ..repositories.rbac_repo import DepartmentRepository
from ..schemas.attendance import (
    AdjustIn,
    AdjustQuotaOut,
    AdjustRequestOut,
    AdjustRequestsOut,
    ApproveRequestIn,
    AttendanceLogOut,
    AttendanceLogsOut,
    CheckIn,
    CheckResultOut,
    DayDetailOut,
    MyShiftOut,
    MyStatusOut,
    NearestLocationOut,
    PreviewOut,
    RejectRequestIn,
    RequestAdjustIn,
    TodayKpiOut,
    HolidayMark,
    PeriodActionIn,
    AttendancePeriodOut,
    ShiftPlanOut,
    ShiftPlanSaveIn,
    ShiftPlanSaveOut,
    TimesheetDay,
    TimesheetOut,
    TimesheetRow,
    TodaySummaryOut,
    WorkLocationIn,
    WorkLocationOut,
    WorkLocationsOut,
    WorkShiftIn,
    WorkShiftOut,
    WorkShiftsOut,
)
from ..services.rbac_service import AuthorizationService
from ..services.attendance_service import (
    AttendanceError,
    AttendanceNotFound,
    AttendanceService,
    AttendanceValidationError,
    NoLinkedEmployee,
    min_to_hhmm,
)

router = APIRouter(prefix="/api/attendance", tags=["attendance"])

MODULE = "nhan_su"

Service = Annotated[AttendanceService, Depends(get_attendance_service)]
Employees = Annotated[EmployeeRepository, Depends(get_employee_repository)]
Depts = Annotated[DepartmentRepository, Depends(get_department_repository)]
Authz = Annotated[AuthorizationService, Depends(get_authorization_service)]


def _scope_for(authz: AuthorizationService, user: User) -> str:
    """Phạm vi dữ liệu của người gọi trên nhan_su (own/department/all). Mặc định own (an toàn)."""
    return authz.scope_for(user, MODULE) or "own"


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


def _shift_out(s) -> WorkShiftOut:
    return WorkShiftOut(
        id=s.id, name=s.name, start_time=min_to_hhmm(s.start_minute),
        end_time=min_to_hhmm(s.end_minute), is_overnight=s.is_overnight,
        night_multiplier=float(getattr(s, "night_multiplier", 1.3) or 1.3),
        grace_minutes=s.grace_minutes,
        meal_allowance=s.meal_allowance, shift_allowance=s.shift_allowance,
        is_active=s.is_active, note=s.note,
    )


# --- work shifts / ca kíp (HR) ----------------------------------------------


@router.get("/shifts", response_model=WorkShiftsOut)
def list_shifts(
    svc: Service,
    user: Annotated[User, Depends(require_permission(MODULE, "read"))],
) -> WorkShiftsOut:
    return WorkShiftsOut(items=[_shift_out(s) for s in svc.list_shifts()])


@router.post("/shifts", response_model=WorkShiftOut, status_code=status.HTTP_201_CREATED)
def create_shift(
    body: WorkShiftIn,
    svc: Service,
    user: Annotated[User, Depends(require_permission(MODULE, "create"))],
) -> WorkShiftOut:
    try:
        s = svc.create_shift(
            actor=user, name=body.name, start_time=body.start_time, end_time=body.end_time,
            is_overnight=body.is_overnight, grace_minutes=body.grace_minutes,
            meal_allowance=body.meal_allowance, shift_allowance=body.shift_allowance,
            night_multiplier=body.night_multiplier, note=body.note,
        )
    except AttendanceError as exc:
        _raise(exc)
    return _shift_out(s)


@router.put("/shifts/{shift_id}", response_model=WorkShiftOut)
def update_shift(
    shift_id: int,
    body: WorkShiftIn,
    svc: Service,
    user: Annotated[User, Depends(require_permission(MODULE, "update"))],
) -> WorkShiftOut:
    try:
        s = svc.update_shift(
            actor=user, shift_id=shift_id, name=body.name, start_time=body.start_time,
            end_time=body.end_time, is_overnight=body.is_overnight,
            grace_minutes=body.grace_minutes, meal_allowance=body.meal_allowance,
            shift_allowance=body.shift_allowance, night_multiplier=body.night_multiplier,
            note=body.note, is_active=body.is_active,
        )
    except AttendanceError as exc:
        _raise(exc)
    return _shift_out(s)


@router.delete("/shifts/{shift_id}", status_code=204)
def delete_shift(
    shift_id: int,
    svc: Service,
    user: Annotated[User, Depends(require_permission(MODULE, "delete"))],
):
    try:
        svc.delete_shift(actor=user, shift_id=shift_id)
    except AttendanceError as exc:
        _raise(exc)


# --- lưới phân ca tháng (khai ca NV × ngày) ---------------------------------


@router.get("/shift-plan", response_model=ShiftPlanOut)
def get_shift_plan(
    svc: Service,
    authz: Authz,
    user: Annotated[User, Depends(require_permission(MODULE, "read"))],
    year: int,
    month: int,
    department_id: int | None = None,
) -> ShiftPlanOut:
    """Lưới khai ca của một tháng. Lọc theo scope người gọi — tổ trưởng (scope
    `department`) chỉ thấy và sửa được tổ mình."""
    try:
        data = svc.shift_plan(
            year=year, month=month, department_id=department_id,
            scope=_scope_for(authz, user), actor=user,
        )
    except AttendanceError as exc:
        _raise(exc)
    return ShiftPlanOut(
        year=data["year"], month=data["month"], days_in_month=data["days_in_month"],
        locked=data["locked"], calendar=data["calendar"],
        shifts=[_shift_out(s) for s in data["shifts"]], rows=data["rows"],
    )


@router.put("/shift-plan", response_model=ShiftPlanSaveOut)
def save_shift_plan(
    body: ShiftPlanSaveIn,
    svc: Service,
    authz: Authz,
    user: Annotated[User, Depends(require_permission(MODULE, "update"))],
) -> ShiftPlanSaveOut:
    """Ghi hàng loạt ô lưới trong MỘT request (không lặp N request). Ô không hợp lệ
    trả về trong `rejected` kèm lý do thay vì bị bỏ qua im lặng."""
    try:
        res = svc.set_shift_plan(
            year=body.year, month=body.month,
            cells=[c.model_dump() for c in body.cells],
            scope=_scope_for(authz, user), actor=user,
        )
    except AttendanceError as exc:
        _raise(exc)
    return ShiftPlanSaveOut(**res)


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
    shift = st.get("shift")
    today = st.get("today")
    return MyStatusOut(
        has_employee=st["has_employee"],
        employee_name=st.get("employee_name"),
        next_action=st.get("next_action"),
        ot_mode=st.get("ot_mode", False),
        can_check=st.get("can_check", False),
        check_block_reason=st.get("check_block_reason"),
        last_check=AttendanceLogOut.model_validate(last) if last is not None else None,
        locations_configured=st["locations_configured"],
        shift=(MyShiftOut(id=shift.id, name=shift.name,
                          start_time=min_to_hhmm(shift.start_minute),
                          end_time=min_to_hhmm(shift.end_minute),
                          is_overnight=shift.is_overnight)
               if shift is not None else None),
        today=TodaySummaryOut(**today) if today is not None else None,
    )


@router.post("/me/preview", response_model=PreviewOut)
def preview(body: CheckIn, svc: Service, user: CurrentUser) -> PreviewOut:
    """Dry-run geofence (không ghi log) cho card chấm 'sống' — self-service."""
    try:
        res = svc.preview(user=user, latitude=body.latitude, longitude=body.longitude)
    except AttendanceError as exc:
        _raise(exc)
    return PreviewOut(**res)


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
        ot_mode=res.get("ot_mode", False),
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


@router.get("/me/timesheet", response_model=TimesheetOut)
def my_timesheet(
    svc: Service,
    depts: Depts,
    user: CurrentUser,
    year: int = Query(ge=2000, le=2100),
    month: int = Query(ge=1, le=12),
) -> TimesheetOut:
    """Bảng công tháng CỦA CHÍNH NV (self-service — chỉ cần login + hồ sơ NV, không cần quyền)."""
    try:
        data = svc.my_timesheet(user=user, year=year, month=month)
    except AttendanceError as exc:
        _raise(exc)
    return TimesheetOut(
        year=data["year"], month=data["month"], days_in_month=data["days_in_month"],
        standard_cong=data.get("standard_cong"),
        holidays=[HolidayMark(**h) for h in data.get("holidays", [])],
        rows=_timesheet_rows(svc, depts, data),
    )


# --- all logs (HR) ----------------------------------------------------------


@router.get("/logs", response_model=AttendanceLogsOut)
def list_logs(
    svc: Service,
    employees: Employees,
    authz: Authz,
    user: Annotated[User, Depends(require_permission(MODULE, "read"))],
    employee_id: int | None = Query(default=None),
) -> AttendanceLogsOut:
    logs = svc.list_logs(scope=_scope_for(authz, user), actor=user, employee_id=employee_id)
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
            shift_id=r.get("shift_id"), shift_name=r.get("shift_name"),
            days={k: TimesheetDay(**v) for k, v in r["days"].items()},
            total_days=r["total_days"], total_leave=r.get("total_leave", 0),
            paid_leave_days=r.get("paid_leave_days", 0),
            total_hours=r["total_hours"], total_cong=r.get("total_cong"),
            excused_cong=r.get("excused_cong", 0),
        ))
    return rows


@router.get("/timesheet", response_model=TimesheetOut)
def timesheet(
    svc: Service,
    depts: Depts,
    authz: Authz,
    user: Annotated[User, Depends(require_permission(MODULE, "read"))],
    year: int = Query(ge=2000, le=2100),
    month: int = Query(ge=1, le=12),
    department_id: int | None = Query(default=None),
) -> TimesheetOut:
    try:
        data = svc.monthly_timesheet(year=year, month=month, department_id=department_id,
                                     scope=_scope_for(authz, user), actor=user)
    except AttendanceError as exc:
        _raise(exc)
    return TimesheetOut(
        year=data["year"], month=data["month"], days_in_month=data["days_in_month"],
        standard_cong=data.get("standard_cong"),
        holidays=[HolidayMark(**h) for h in data.get("holidays", [])],
        rows=_timesheet_rows(svc, depts, data),
    )


@router.get("/timesheet.csv")
def timesheet_csv(
    svc: Service,
    depts: Depts,
    authz: Authz,
    user: Annotated[User, Depends(require_permission(MODULE, "read"))],
    year: int = Query(ge=2000, le=2100),
    month: int = Query(ge=1, le=12),
    department_id: int | None = Query(default=None),
) -> Response:
    try:
        data = svc.monthly_timesheet(year=year, month=month, department_id=department_id,
                                     scope=_scope_for(authz, user), actor=user)
    except AttendanceError as exc:
        _raise(exc)
    rows = _timesheet_rows(svc, depts, data)
    n = data["days_in_month"]

    buf = io.StringIO()
    buf.write("﻿")  # BOM để Excel đọc đúng tiếng Việt
    w = csv.writer(buf)
    w.writerow(["Mã", "Họ tên", "Phòng/Tổ", "Ca", *[str(d) for d in range(1, n + 1)],
                "Số công", "Tổng giờ"])
    for r in rows:
        cells = []
        for d in range(1, n + 1):
            day = r.days.get(str(d))
            if not day:
                cells.append("")
            elif day.leave:              # ngày nghỉ đã duyệt
                cells.append("P" if day.leave_paid else "KL")
            elif day.cong is not None:   # có gán ca → công theo ca
                cells.append(f"{day.cong:g}")
            elif day.hours is not None:  # chưa gán ca → số giờ
                cells.append(f"{day.hours:g}h")
            else:
                cells.append("có")
        total = f"{r.total_cong:g}" if r.total_cong is not None else str(r.total_days)
        w.writerow([r.employee_code, r.employee_name, r.department_name or "", r.shift_name or "",
                    *cells, total, f"{r.total_hours:g}"])
    return Response(
        content=buf.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="bang-cong-{year}-{month:02d}.csv"'},
    )


# --- Chốt công tháng (kỳ công) ----------------------------------------------


@router.get("/period", response_model=AttendancePeriodOut)
def get_period(svc: Service,
               user: Annotated[User, Depends(require_permission(MODULE, "read"))],
               year: int = Query(ge=2000, le=2100),
               month: int = Query(ge=1, le=12)) -> AttendancePeriodOut:
    try:
        data = svc.period_status(year=year, month=month)
    except AttendanceError as exc:
        _raise(exc)
    return AttendancePeriodOut(**data)


@router.post("/period/lock", response_model=AttendancePeriodOut)
def lock_period(body: PeriodActionIn, svc: Service,
                user: Annotated[User, Depends(require_permission(MODULE, "adjust"))]) -> AttendancePeriodOut:
    try:
        data = svc.lock_period(year=body.year, month=body.month, actor=user)
    except AttendanceError as exc:
        _raise(exc)
    return AttendancePeriodOut(**data)


@router.post("/period/reopen", response_model=AttendancePeriodOut)
def reopen_period(body: PeriodActionIn, svc: Service,
                  user: Annotated[User, Depends(require_permission(MODULE, "adjust"))]) -> AttendancePeriodOut:
    try:
        data = svc.reopen_period(year=body.year, month=body.month, actor=user)
    except AttendanceError as exc:
        _raise(exc)
    return AttendancePeriodOut(**data)


# --- "ô biết nói": chi tiết 1 ngày + điều chỉnh punch (HR) -------------------


@router.get("/day", response_model=DayDetailOut)
def day_detail(
    svc: Service,
    authz: Authz,
    user: Annotated[User, Depends(require_permission(MODULE, "read"))],
    employee_id: int = Query(),
    date: str = Query(description="YYYY-MM-DD"),
) -> DayDetailOut:
    try:
        data = svc.day_detail(scope=_scope_for(authz, user), actor=user, employee_id=employee_id, date_str=date)
    except AttendanceError as exc:
        _raise(exc)
    return DayDetailOut(**data)


@router.post("/adjust", response_model=DayDetailOut)
def adjust(
    body: AdjustIn,
    svc: Service,
    authz: Authz,
    user: Annotated[User, Depends(require_permission(MODULE, "adjust"))],
) -> DayDetailOut:
    try:
        data = svc.adjust(
            actor=user, scope=_scope_for(authz, user), employee_id=body.employee_id,
            date_str=body.date, check_type=body.check_type, time_hhmm=body.time,
            reason=body.reason, fault_party=body.fault_party,
        )
    except AttendanceError as exc:
        _raise(exc)
    return DayDetailOut(**data)


@router.delete("/logs/{log_id}", response_model=DayDetailOut)
def delete_manual_log(
    log_id: int,
    svc: Service,
    authz: Authz,
    user: Annotated[User, Depends(require_permission(MODULE, "adjust"))],
    employee_id: int = Query(),
    date: str = Query(description="YYYY-MM-DD"),
) -> DayDetailOut:
    try:
        data = svc.delete_manual(
            actor=user, scope=_scope_for(authz, user), log_id=log_id,
            employee_id=employee_id, date_str=date,
        )
    except AttendanceError as exc:
        _raise(exc)
    return DayDetailOut(**data)


# --- KPI giám sát hôm nay (HR) ----------------------------------------------


@router.get("/kpi", response_model=TodayKpiOut)
def today_kpi(
    svc: Service,
    authz: Authz,
    user: Annotated[User, Depends(require_permission(MODULE, "read"))],
) -> TodayKpiOut:
    return TodayKpiOut(**svc.today_kpi(scope=_scope_for(authz, user), actor=user))


# --- yêu cầu chỉnh công: NV tự gửi (self-service) ---------------------------


@router.post("/me/adjust-request", response_model=AdjustRequestOut)
def create_adjust_request(body: RequestAdjustIn, svc: Service, user: CurrentUser) -> AdjustRequestOut:
    try:
        data = svc.request_adjust(user=user, date_str=body.date, check_type=body.check_type,
                                  suggested_time=body.suggested_time, reason=body.reason)
    except AttendanceError as exc:
        _raise(exc)
    return AdjustRequestOut(**data)


@router.get("/me/adjust-requests", response_model=AdjustRequestsOut)
def my_adjust_requests(svc: Service, user: CurrentUser) -> AdjustRequestsOut:
    try:
        res = svc.my_requests(user=user)
    except AttendanceError as exc:
        _raise(exc)
    q = res["quota"]
    return AdjustRequestsOut(
        items=[AdjustRequestOut(**r) for r in res["items"]],
        quota=AdjustQuotaOut(year=q["year"], month=q["month"], limit=q["limit"],
                             used=q["used"], remaining=q["remaining"],
                             days=sorted(q["days"])),
    )


@router.post("/me/adjust-requests/{request_id}/cancel", response_model=AdjustRequestOut)
def cancel_adjust_request(request_id: int, svc: Service, user: CurrentUser) -> AdjustRequestOut:
    try:
        data = svc.cancel_request(user=user, request_id=request_id)
    except AttendanceError as exc:
        _raise(exc)
    return AdjustRequestOut(**data)


# --- yêu cầu chỉnh công: HCNS duyệt -----------------------------------------


@router.get("/adjust-requests", response_model=AdjustRequestsOut)
def list_adjust_requests(
    svc: Service,
    authz: Authz,
    user: Annotated[User, Depends(require_permission(MODULE, "read"))],
    status: str | None = Query(default="pending"),
) -> AdjustRequestsOut:
    items = svc.list_requests(scope=_scope_for(authz, user), actor=user,
                              status=None if status in (None, "all") else status)
    return AdjustRequestsOut(items=[AdjustRequestOut(**r) for r in items])


@router.post("/adjust-requests/{request_id}/approve", response_model=AdjustRequestOut)
def approve_adjust_request(
    request_id: int,
    body: ApproveRequestIn,
    svc: Service,
    authz: Authz,
    user: Annotated[User, Depends(require_permission(MODULE, "adjust"))],
) -> AdjustRequestOut:
    try:
        data = svc.approve_request(actor=user, scope=_scope_for(authz, user), request_id=request_id,
                                   time_hhmm=body.time, fault_party=body.fault_party, note=body.note)
    except AttendanceError as exc:
        _raise(exc)
    return AdjustRequestOut(**data)


@router.post("/adjust-requests/{request_id}/reject", response_model=AdjustRequestOut)
def reject_adjust_request(
    request_id: int,
    body: RejectRequestIn,
    svc: Service,
    authz: Authz,
    user: Annotated[User, Depends(require_permission(MODULE, "adjust"))],
) -> AdjustRequestOut:
    try:
        data = svc.reject_request(actor=user, scope=_scope_for(authz, user), request_id=request_id, note=body.note)
    except AttendanceError as exc:
        _raise(exc)
    return AdjustRequestOut(**data)
