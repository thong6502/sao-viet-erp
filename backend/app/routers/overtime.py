"""Phiếu tăng ca routes (module `tang_ca`).

- NV tự gửi/hủy/xem phiếu của MÌNH: chỉ cần đăng nhập + có hồ sơ NV (không cần ô quyền riêng).
- Tổ trưởng duyệt: `approve` + scope `department` ⇒ chỉ đụng được người trong tổ mình + cây con.
- HCNS/Admin: `approve` + scope `all`.
Real-time: gửi/hủy → broadcast cho người duyệt; quyết định → đẩy thẳng tới NV nộp phiếu.
"""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status

from ..deps import (
    CurrentUser,
    get_authorization_service,
    get_employee_repository,
    get_overtime_service,
    require_permission,
    require_any_permission,
)
from ..models.user import User
from ..realtime import hub
from ..repositories.employee_repo import EmployeeRepository
from ..schemas.overtime import (
    MyOvertimeOut,
    OvertimeBulkIn,
    OvertimeBulkRejectIn,
    OvertimeBulkResultOut,
    OvertimeDecisionIn,
    OvertimeRejectIn,
    OvertimeRequestForIn,
    OvertimeRequestIn,
    OvertimeRequestOut,
    OvertimeRequestsOut,
    OvertimeSummaryOut,
)
from ..services.overtime_service import (
    NoLinkedEmployee,
    OvertimeError,
    OvertimeForbidden,
    OvertimeNotFound,
    OvertimeService,
    OvertimeValidationError,
)
from ..services.rbac_service import AuthorizationService

router = APIRouter(prefix="/api/overtime", tags=["overtime"])

MODULE = "tang_ca"

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

Service = Annotated[OvertimeService, Depends(get_overtime_service)]
Employees = Annotated[EmployeeRepository, Depends(get_employee_repository)]
Authz = Annotated[AuthorizationService, Depends(get_authorization_service)]


def _scope(authz: AuthorizationService, user: User) -> str:
    """Phạm vi dữ liệu của người gọi trên module tăng ca. Mặc định `own` — hụt quyền thì siết
    chặt nhất, không mở toang."""
    return authz.scope_for(user, MODULE) or "own"


def _raise(exc: Exception) -> None:
    if isinstance(exc, OvertimeNotFound):
        raise HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, OvertimeForbidden):
        raise HTTPException(status_code=403, detail=str(exc))
    if isinstance(exc, (OvertimeValidationError, NoLinkedEmployee)):
        raise HTTPException(status_code=400, detail=str(exc))
    raise exc


def _out(r, emp_names: dict[int, str], decider_names: dict[int, str]) -> OvertimeRequestOut:
    o = OvertimeRequestOut.model_validate(r)
    o.employee_name = emp_names.get(r.employee_id)
    o.decided_by_name = decider_names.get(r.decided_by) if r.decided_by else None
    o.minutes = max(0, int(r.to_minute) - int(r.from_minute))
    return o


def _resolve(employees: EmployeeRepository, reqs: list) -> list[OvertimeRequestOut]:
    names: dict[int, str] = {}
    for eid in {r.employee_id for r in reqs}:
        emp = employees.get_by_id(eid)
        if emp is not None:
            names[eid] = emp.full_name
    # Người DUYỆT/từ chối là 1 user id → tra hồ sơ NV theo user_id (tổ trưởng/HCNS/GĐ đều có hồ sơ).
    decider_names: dict[int, str] = {}
    for uid in {r.decided_by for r in reqs if r.decided_by}:
        emp = employees.get_by_user_id(uid)
        if emp is not None:
            decider_names[uid] = emp.full_name
    return [_out(r, names, decider_names) for r in reqs]


# --- real-time (bám hub SSE chung; event chỉ là TÍN HIỆU nhẹ, FE tự refetch số) ------------

def _notify_pending_changed() -> None:
    """Có phiếu mới/hủy → mọi client refetch badge (người duyệt thấy số nhảy ngay)."""
    hub.broadcast({"type": "ot_pending_changed"})


def _notify_decision(r, employees: EmployeeRepository, decision: str) -> None:
    """Duyệt/từ chối → đẩy tới ĐÚNG NV nộp phiếu; kèm broadcast để badge người duyệt hạ xuống."""
    emp = employees.get_by_id(r.employee_id)
    if emp is not None and emp.user_id is not None:
        hub.publish(emp.user_id, {"type": "ot_decision", "decision": decision,
                                  "code": emp.full_name})
    hub.broadcast({"type": "ot_pending_changed"})


# --- NV tự phục vụ ----------------------------------------------------------


@router.post("/me", response_model=OvertimeRequestOut, status_code=status.HTTP_201_CREATED)
def create_my_request(body: OvertimeRequestIn, svc: Service, employees: Employees,
                      user: SelfWriter):
    """TỰ PHỤC VỤ: chỉ cần đăng nhập + có hồ sơ NV — KHÔNG bắt ô quyền riêng, đúng khuôn
    `POST /api/attendance/me/adjust-request`. Mọi người lao động đều phải xin được tăng ca cho
    CHÍNH MÌNH; quyền `tang_ca:read` chỉ quyết định có thấy màn hay không, còn `approve` mới là
    thứ phân biệt người duyệt. (Không có hồ sơ NV → service trả 400.)"""
    try:
        r = svc.create_request(actor=user, work_date=body.work_date,
                               from_minute=body.from_minute, to_minute=body.to_minute,
                               reason=body.reason)
    except OvertimeError as exc:
        _raise(exc)
    _notify_pending_changed()
    return _resolve(employees, [r])[0]


@router.get("/me", response_model=MyOvertimeOut)
def my_requests(svc: Service, employees: Employees, user: SelfUser,
                page: int = Query(default=1, ge=1),
                size: int = Query(default=20, ge=1, le=100)):
    if not svc.has_employee(user=user):
        return MyOvertimeOut(has_employee=False, page=page, size=size)
    reqs, total = svc.my_requests(user=user, page=page, size=size)
    emp = employees.get_by_user_id(user.id)
    return MyOvertimeOut(has_employee=True,
                         employee_name=emp.full_name if emp is not None else None,
                         items=_resolve(employees, reqs),
                         total=total, page=page, size=size)


@router.get("/summary", response_model=OvertimeSummaryOut)
def summary(svc: Service, authz: Authz, user: SelfUser):
    """Badge sidebar + chuông. `pending_in_scope` = None khi người gọi KHÔNG có quyền duyệt."""
    pending = None
    if authz.can(user, MODULE, "approve"):
        pending = svc.count_pending(scope=authz.scope_for(user, MODULE) or "own", actor=user)
    return OvertimeSummaryOut(pending_in_scope=pending,
                              my_decided_unseen=svc.my_unseen_count(user=user))


@router.post("/mark-seen", status_code=204)
def mark_seen(svc: Service, user: SelfUser):
    svc.mark_seen(user=user)


# --- tổ trưởng / HCNS -------------------------------------------------------


@router.post("", response_model=OvertimeRequestOut, status_code=status.HTTP_201_CREATED)
def create_for_employee(body: OvertimeRequestForIn, svc: Service, employees: Employees,
                        user: Annotated[User, Depends(require_permission(MODULE, "approve"))]):
    """Tổ trưởng tạo THẲNG cho thợ → duyệt luôn (không bắt thợ gửi rồi duyệt lại)."""
    try:
        r = svc.create_request(actor=user, work_date=body.work_date,
                               from_minute=body.from_minute, to_minute=body.to_minute,
                               reason=body.reason, employee_id=body.employee_id,
                               auto_approve=True)
    except OvertimeError as exc:
        _raise(exc)
    _notify_decision(r, employees, "approved")
    return _resolve(employees, [r])[0]


@router.get("", response_model=OvertimeRequestsOut)
def list_requests(svc: Service, employees: Employees, authz: Authz,
                  user: Annotated[User, Depends(require_permission(MODULE, "read"))],
                  status_filter: str | None = None,
                  employee_id: int | None = Query(default=None),
                  page: int = Query(default=1, ge=1),
                  size: int = Query(default=20, ge=1, le=100)):
    # `employee_id` KHÔNG nới phạm vi — chỉ lọc THÊM bên trong phạm vi đã có (xem service).
    scope = authz.scope_for(user, MODULE) or "own"
    reqs, total = svc.list_requests(scope=scope, actor=user, status=status_filter,
                                    employee_id=employee_id, page=page, size=size)
    return OvertimeRequestsOut(items=_resolve(employees, reqs),
                               total=total, page=page, size=size)


@router.post("/bulk-approve", response_model=OvertimeBulkResultOut)
def bulk_approve(body: OvertimeBulkIn, svc: Service, employees: Employees, authz: Authz,
                 user: Annotated[User, Depends(require_permission(MODULE, "approve"))]):
    done = svc.bulk_approve(actor=user, request_ids=body.ids, scope=_scope(authz, user))
    for r in done:
        _notify_decision(r, employees, "approved")
    ids = {r.id for r in done}
    return OvertimeBulkResultOut(done=sorted(ids),
                                 skipped=sorted(set(body.ids) - ids))


@router.post("/bulk-reject", response_model=OvertimeBulkResultOut)
def bulk_reject(body: OvertimeBulkRejectIn, svc: Service, employees: Employees, authz: Authz,
                user: Annotated[User, Depends(require_permission(MODULE, "approve"))]):
    try:
        done = svc.bulk_reject(actor=user, request_ids=body.ids, note=body.note,
                               scope=_scope(authz, user))
    except OvertimeError as exc:
        _raise(exc)
    for r in done:
        _notify_decision(r, employees, "rejected")
    ids = {r.id for r in done}
    return OvertimeBulkResultOut(done=sorted(ids),
                                 skipped=sorted(set(body.ids) - ids))


@router.post("/{request_id}/approve", response_model=OvertimeRequestOut)
def approve(request_id: int, body: OvertimeDecisionIn, svc: Service, employees: Employees,
            authz: Authz,
            user: Annotated[User, Depends(require_permission(MODULE, "approve"))]):
    try:
        r = svc.approve(actor=user, request_id=request_id, note=body.note,
                        scope=_scope(authz, user))
    except OvertimeError as exc:
        _raise(exc)
    _notify_decision(r, employees, "approved")
    return _resolve(employees, [r])[0]


@router.post("/{request_id}/reject", response_model=OvertimeRequestOut)
def reject(request_id: int, body: OvertimeRejectIn, svc: Service, employees: Employees,
           authz: Authz,
           user: Annotated[User, Depends(require_permission(MODULE, "approve"))]):
    try:
        r = svc.reject(actor=user, request_id=request_id, note=body.note,
                       scope=_scope(authz, user))
    except OvertimeError as exc:
        _raise(exc)
    _notify_decision(r, employees, "rejected")
    return _resolve(employees, [r])[0]


@router.put("/{request_id}", response_model=OvertimeRequestOut)
def update_my_request(request_id: int, body: OvertimeRequestIn, svc: Service, employees: Employees,
                      user: SelfOrApprover):
    """SỬA phiếu đang chờ duyệt — chỉ người tạo, chỉ khi pending (service chặn). Không cần ô quyền
    riêng (tự phục vụ, giống POST /me)."""
    try:
        r = svc.update_request(actor=user, request_id=request_id, work_date=body.work_date,
                               from_minute=body.from_minute, to_minute=body.to_minute,
                               reason=body.reason)
    except OvertimeError as exc:
        _raise(exc)
    _notify_pending_changed()
    return _resolve(employees, [r])[0]


@router.post("/{request_id}/cancel", response_model=OvertimeRequestOut)
def cancel(request_id: int, svc: Service, employees: Employees, authz: Authz, user: SelfOrApprover):
    try:
        r = svc.cancel(actor=user, request_id=request_id,
                       is_manager=authz.can(user, MODULE, "approve"))
    except OvertimeError as exc:
        _raise(exc)
    _notify_pending_changed()
    return _resolve(employees, [r])[0]
