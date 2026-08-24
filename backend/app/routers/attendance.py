"""Chấm công GPS routes (module `nhan_su`, lát Chấm công).

- Cấu hình điểm chấm công + xem toàn bộ log: gated on `nhan_su` (HR).
- Tự chấm công (me/status, check, me/logs): chỉ cần đăng nhập + có hồ sơ NV nối tài khoản
  (self-service, không cần quyền module) — công nhân dùng tài khoản của mình.
"""
from __future__ import annotations

import csv
import io
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status

from ..deps import (
    get_current_user,
    CurrentUser,
    get_attendance_service,
    get_authorization_service,
    get_department_repository,
    get_employee_repository,
    require_permission,
)
from ..models.role import SCOPE_ALL
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
    AttendanceNotifyOut,
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
    HeSoNgay,
    HolidayMark,
    PeriodActionIn,
    AttendancePeriodOut,
    ShiftChangeOut,
    ShiftChangesOut,
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

# Màn CHẤM CÔNG có khoá RIÊNG từ 10/08/2026 — trước đây dùng chung `nhan_su` với màn Hồ sơ
# nhân sự, nên cấp quyền xem hồ sơ là mở luôn bảng công cả công ty.
#
# Các ô của màn này:
#   read    — Bảng công tháng + Nhật ký chấm công
#   adjust  — Chấm bù / sửa lượt bấm ⚠️
#   lock    — Chốt kỳ / Mở lại kỳ ⚠️ (TÁCH khỏi `adjust` 10/08/2026: một cú bấm đóng băng đầu
#             vào lương toàn nhà máy, không được đi kèm quyền sửa công thường ngày)
#   approve — Duyệt yêu cầu chỉnh công
#   update  — Cấu hình chấm công: Điểm chấm công · Khai ca · Lịch & Ngày lễ (gác cả ĐỌC lẫn
#             GHI — trước đây đường đọc chỉ đòi `read` nên vai chỉ-xem đọc được toạ độ + bán
#             kính mọi điểm chấm công và lưới phân ca cả tháng)
MODULE = "cham_cong"
# Tab "Yêu cầu chỉnh công" có khoá RIÊNG (11/08/2026) — trước đây xem thì dùng chung
# `cham_cong:read`, duyệt thì dùng chung `cham_cong:adjust`. Duyệt yêu cầu chỉnh công là
# việc của người QUẢN tổ/phòng, còn `cham_cong:read` thì ai xem bảng công cũng có.
# Phạm vi chỉ `department` / `all` — duyệt yêu cầu của chính mình là vô nghĩa.
MODULE_YC_CHINH_CONG = "yeu_cau_chinh_cong"

# TỰ PHỤC VỤ (tách 10/08/2026) — một ô quyền cho MỌI việc người lao động làm với hồ sơ của CHÍNH
# MÌNH: tự chấm công, xem công/phiếu lương của mình, tự gửi đơn nghỉ / phiếu tăng ca / xin tạm ứng.
# Trước đây nhóm này không gác gì (chỉ cần đăng nhập) nên không có cách nào tắt cho một vai.
# Ba hàng rào cũ GIỮ NGUYÊN (phải có hồ sơ NV nối tài khoản · trong bán kính điểm chấm công · đúng
# khung giờ ca) — chúng chống lạm dụng, còn ô này chống truy cập.
# Ô `self_service` ĐÃ BỎ 15/08/2026 (chủ chốt). Dữ liệu của CHÍNH MÌNH là quyền đương nhiên của
# mọi tài khoản đăng nhập — xem công / phiếu / đơn của mình, và gửi · sửa · huỷ đơn của mình.
# Chặn nó là chặn người ta đi làm, chứ không bảo vệ được gì: mọi đường `/me` đã tự lọc theo hồ sơ
# gắn với tài khoản, không đọc sang ai được.
# Ba hàng rào thật GIỮ NGUYÊN: phải có hồ sơ NV nối tài khoản · trong bán kính điểm chấm công ·
# đúng khung giờ ca. Cái quyết định THẤY MÀN NÀO vẫn là ô của chính màn đó.
MODULE_TU_PHUC_VU = "self_service"
SelfUser = Annotated[User, Depends(get_current_user)]

# Ô THAO TÁC của Tự phục vụ (tách 11/08/2026). `SelfUser` (= `read`) chỉ cho XEM công / phiếu /
# đơn của chính mình; mọi đường GHI — chấm công, gửi · sửa · huỷ đơn nghỉ, phiếu tăng ca, xin đi
# muộn, xin tạm ứng, sửa hồ sơ của mình — đòi ô này.
# GHI LÀ GHI — phải có ô THAO TÁC của chính màn này (chủ chốt 15/08/2026: *"tôi chưa bật thao tác
# vẫn bấm gửi đơn được nè"*). Bấm giờ · gửi yêu cầu chỉnh công · xin đi muộn đều là ĐƯỜNG GHI,
# không phải "xem dữ liệu của mình".
#
# Khác với `SelfUser` (đọc phần của mình — quyền đương nhiên, xem chú thích ở trên).
SelfWriter = Annotated[User, Depends(require_permission(MODULE, "create"))]

Service = Annotated[AttendanceService, Depends(get_attendance_service)]
Employees = Annotated[EmployeeRepository, Depends(get_employee_repository)]
Depts = Annotated[DepartmentRepository, Depends(get_department_repository)]
Authz = Annotated[AuthorizationService, Depends(get_authorization_service)]


def _scope_for(authz: AuthorizationService, user: User) -> str:
    """Phạm vi dữ liệu của người gọi trên nhan_su (own/department/all). Mặc định own (an toàn)."""
    return authz.scope_for(user, MODULE) or "own"


def _chan_neu_khong_toan_cong_ty(authz: AuthorizationService, user: User, viec: str) -> None:
    """CHỐT / MỞ LẠI kỳ công là việc TOÀN CÔNG TY ⇒ đòi phạm vi `all`, không nhận `own`/`department`.

    Vì sao chặn chứ không thu hẹp theo phạm vi: kỳ công là MỘT bản ghi cho cả công ty
    (`attendance_periods` khoá theo năm+tháng), và chốt kỳ là chụp ảnh bảng công của TẤT CẢ nhân sự
    rồi ghi thành số liệu chốt — bảng lương khi kỳ đã khoá đọc đúng ảnh chụp đó. Cho người quản một
    tổ chốt "phần của tổ mình" thì kỳ thành nửa vời: nửa công ty có số liệu chốt, nửa kia không, mà
    bảng lương không có cách nào biết nửa nào là nửa nào.

    ⚠️ LỖ HỔNG ĐÃ ĐO ĐƯỢC 10/08/2026: trước bản vá này, endpoint chỉ hỏi "có quyền chấm bù không",
    KHÔNG hỏi người bấm quản ai. Test dựng vai phạm vi `own` bấm chốt kỳ ⇒ CHỐT ĐƯỢC, và ảnh chụp
    ra 2 dòng thuộc 2 phòng ban — tức đóng băng đầu vào lương của cả nhà máy. `Mở lại kỳ` còn nặng
    hơn: nó XOÁ SẠCH ảnh chụp đó.

    Hôm nay chưa ai nổ vì chỉ Giám đốc và TP HCNS có quyền chấm bù, cả hai đều phạm vi cả công ty.
    Đây là quả mìn chờ đúng ngày phân quyền hẹp lại."""
    if _scope_for(authz, user) != SCOPE_ALL:
        raise HTTPException(
            status_code=403,
            detail=(
                f"{viec} là việc của cả công ty — tài khoản của bạn chỉ có phạm vi trong "
                "tổ/phòng. Nhờ người có phạm vi toàn công ty thực hiện."
            ),
        )


def _ghi_cau_hinh_chung(action: str, viec: str):
    """Dependency cho các đường GHI vào dữ liệu DÙNG CHUNG cả nhà máy: điểm chấm công · khai ca ·
    lịch & ngày lễ (chủ chốt 15/08/2026).

    Ba thứ đó không thuộc một tổ nào: đổi lịch lễ hay sửa khai ca là đổi CÔNG của toàn bộ nhân
    viên. Người phạm vi "Của tôi" / "Cả phòng" mà sửa được thì họ đụng vào bảng công của cả công
    ty — cùng loại rủi ro với Chốt kỳ công, nên dùng chung một hàng rào.

    Trả về `User` để endpoint dùng như `require_permission` bình thường."""

    doi_o = require_permission(MODULE, action)

    # ⚠️ KHÔNG dùng `Annotated[...]` ở đây: file bật `from __future__ import annotations` nên chú
    # thích kiểu thành CHUỖI, mà chuỗi đó lại tham chiếu `action` — biến của closure, không nằm
    # trong globals. FastAPI giải không ra ⇒ coi `user` là tham số QUERY và trả 422 "Field
    # required". Tham số mặc định thì `Depends(...)` được tính NGAY, không qua chú thích.
    def _dep(authz: AuthorizationService = Depends(get_authorization_service),
             user: User = Depends(doi_o)) -> User:
        _chan_neu_khong_toan_cong_ty(authz, user, viec)
        return user

    return _dep


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
        is_active=s.is_active, ca_san_xuat=bool(getattr(s, "ca_san_xuat", True)), note=s.note,
    )


# --- work shifts / ca kíp (HR) ----------------------------------------------


@router.get("/shifts", response_model=WorkShiftsOut)
def list_shifts(
    svc: Service,
    user: Annotated[User, Depends(require_permission(MODULE, "manage_shifts"))],
) -> WorkShiftsOut:
    return WorkShiftsOut(items=[_shift_out(s) for s in svc.list_shifts()])


# Endpoint `/ca-lam` ĐÃ BỎ (2026-08-10) cùng hai ô "Ca làm riêng" ở màn Máy / Phòng ban: máy chạy
# liên tục, ca khai một chỗ duy nhất tại danh mục Ca kíp bên dưới.


@router.post("/shifts", response_model=WorkShiftOut, status_code=status.HTTP_201_CREATED)
def create_shift(
    body: WorkShiftIn,
    svc: Service,
    user: Annotated[User, Depends(_ghi_cau_hinh_chung("create", "Khai ca"))],
) -> WorkShiftOut:
    try:
        s = svc.create_shift(
            actor=user, name=body.name, start_time=body.start_time, end_time=body.end_time,
            is_overnight=body.is_overnight, grace_minutes=body.grace_minutes,
            meal_allowance=body.meal_allowance, shift_allowance=body.shift_allowance,
            night_multiplier=body.night_multiplier, note=body.note,
            ca_san_xuat=body.ca_san_xuat,
        )
    except AttendanceError as exc:
        _raise(exc)
    return _shift_out(s)


@router.put("/shifts/{shift_id}", response_model=WorkShiftOut)
def update_shift(
    shift_id: int,
    body: WorkShiftIn,
    svc: Service,
    user: Annotated[User, Depends(_ghi_cau_hinh_chung("update", "Khai ca"))],
) -> WorkShiftOut:
    try:
        s = svc.update_shift(
            actor=user, shift_id=shift_id, name=body.name, start_time=body.start_time,
            end_time=body.end_time, is_overnight=body.is_overnight,
            grace_minutes=body.grace_minutes, meal_allowance=body.meal_allowance,
            shift_allowance=body.shift_allowance, night_multiplier=body.night_multiplier,
            note=body.note, is_active=body.is_active, ca_san_xuat=body.ca_san_xuat,
        )
    except AttendanceError as exc:
        _raise(exc)
    return _shift_out(s)


@router.delete("/shifts/{shift_id}", status_code=204)
def delete_shift(
    shift_id: int,
    svc: Service,
    user: Annotated[User, Depends(_ghi_cau_hinh_chung("delete", "Khai ca"))],
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
    # ⚠️ ĐỌC cũng đòi ô CẤU HÌNH, không phải ô Xem. Trước 10/08/2026 đường đọc chỉ đòi `read`:
    # vai chỉ-xem không thấy tab nhưng vẫn gọi thẳng API đọc được toạ độ + bán kính mọi điểm
    # chấm công và lưới phân ca cả tháng. Giao diện ẩn tab, máy chủ thì không — đúng Luật 2.
    user: Annotated[User, Depends(require_permission(MODULE, "manage_shifts"))],
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
    user: Annotated[User, Depends(_ghi_cau_hinh_chung("update", "Khai ca (lưới phân ca)"))],
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


# --- lịch sử thay đổi ca + hộp thư của NV (chủ 28/07/2026) ------------------


@router.get("/shift-changes", response_model=ShiftChangesOut)
def list_shift_changes(
    svc: Service,
    authz: Authz,
    user: Annotated[User, Depends(require_permission(MODULE, "read"))],
    year: int | None = None,
    month: int | None = None,
    employee_id: int | None = None,
    kind: str | None = None,
) -> ShiftChangesOut:
    """Lịch sử đổi ca cho HCNS/quản lý — CẢ HAI lớp (ô lưới + ca nền).

    Lọc theo scope như `shift-plan`: tổ trưởng chỉ thấy tổ mình. `kind` để tách riêng
    *Sửa tay* (`day`) / *Ca nền* (`base`)."""
    rows = svc.shift_changes(
        scope=_scope_for(authz, user), actor=user,
        year=year, month=month, employee_id=employee_id, kind=kind,
    )
    return ShiftChangesOut(items=[ShiftChangeOut(**r) for r in rows])


@router.get("/my-shift-changes", response_model=ShiftChangesOut)
def my_shift_changes(svc: Service, user: SelfUser, unseen: bool = False) -> ShiftChangesOut:
    """Hộp thư "ca của tôi vừa bị đổi" — mọi NV có tài khoản đều xem được của CHÍNH mình,
    không cần quyền quản lý. `unseen=true` chỉ lấy tin CHƯA ĐỌC (khối báo ở màn Công của tôi)."""
    rows = svc.my_shift_changes(user=user, unseen_only=unseen)
    return ShiftChangesOut(items=[ShiftChangeOut(**r) for r in rows])


@router.post("/my-shift-changes/seen", response_model=AttendanceNotifyOut)
def mark_my_shift_changes_seen(svc: Service, user: SelfUser) -> AttendanceNotifyOut:
    svc.mark_shift_changes_seen(user=user)
    return AttendanceNotifyOut(unseen_shift_changes=0)


@router.get("/notify-summary", response_model=AttendanceNotifyOut)
def notify_summary(svc: Service, user: SelfUser) -> AttendanceNotifyOut:
    """Số nuôi badge + toast real-time (SSE đẩy `shift_changed` → FE gọi lại hàm này)."""
    return AttendanceNotifyOut(unseen_shift_changes=svc.unseen_shift_changes(user=user))


# --- work locations (HR) ----------------------------------------------------


@router.get("/locations", response_model=WorkLocationsOut)
def list_locations(
    svc: Service,
    # ⚠️ ĐỌC cũng đòi ô CẤU HÌNH, không phải ô Xem. Trước 10/08/2026 đường đọc chỉ đòi `read`:
    # vai chỉ-xem không thấy tab nhưng vẫn gọi thẳng API đọc được toạ độ + bán kính mọi điểm
    # chấm công và lưới phân ca cả tháng. Giao diện ẩn tab, máy chủ thì không — đúng Luật 2.
    user: Annotated[User, Depends(require_permission(MODULE, "manage_locations"))],
) -> WorkLocationsOut:
    return WorkLocationsOut(items=[WorkLocationOut.model_validate(l) for l in svc.list_locations()])


@router.post("/locations", response_model=WorkLocationOut, status_code=status.HTTP_201_CREATED)
def create_location(
    body: WorkLocationIn,
    svc: Service,
    user: Annotated[User, Depends(_ghi_cau_hinh_chung("create", "Điểm chấm công"))],
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
    user: Annotated[User, Depends(_ghi_cau_hinh_chung("update", "Điểm chấm công"))],
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
    user: Annotated[User, Depends(_ghi_cau_hinh_chung("delete", "Điểm chấm công"))],
):
    try:
        svc.delete_location(actor=user, location_id=location_id)
    except AttendanceError as exc:
        _raise(exc)


# --- self check-in (authenticated + linked employee) ------------------------


@router.get("/me/status", response_model=MyStatusOut)
def my_status(svc: Service, user: SelfUser) -> MyStatusOut:
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
def preview(body: CheckIn, svc: Service, user: SelfUser) -> PreviewOut:
    """Dry-run geofence (không ghi log) cho card chấm 'sống' — self-service."""
    try:
        res = svc.preview(user=user, latitude=body.latitude, longitude=body.longitude)
    except AttendanceError as exc:
        _raise(exc)
    return PreviewOut(**res)


@router.post("/check", response_model=CheckResultOut)
def check(body: CheckIn, svc: Service, user: SelfWriter) -> CheckResultOut:
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
def my_logs(svc: Service, user: SelfUser) -> AttendanceLogsOut:
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
    user: SelfUser,
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
        he_so_ngay=HeSoNgay(**data.get("he_so_ngay", {})),
        rows=_timesheet_rows(svc, depts, data),
    )


# --- all logs (HR) ----------------------------------------------------------


@router.get("/logs", response_model=AttendanceLogsOut)
def list_logs(
    svc: Service,
    employees: Employees,
    authz: Authz,
    # Ô RIÊNG `view_log` (11/08/2026) — KHÔNG dùng chung `read` với Bảng công tháng.
    # Bảng công là số công đã tổng hợp; nhật ký là TỪNG LƯỢT BẤM kèm giờ + toạ độ của từng người,
    # cả xưởng. Ai cần xem công để tính lương thì không đương nhiên cần đọc dấu chân từng người.
    user: Annotated[User, Depends(require_permission(MODULE, "view_log"))],
    employee_id: int | None = Query(default=None),
    # Tìm theo TÊN hoặc MÃ nhân viên. Lọc ở SQL (xem `AttendanceRepository.list_all`) — danh sách
    # chỉ trả 100 lượt gần nhất nên lọc ở FE là gõ tên ai cũng dễ ra "không tìm thấy".
    q: str | None = Query(default=None, max_length=100),
    # Khoảng NGÀY VN (trọn hai đầu). Có lọc ngày thì service tự nới trần dòng — một ngày của xưởng
    # đông người vượt xa 100 lượt, giữ trần cũ là lọc xong vẫn mất nửa ngày.
    tu_ngay: date | None = Query(default=None),
    den_ngay: date | None = Query(default=None),
) -> AttendanceLogsOut:
    logs = svc.list_logs(scope=_scope_for(authz, user), actor=user, employee_id=employee_id, q=q,
                         tu_ngay=tu_ngay, den_ngay=den_ngay)
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
            # Công đặc biệt — service đã tách sẵn từ 17/08/2026, tới 18/08 mới có đường ra API.
            holiday_cong=r.get("holiday_cong", 0), restday_cong=r.get("restday_cong", 0),
            plain_cong=r.get("plain_cong", 0),
        ))
    return rows


@router.get("/timesheet", response_model=TimesheetOut)
def timesheet(
    svc: Service,
    depts: Depts,
    authz: Authz,
    user: Annotated[User, Depends(require_permission(MODULE, "view_timesheet"))],
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
        he_so_ngay=HeSoNgay(**data.get("he_so_ngay", {})),
        rows=_timesheet_rows(svc, depts, data),
    )


@router.get("/timesheet.csv")
def timesheet_csv(
    svc: Service,
    depts: Depts,
    authz: Authz,
    user: Annotated[User, Depends(require_permission(MODULE, "view_timesheet"))],
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
def lock_period(body: PeriodActionIn, svc: Service, authz: Authz,
                user: Annotated[User, Depends(require_permission(MODULE, "lock"))]) -> AttendancePeriodOut:
    _chan_neu_khong_toan_cong_ty(authz, user, "Chốt kỳ công")
    try:
        data = svc.lock_period(year=body.year, month=body.month, actor=user)
    except AttendanceError as exc:
        _raise(exc)
    return AttendancePeriodOut(**data)


@router.post("/period/reopen", response_model=AttendancePeriodOut)
def reopen_period(body: PeriodActionIn, svc: Service, authz: Authz,
                  user: Annotated[User, Depends(require_permission(MODULE, "lock"))]) -> AttendancePeriodOut:
    _chan_neu_khong_toan_cong_ty(authz, user, "Mở lại kỳ công")
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
def create_adjust_request(body: RequestAdjustIn, svc: Service, user: SelfWriter) -> AdjustRequestOut:
    try:
        data = svc.request_adjust(user=user, date_str=body.date, check_type=body.check_type,
                                  suggested_time=body.suggested_time, reason=body.reason)
    except AttendanceError as exc:
        _raise(exc)
    return AdjustRequestOut(**data)


@router.get("/me/adjust-requests", response_model=AdjustRequestsOut)
def my_adjust_requests(svc: Service, user: SelfUser) -> AdjustRequestsOut:
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
def cancel_adjust_request(request_id: int, svc: Service, user: SelfWriter) -> AdjustRequestOut:
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
    user: Annotated[User, Depends(require_permission(MODULE, "approve"))],
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
    user: Annotated[User, Depends(require_permission(MODULE, "approve"))],
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
    user: Annotated[User, Depends(require_permission(MODULE, "approve"))],
) -> AdjustRequestOut:
    try:
        data = svc.reject_request(actor=user, scope=_scope_for(authz, user), request_id=request_id, note=body.note)
    except AttendanceError as exc:
        _raise(exc)
    return AdjustRequestOut(**data)
