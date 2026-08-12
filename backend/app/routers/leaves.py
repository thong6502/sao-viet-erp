"""Nghỉ phép routes (module `nhan_su`).

- Loại nghỉ (types) + xem toàn bộ đơn + duyệt/từ chối: gated on `nhan_su` (HR).
- Tự tạo/hủy/xem đơn của mình (me): chỉ cần đăng nhập + có hồ sơ NV (self-service).
"""
from __future__ import annotations

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status

from ..deps import (
    CurrentUser,
    get_authorization_service,
    get_employee_repository,
    get_leave_service,
    require_permission,
    require_any_permission,
)
from ..models.user import User
from ..repositories.employee_repo import EmployeeRepository
from ..schemas.leave import (
    LeaveBulkIn,
    LeaveBulkRejectIn,
    LeaveBulkResultOut,
    LeaveCalendarOut,
    LeaveDecisionIn,
    LeaveRequestIn,
    LeaveRequestOut,
    LeaveRequestsOut,
    LeaveSummaryOut,
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

# Module quyền RIÊNG (tách khỏi `nhan_su`) → nhân viên thường được cấp read(own)+create+
# cancel để tự phục vụ; HCNS/Admin thêm `approve` = "leave admin" (duyệt + quản loại nghỉ +
# xem mọi đơn theo scope). Duyệt TẬP TRUNG: chỉ HCNS/Admin có `approve`.
MODULE = "nghi_phep"

# TỰ PHỤC VỤ (tách 10/08/2026) — một ô quyền cho MỌI việc người lao động làm với hồ sơ của CHÍNH
# MÌNH: tự chấm công, xem công/phiếu lương của mình, tự gửi đơn nghỉ / phiếu tăng ca / xin tạm ứng.
# Trước đây nhóm này không gác gì (chỉ cần đăng nhập) nên không có cách nào tắt cho một vai.
# Ba hàng rào cũ GIỮ NGUYÊN (phải có hồ sơ NV nối tài khoản · trong bán kính điểm chấm công · đúng
# khung giờ ca) — chúng chống lạm dụng, còn ô này chống truy cập.
MODULE_TU_PHUC_VU = "self_service"
SelfUser = Annotated[User, Depends(require_permission(MODULE_TU_PHUC_VU, "read"))]
# Sửa / huỷ phiếu: người TẠO tự làm với phiếu của mình, hoặc NGƯỜI DUYỆT làm hộ ⇒ nhận
# cả hai ô. Ai không có ô nào trong hai ô này thì không đụng được — trước đây chỉ cần
# đăng nhập là gọi được, đúng chỗ tester bắt.
SelfOrApprover = Annotated[
    # Người TẠO huỷ đơn của mình ⇒ ô THAO TÁC của Tự phục vụ (`create`), không phải ô Xem
    # (đổi 11/08/2026). Người DUYỆT huỷ hộ thì đi bằng ô duyệt của phân hệ.
    User, Depends(require_any_permission((MODULE_TU_PHUC_VU, "create"), (MODULE, "approve")))
]

Service = Annotated[LeaveService, Depends(get_leave_service)]
Employees = Annotated[EmployeeRepository, Depends(get_employee_repository)]
Authz = Annotated[AuthorizationService, Depends(get_authorization_service)]


def _scope(authz: AuthorizationService, user: User) -> str:
    """Phạm vi dữ liệu của người gọi trên module nghỉ phép. Mặc định `own` — hụt quyền thì siết
    chặt nhất, không mở toang."""
    return authz.scope_for(user, MODULE) or "own"


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


# --- Danh mục LOẠI NGHỈ ------------------------------------------------------
# Ba endpoint ghi bên dưới gác bằng ô quyền `update`, KHÔNG phải `approve` (chủ 29/07/2026).
# Lý do: chủ chốt "nghỉ phép để tổ trưởng duyệt, phạm vi trong tổ nó thôi" ⇒ tổ trưởng được cấp
# `can_approve`. Nếu danh mục vẫn gác bằng `approve` thì cấp quyền duyệt đơn là tổ trưởng sửa
# được luôn DANH MỤC LOẠI NGHỈ của cả công ty — chính sách toàn công ty, phải giữ ở HCNS.
# `update` trước đó KHÔNG dùng ở module này nên đổi sang đây không cướp quyền của ai:
# HCNS (`_leave_admin`) có `can_update=True` giữ nguyên, mọi vai khác đều `False`.


@router.get("/types", response_model=LeaveTypesOut)
def list_types(svc: Service, user: Annotated[User, Depends(require_permission(MODULE, "read"))]) -> LeaveTypesOut:
    return LeaveTypesOut(items=[LeaveTypeOut.model_validate(t) for t in svc.list_types()])


@router.post("/types", response_model=LeaveTypeOut, status_code=status.HTTP_201_CREATED)
def create_type(body: LeaveTypeIn, svc: Service,
                user: Annotated[User, Depends(require_permission(MODULE, "update"))]) -> LeaveTypeOut:
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
                user: Annotated[User, Depends(require_permission(MODULE, "update"))]):
    try:
        svc.delete_type(actor=user, type_id=type_id)
    except LeaveError as exc:
        _raise(exc)


# --- self (authenticated + linked employee) ---------------------------------


@router.post("", response_model=LeaveRequestOut, status_code=status.HTTP_201_CREATED)
def create_request(body: LeaveRequestIn, svc: Service, employees: Employees,
                   # XIN NGHỈ CHO CHÍNH MÌNH ⇒ ô Thao tác của **Tự phục vụ**, cùng chỗ với xin
                   # tăng ca · đi muộn · tạm ứng (đổi 11/08/2026). Trước đó đòi `nghi_phep:create`
                   # — riêng nghỉ phép một kiểu, nên chủ chốt tắt ô Thao tác của Tự phục vụ mà vẫn
                   # xin nghỉ được. Vẫn nhận `nghi_phep:create` cho ca HCNS **nhập đơn hộ** thợ
                   # không dùng máy.
                   user: Annotated[User, Depends(require_any_permission(
                       (MODULE_TU_PHUC_VU, "create"), (MODULE, "create")))]) -> LeaveRequestOut:
    try:
        r = svc.create_request(actor=user, leave_type_id=body.leave_type_id,
                               start_date=body.start_date, end_date=body.end_date, reason=body.reason)
    except LeaveError as exc:
        _raise(exc)
    return _resolve(svc, employees, [r])[0]


@router.get("/me", response_model=MyLeaveOut)
def my_requests(svc: Service, employees: Employees,
                user: Annotated[User, Depends(require_permission(MODULE, "read"))],
                page: int = Query(default=1, ge=1),
                size: int = Query(default=20, ge=1, le=100)) -> MyLeaveOut:
    if not svc.has_employee(user=user):
        return MyLeaveOut(has_employee=False, employee_name=None, items=[], quotas=[],
                          total=0, page=page, size=size)
    reqs, total = svc.my_requests(user=user, page=page, size=size)
    # Tên lấy từ HỒ SƠ GẮN TÀI KHOẢN, không suy từ `reqs[0]` như trước: sang trang 2 mà trang đó
    # rỗng (hoặc NV chưa có đơn nào) thì `reqs` rỗng ⇒ tên biến mất giữa chừng.
    emp = employees.get_by_user_id(user.id)
    name = emp.full_name if emp is not None else None
    quotas = svc.my_quotas(user=user, year=date.today().year)
    return MyLeaveOut(has_employee=True, employee_name=name,
                      items=_resolve(svc, employees, reqs), quotas=quotas,
                      total=total, page=page, size=size)


@router.get("/summary", response_model=LeaveSummaryOut)
def leave_summary(svc: Service, authz: Authz,
                  user: Annotated[User, Depends(require_permission(MODULE, "read"))]) -> LeaveSummaryOut:
    """Badge sidebar: số đơn CHỜ DUYỆT trong scope. Trả None nếu người gọi không có quyền
    duyệt → client ẩn badge (không lộ số cho người không phận sự)."""
    unseen = svc.my_unseen_count(user=user)   # chuông: đơn của TÔI vừa được quyết (mọi NV)
    if not authz.can(user, MODULE, "approve"):
        return LeaveSummaryOut(pending_in_scope=None, my_decided_unseen=unseen)
    scope = authz.scope_for(user, MODULE) or "own"
    return LeaveSummaryOut(pending_in_scope=svc.count_pending(scope=scope, actor=user), my_decided_unseen=unseen)


@router.post("/mark-seen", status_code=204)
def mark_seen(svc: Service,
              user: Annotated[User, Depends(require_permission(MODULE, "read"))]):
    """NV xác nhận đã xem kết quả các đơn của mình (đóng chuông)."""
    svc.mark_seen(user=user)


@router.get("/calendar", response_model=LeaveCalendarOut)
def leave_calendar(svc: Service, authz: Authz,
                   user: Annotated[User, Depends(require_permission(MODULE, "approve"))],
                   year: int = Query(...), month: int = Query(..., ge=1, le=12)) -> LeaveCalendarOut:
    """Lịch nghỉ trong tháng (đã duyệt + đang chờ) — để tránh duyệt trùng người.

    LỌC THEO PHẠM VI người xem: HCNS (scope `all`) thấy toàn công ty, tổ trưởng chỉ thấy tổ mình.
    Màn này gác bằng ô `approve`, mà từ 29/07/2026 tổ trưởng cũng có cờ đó."""
    return LeaveCalendarOut(**svc.calendar(year=year, month=month,
                                          scope=_scope(authz, user), actor=user))


@router.post("/{request_id}/cancel", response_model=LeaveRequestOut)
def cancel_request(request_id: int, svc: Service, employees: Employees, authz: Authz, user: SelfOrApprover) -> LeaveRequestOut:
    is_hr = authz.can(user, MODULE, "approve")
    try:
        r = svc.cancel(actor=user, request_id=request_id, is_hr=is_hr,
                       scope=_scope(authz, user))
    except LeaveError as exc:
        _raise(exc)
    return _resolve(svc, employees, [r])[0]


# --- all + decisions (HR) ---------------------------------------------------


@router.get("", response_model=LeaveRequestsOut)
def list_requests(svc: Service, employees: Employees, authz: Authz,
                  user: Annotated[User, Depends(require_permission(MODULE, "read"))],
                  status_filter: str | None = Query(default=None, alias="status"),
                  employee_id: int | None = Query(default=None),
                  page: int = Query(default=1, ge=1),
                  size: int = Query(default=20, ge=1, le=100)) -> LeaveRequestsOut:
    # Data-scope: HCNS/Admin (scope=all) thấy mọi đơn; NV (scope=own) chỉ thấy đơn của mình.
    # `employee_id` KHÔNG nới phạm vi — nó lọc THÊM bên trong phạm vi đã có (xem service).
    scope = authz.scope_for(user, MODULE) or "own"
    reqs, total = svc.list_requests(scope=scope, actor=user, status=status_filter,
                                    employee_id=employee_id, page=page, size=size)
    return LeaveRequestsOut(items=_resolve(svc, employees, reqs),
                            total=total, page=page, size=size)


@router.post("/{request_id}/approve", response_model=LeaveRequestOut)
def approve_request(request_id: int, body: LeaveDecisionIn, svc: Service, employees: Employees,
                    authz: Authz,
                    user: Annotated[User, Depends(require_permission(MODULE, "approve"))]) -> LeaveRequestOut:
    try:
        r = svc.approve(actor=user, request_id=request_id, note=body.note,
                        scope=_scope(authz, user))
    except LeaveError as exc:
        _raise(exc)
    return _resolve(svc, employees, [r])[0]


@router.post("/{request_id}/reject", response_model=LeaveRequestOut)
def reject_request(request_id: int, body: LeaveDecisionIn, svc: Service, employees: Employees,
                   authz: Authz,
                   user: Annotated[User, Depends(require_permission(MODULE, "approve"))]) -> LeaveRequestOut:
    try:
        r = svc.reject(actor=user, request_id=request_id, note=body.note,
                       scope=_scope(authz, user))
    except LeaveError as exc:
        _raise(exc)
    return _resolve(svc, employees, [r])[0]


@router.post("/bulk-approve", response_model=LeaveBulkResultOut)
def bulk_approve(body: LeaveBulkIn, svc: Service, authz: Authz,
                 user: Annotated[User, Depends(require_permission(MODULE, "approve"))]) -> LeaveBulkResultOut:
    return LeaveBulkResultOut(**svc.bulk_approve(actor=user, ids=body.ids,
                                                scope=_scope(authz, user)))


@router.post("/bulk-reject", response_model=LeaveBulkResultOut)
def bulk_reject(body: LeaveBulkRejectIn, svc: Service, authz: Authz,
                user: Annotated[User, Depends(require_permission(MODULE, "approve"))]) -> LeaveBulkResultOut:
    try:
        res = svc.bulk_reject(actor=user, ids=body.ids, note=body.note,
                              scope=_scope(authz, user))
    except LeaveError as exc:
        _raise(exc)
    return LeaveBulkResultOut(**res)
