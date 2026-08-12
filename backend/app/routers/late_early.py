"""Phiếu đi muộn / về sớm / nghỉ nửa buổi routes (module `di_muon`).

- NV tự gửi/sửa/hủy/xem phiếu của MÌNH: chỉ cần đăng nhập + có hồ sơ NV (không cần ô quyền riêng).
- Tổ trưởng duyệt: `approve` + scope `department` ⇒ chỉ đụng được người trong tổ mình + cây con.
- HCNS/Admin: `approve` + scope `all`.
Real-time: gửi/hủy → broadcast cho người duyệt; quyết định → đẩy thẳng tới NV nộp phiếu.
"""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from ..deps import (
    CurrentUser,
    get_attendance_repository,
    get_authorization_service,
    get_employee_repository,
    get_late_early_service,
    get_leave_repository,
    require_permission,
    require_any_permission,
)
from ..models.user import User
from ..realtime import hub
from ..repositories.attendance_repo import AttendanceRepository
from ..repositories.employee_repo import EmployeeRepository
from ..repositories.leave_repo import LeaveRepository
from ..schemas.late_early import (
    LateEarlyBulkIn,
    LateEarlyBulkRejectIn,
    LateEarlyBulkResultOut,
    LateEarlyDecisionIn,
    LateEarlyRejectIn,
    LateEarlyRequestForIn,
    LateEarlyRequestIn,
    LateEarlyRequestOut,
    LateEarlyRequestsOut,
    LateEarlyRosterEmpOut,
    LateEarlyRosterOut,
    LateEarlyRosterShiftOut,
    LateEarlySummaryOut,
    MyLateEarlyOut,
)
from ..services.late_early_service import (
    LateEarlyError,
    LateEarlyForbidden,
    LateEarlyNotFound,
    LateEarlyService,
    LateEarlyValidationError,
    NoLinkedEmployee,
)
from ..services.rbac_service import AuthorizationService

router = APIRouter(prefix="/api/late-early", tags=["late-early"])

MODULE = "di_muon"

# TỰ PHỤC VỤ (tách 10/08/2026) — một ô quyền cho MỌI việc người lao động làm với hồ sơ của CHÍNH
# MÌNH: tự chấm công, xem công/phiếu lương của mình, tự gửi đơn nghỉ / phiếu tăng ca / xin tạm ứng.
# Trước đây nhóm này không gác gì (chỉ cần đăng nhập) nên không có cách nào tắt cho một vai.
# Ba hàng rào cũ GIỮ NGUYÊN (phải có hồ sơ NV nối tài khoản · trong bán kính điểm chấm công · đúng
# khung giờ ca) — chúng chống lạm dụng, còn ô này chống truy cập.
MODULE_TU_PHUC_VU = "self_service"
SelfUser = Annotated[User, Depends(require_permission(MODULE_TU_PHUC_VU, "read"))]

# Ô THAO TÁC của Tự phục vụ (tách 11/08/2026). `SelfUser` (= `read`) chỉ cho XEM công / phiếu /
# đơn của chính mình; mọi đường GHI — chấm công, gửi · sửa · huỷ đơn nghỉ, phiếu tăng ca, xin đi
# muộn, xin tạm ứng, sửa hồ sơ của mình — đòi ô này.
SelfWriter = Annotated[User, Depends(require_permission(MODULE_TU_PHUC_VU, "create"))]
# Sửa / huỷ phiếu: người TẠO tự làm với phiếu của mình, hoặc NGƯỜI DUYỆT làm hộ ⇒ nhận
# cả hai ô. Ai không có ô nào trong hai ô này thì không đụng được — trước đây chỉ cần
# đăng nhập là gọi được, đúng chỗ tester bắt.
SelfOrApprover = Annotated[
    # Người TẠO sửa/huỷ phiếu của mình ⇒ đòi ô THAO TÁC của Tự phục vụ (`create`),
    # không phải ô Xem. Người DUYỆT làm hộ thì đi bằng ô duyệt của phân hệ.
    User, Depends(require_any_permission((MODULE_TU_PHUC_VU, "create"), (MODULE, "approve")))
]

Service = Annotated[LateEarlyService, Depends(get_late_early_service)]
Employees = Annotated[EmployeeRepository, Depends(get_employee_repository)]
Leaves = Annotated[LeaveRepository, Depends(get_leave_repository)]
Attendance = Annotated[AttendanceRepository, Depends(get_attendance_repository)]
Authz = Annotated[AuthorizationService, Depends(get_authorization_service)]


def _scope(authz: AuthorizationService, user: User) -> str:
    """Tầm dữ liệu của người gọi (own/department/all). Mặc định `own` — an toàn.

    Dùng cho CẢ đường GHI, không chỉ đường đọc: ô quyền `approve` chỉ nói "được duyệt", còn
    scope mới nói "được duyệt CHO AI"."""
    return authz.scope_for(user, MODULE) or "own"


def _raise(exc: Exception) -> None:
    if isinstance(exc, LateEarlyNotFound):
        raise HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, LateEarlyForbidden):
        raise HTTPException(status_code=403, detail=str(exc))
    if isinstance(exc, (LateEarlyValidationError, NoLinkedEmployee)):
        raise HTTPException(status_code=400, detail=str(exc))
    raise exc


def _out(r, emp_names: dict[int, str], decider_names: dict[int, str],
         type_names: dict[int, str]) -> LateEarlyRequestOut:
    o = LateEarlyRequestOut.model_validate(r)
    o.employee_name = emp_names.get(r.employee_id)
    o.decided_by_name = decider_names.get(r.decided_by) if r.decided_by else None
    o.leave_type_name = type_names.get(r.leave_type_id) if r.leave_type_id else None
    o.minutes = max(0, int(r.to_minute) - int(r.from_minute))
    return o


def _resolve(employees: EmployeeRepository, leaves: LeaveRepository,
             reqs: list) -> list[LateEarlyRequestOut]:
    names: dict[int, str] = {}
    for eid in {r.employee_id for r in reqs}:
        emp = employees.get_by_id(eid)
        if emp is not None:
            names[eid] = emp.full_name
    # Người DUYỆT là 1 user id → tra hồ sơ NV theo user_id.
    decider_names: dict[int, str] = {}
    for uid in {r.decided_by for r in reqs if r.decided_by}:
        emp = employees.get_by_user_id(uid)
        if emp is not None:
            decider_names[uid] = emp.full_name
    type_names: dict[int, str] = {}
    for tid in {r.leave_type_id for r in reqs if r.leave_type_id}:
        lt = leaves.get_type(tid)
        if lt is not None:
            type_names[tid] = lt.name
    return [_out(r, names, decider_names, type_names) for r in reqs]


# --- real-time (bám hub SSE chung; event chỉ là TÍN HIỆU nhẹ, FE tự refetch số) ------------

def _notify_pending_changed() -> None:
    """Có phiếu mới/sửa/hủy → mọi client refetch badge (người duyệt thấy số nhảy ngay)."""
    hub.broadcast({"type": "el_pending_changed"})


def _notify_decision(r, employees: EmployeeRepository, decision: str) -> None:
    """Duyệt/từ chối → đẩy tới ĐÚNG NV nộp phiếu; kèm broadcast để badge người duyệt hạ xuống."""
    emp = employees.get_by_id(r.employee_id)
    if emp is not None and emp.user_id is not None:
        hub.publish(emp.user_id, {"type": "el_decision", "decision": decision,
                                  "code": emp.full_name})
    hub.broadcast({"type": "el_pending_changed"})


# --- NV tự phục vụ ----------------------------------------------------------


@router.post("/me", response_model=LateEarlyRequestOut, status_code=status.HTTP_201_CREATED)
def create_my_request(body: LateEarlyRequestIn, svc: Service, employees: Employees,
                      leaves: Leaves, user: SelfWriter):
    """TỰ PHỤC VỤ: chỉ cần đăng nhập + có hồ sơ NV — KHÔNG bắt ô quyền riêng. Mọi người lao động
    đều phải xin đi muộn/về sớm cho CHÍNH MÌNH được; `di_muon:read` chỉ quyết định có thấy màn
    hay không, còn `approve` mới phân biệt người duyệt."""
    try:
        r = svc.create_request(actor=user, work_date=body.work_date,
                               from_minute=body.from_minute, to_minute=body.to_minute,
                               reason=body.reason, leave_type_id=body.leave_type_id)
    except LateEarlyError as exc:
        _raise(exc)
    _notify_pending_changed()
    return _resolve(employees, leaves, [r])[0]


@router.get("/me", response_model=MyLateEarlyOut)
def my_requests(svc: Service, employees: Employees, leaves: Leaves, user: SelfUser):
    if not svc.has_employee(user=user):
        return MyLateEarlyOut(has_employee=False)
    reqs = svc.my_requests(user=user)
    emp = employees.get_by_user_id(user.id)
    return MyLateEarlyOut(has_employee=True,
                          employee_name=emp.full_name if emp is not None else None,
                          items=_resolve(employees, leaves, reqs))


@router.get("/summary", response_model=LateEarlySummaryOut)
def summary(svc: Service, authz: Authz, user: SelfUser):
    """Badge sidebar + chuông. `pending_in_scope` = None khi người gọi KHÔNG có quyền duyệt."""
    pending = None
    if authz.can(user, MODULE, "approve"):
        pending = svc.count_pending(scope=authz.scope_for(user, MODULE) or "own", actor=user)
    return LateEarlySummaryOut(pending_in_scope=pending,
                               my_decided_unseen=svc.my_unseen_count(user=user))


@router.post("/mark-seen", status_code=204)
def mark_seen(svc: Service, user: SelfUser):
    svc.mark_seen(user=user)


# --- tổ trưởng / HCNS -------------------------------------------------------


@router.post("", response_model=LateEarlyRequestOut, status_code=status.HTTP_201_CREATED)
def create_for_employee(body: LateEarlyRequestForIn, svc: Service, employees: Employees,
                        leaves: Leaves, authz: Authz,
                        user: Annotated[User, Depends(require_permission(MODULE, "approve"))]):
    """Tổ trưởng khai THẲNG cho thợ → duyệt luôn (không bắt thợ gửi rồi duyệt lại)."""
    try:
        r = svc.create_request(actor=user, work_date=body.work_date,
                               from_minute=body.from_minute, to_minute=body.to_minute,
                               reason=body.reason, employee_id=body.employee_id,
                               leave_type_id=body.leave_type_id, auto_approve=True,
                               scope=_scope(authz, user))
    except LateEarlyError as exc:
        _raise(exc)
    _notify_decision(r, employees, "approved")
    return _resolve(employees, leaves, [r])[0]


@router.get("/roster", response_model=LateEarlyRosterOut)
def roster(svc: Service, employees: Employees, attendance: Attendance, authz: Authz,
           user: Annotated[User, Depends(require_permission(MODULE, "approve"))]):
    """Thợ trong tầm + danh mục ca — nuôi dropdown "Khai hộ thợ" và suy kiểu vắng (đi muộn /
    về sớm / nửa buổi) từ khung ca.

    Đặt ở ĐÂY chứ không dùng `/api/employees`: vai Tổ trưởng SX có `di_muon:approve` nhưng
    không có module `nhan_su`, nên nút khai hộ sẽ 403 với đúng người được giao dùng nó."""
    scope = _scope(authz, user)
    emps = [
        LateEarlyRosterEmpOut(
            id=e.id, code=getattr(e, "code", None), full_name=e.full_name,
            department=getattr(getattr(e, "department", None), "name", None),
            default_shift_id=getattr(e, "default_shift_id", None),
        )
        for e in employees.list_scoped_all(scope=scope, actor=user)
        if getattr(e, "status", None) != "resigned"
    ]
    emps.sort(key=lambda e: (e.full_name or "").lower())
    shifts = [
        LateEarlyRosterShiftOut(
            id=s.id, name=s.name, start_minute=s.start_minute, end_minute=s.end_minute,
            is_overnight=bool(getattr(s, "is_overnight", False)),
        )
        for s in attendance.list_shifts(active_only=True)
    ]
    return LateEarlyRosterOut(employees=emps, shifts=shifts)


@router.get("", response_model=LateEarlyRequestsOut)
def list_requests(svc: Service, employees: Employees, leaves: Leaves, authz: Authz,
                  # Màn này chỉ còn MỘT việc thật: DUYỆT phiếu của người khác — nên đọc danh sách
                  # cũng đi theo ô đó (đổi 11/08/2026, chủ chốt: *"Nút Xem với Thao tác có bị thừa
                  # không, tôi chỉ thấy Duyệt phiếu đi muộn/về sớm là dùng được thôi"*).
                  # Ai chỉ xem phiếu CỦA MÌNH thì đi bằng `/me` (ô Tự phục vụ), không qua đây.
                  user: Annotated[User, Depends(require_permission(MODULE, "approve"))],
                  status_filter: str | None = None):
    scope = authz.scope_for(user, MODULE) or "own"
    reqs = svc.list_requests(scope=scope, actor=user, status=status_filter)
    return LateEarlyRequestsOut(items=_resolve(employees, leaves, reqs))


@router.post("/bulk-approve", response_model=LateEarlyBulkResultOut)
def bulk_approve(body: LateEarlyBulkIn, svc: Service, employees: Employees, authz: Authz,
                 user: Annotated[User, Depends(require_permission(MODULE, "approve"))]):
    done = svc.bulk_approve(actor=user, request_ids=body.ids, scope=_scope(authz, user))
    for r in done:
        _notify_decision(r, employees, "approved")
    ids = {r.id for r in done}
    return LateEarlyBulkResultOut(done=sorted(ids), skipped=sorted(set(body.ids) - ids))


@router.post("/bulk-reject", response_model=LateEarlyBulkResultOut)
def bulk_reject(body: LateEarlyBulkRejectIn, svc: Service, employees: Employees, authz: Authz,
                user: Annotated[User, Depends(require_permission(MODULE, "approve"))]):
    try:
        done = svc.bulk_reject(actor=user, request_ids=body.ids, note=body.note,
                               scope=_scope(authz, user))
    except LateEarlyError as exc:
        _raise(exc)
    for r in done:
        _notify_decision(r, employees, "rejected")
    ids = {r.id for r in done}
    return LateEarlyBulkResultOut(done=sorted(ids), skipped=sorted(set(body.ids) - ids))


@router.post("/{request_id}/approve", response_model=LateEarlyRequestOut)
def approve(request_id: int, body: LateEarlyDecisionIn, svc: Service, employees: Employees,
            leaves: Leaves, authz: Authz,
            user: Annotated[User, Depends(require_permission(MODULE, "approve"))]):
    try:
        r = svc.approve(actor=user, request_id=request_id, note=body.note,
                        scope=_scope(authz, user))
    except LateEarlyError as exc:
        _raise(exc)
    _notify_decision(r, employees, "approved")
    return _resolve(employees, leaves, [r])[0]


@router.post("/{request_id}/reject", response_model=LateEarlyRequestOut)
def reject(request_id: int, body: LateEarlyRejectIn, svc: Service, employees: Employees,
           leaves: Leaves, authz: Authz,
           user: Annotated[User, Depends(require_permission(MODULE, "approve"))]):
    try:
        r = svc.reject(actor=user, request_id=request_id, note=body.note,
                       scope=_scope(authz, user))
    except LateEarlyError as exc:
        _raise(exc)
    _notify_decision(r, employees, "rejected")
    return _resolve(employees, leaves, [r])[0]


@router.put("/{request_id}", response_model=LateEarlyRequestOut)
def update_my_request(request_id: int, body: LateEarlyRequestIn, svc: Service,
                      employees: Employees, leaves: Leaves, user: SelfOrApprover):
    """SỬA phiếu đang chờ duyệt — chỉ người tạo, chỉ khi pending (service chặn)."""
    try:
        r = svc.update_request(actor=user, request_id=request_id, work_date=body.work_date,
                               from_minute=body.from_minute, to_minute=body.to_minute,
                               reason=body.reason, leave_type_id=body.leave_type_id)
    except LateEarlyError as exc:
        _raise(exc)
    _notify_pending_changed()
    return _resolve(employees, leaves, [r])[0]


@router.post("/{request_id}/cancel", response_model=LateEarlyRequestOut)
def cancel(request_id: int, svc: Service, employees: Employees, leaves: Leaves,
           authz: Authz, user: SelfOrApprover):
    try:
        r = svc.cancel(actor=user, request_id=request_id,
                       is_manager=authz.can(user, MODULE, "approve"),
                       scope=_scope(authz, user))
    except LateEarlyError as exc:
        _raise(exc)
    _notify_pending_changed()
    return _resolve(employees, leaves, [r])[0]
