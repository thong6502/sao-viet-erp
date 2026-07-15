"""Đơn hàng bán (Order) routes — redesign-don-hang-ban.md (P1 khung đơn).

P1: list / get / enums / activity / create (từ báo giá | nhập tay) / update (khi nháp).
Cọc/duyệt/chốt/hủy = P2–P5.
"""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status

from ..deps import (
    get_authorization_service,
    get_current_user,
    get_order_service,
    require_permission,
)
from ..models.user import User
from ..schemas.order import (
    ApprovalActionIn,
    OrderActivityOut,
    OrderCancelIn,
    OrderCreate,
    OrderDepositIn,
    OrderDetailOut,
    OrderEnumsOut,
    OrderListOut,
    OrderStatsOut,
    OrderUpdate,
)
from ..services.order_service import (
    OrderConflict,
    OrderForbidden,
    OrderNotFound,
    OrderService,
    OrderValidationError,
)
from ..services.rbac_service import AuthorizationService

router = APIRouter(prefix="/api/orders", tags=["orders"])

MODULE = "don_hang_ban"

Service = Annotated[OrderService, Depends(get_order_service)]
Authz = Annotated[AuthorizationService, Depends(get_authorization_service)]
CurrentUser = Annotated[User, Depends(get_current_user)]


def _scope_for(authz: AuthorizationService, user: User) -> str:
    return authz.scope_for(user, MODULE) or "own"


_SCOPE_RANK = {"own": 0, "department": 1, "all": 2}


def _effective_scope(role_scope: str, view_scope: str | None) -> str:
    """Lọc phạm vi FE (Của tôi/Cả phòng/Tất cả) — KẸP về quyền: không cho xem rộng hơn."""
    if not view_scope or view_scope not in _SCOPE_RANK:
        return role_scope
    return view_scope if _SCOPE_RANK[view_scope] <= _SCOPE_RANK.get(role_scope, 2) else role_scope


def _map(exc: Exception) -> HTTPException:
    if isinstance(exc, OrderNotFound):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    if isinstance(exc, OrderForbidden):
        return HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
    if isinstance(exc, OrderConflict):
        return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    if isinstance(exc, OrderValidationError):
        return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
    raise exc


@router.get("/enums", response_model=OrderEnumsOut)
def get_enums(
    _user: Annotated[User, Depends(require_permission(MODULE, "read"))],
    svc: Service,
) -> OrderEnumsOut:
    return svc.enums()


@router.get("", response_model=OrderListOut)
def list_orders(
    user: Annotated[User, Depends(require_permission(MODULE, "read"))],
    svc: Service,
    authz: Authz,
    q: str | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
    order_kind: str | None = Query(default=None),
    approval_state: str | None = Query(default=None),
    view_scope: str | None = Query(default=None),
    sort: str = Query(default="-created_at"),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=200),
) -> OrderListOut:
    scope = _effective_scope(_scope_for(authz, user), view_scope)
    return svc.list(
        actor=user, scope=scope, q=q, status=status_filter, order_kind=order_kind,
        approval_state=approval_state, sort=sort, page=page, size=size,
    )


@router.get("/stats", response_model=OrderStatsOut)
def get_stats(
    user: Annotated[User, Depends(require_permission(MODULE, "read"))],
    svc: Service,
    authz: Authz,
    view_scope: str | None = Query(default=None),
) -> OrderStatsOut:
    return svc.stats(actor=user, scope=_effective_scope(_scope_for(authz, user), view_scope))


@router.get("/{order_id}", response_model=OrderDetailOut)
def get_order(
    order_id: int,
    user: Annotated[User, Depends(require_permission(MODULE, "read"))],
    svc: Service,
    authz: Authz,
) -> OrderDetailOut:
    try:
        return svc.get(order_id=order_id, actor=user, scope=_scope_for(authz, user))
    except Exception as exc:
        raise _map(exc)


@router.get("/{order_id}/activity", response_model=OrderActivityOut)
def get_activity(
    order_id: int,
    user: Annotated[User, Depends(require_permission(MODULE, "read"))],
    svc: Service,
    authz: Authz,
) -> OrderActivityOut:
    try:
        return svc.activity(order_id=order_id, actor=user, scope=_scope_for(authz, user))
    except Exception as exc:
        raise _map(exc)


@router.post("", response_model=OrderDetailOut, status_code=status.HTTP_201_CREATED)
def create_order(
    payload: OrderCreate,
    user: Annotated[User, Depends(require_permission(MODULE, "create"))],
    svc: Service,
    authz: Authz,
) -> OrderDetailOut:
    try:
        return svc.create(actor=user, scope=_scope_for(authz, user), payload=payload)
    except Exception as exc:
        raise _map(exc)


@router.put("/{order_id}", response_model=OrderDetailOut)
def update_order(
    order_id: int,
    payload: OrderUpdate,
    user: Annotated[User, Depends(require_permission(MODULE, "update"))],
    svc: Service,
    authz: Authz,
) -> OrderDetailOut:
    try:
        return svc.update(order_id=order_id, actor=user, scope=_scope_for(authz, user), payload=payload)
    except Exception as exc:
        raise _map(exc)


# --- Hủy đơn (P5) — nháp: `update`; đã chốt: cần `approve_exception` -----------
@router.post("/{order_id}/cancel", response_model=OrderDetailOut)
def cancel_order(
    order_id: int,
    payload: OrderCancelIn,
    user: Annotated[User, Depends(require_permission(MODULE, "update"))],
    svc: Service,
    authz: Authz,
) -> OrderDetailOut:
    elevated = authz.can(user, MODULE, "approve_exception")
    try:
        return svc.cancel(
            order_id=order_id, actor=user, scope=_scope_for(authz, user),
            reason=payload.reason, fault=payload.fault, can_cancel_ordered=elevated,
        )
    except Exception as exc:
        raise _map(exc)


# --- Chốt đơn (P4) — quyền `manage_status` ------------------------------------
@router.post("/{order_id}/confirm", response_model=OrderDetailOut)
def confirm_order(
    order_id: int,
    user: Annotated[User, Depends(require_permission(MODULE, "manage_status"))],
    svc: Service,
    authz: Authz,
) -> OrderDetailOut:
    try:
        return svc.confirm(order_id=order_id, actor=user, scope=_scope_for(authz, user))
    except Exception as exc:
        raise _map(exc)


# --- Duyệt đơn đặc thù (P3) — luật trình-duyệt --------------------------------
@router.post("/{order_id}/submit", response_model=OrderDetailOut)
def submit_for_approval(
    order_id: int,
    user: Annotated[User, Depends(require_permission(MODULE, "update"))],
    svc: Service,
    authz: Authz,
) -> OrderDetailOut:
    try:
        return svc.submit_for_approval(order_id=order_id, actor=user, scope=_scope_for(authz, user))
    except Exception as exc:
        raise _map(exc)


@router.post("/{order_id}/approve", response_model=OrderDetailOut)
def approve_order(
    order_id: int,
    payload: ApprovalActionIn,
    user: Annotated[User, Depends(require_permission(MODULE, "approve_exception"))],
    svc: Service,
    authz: Authz,
) -> OrderDetailOut:
    try:
        return svc.approve(order_id=order_id, actor=user, scope=_scope_for(authz, user), note=payload.note)
    except Exception as exc:
        raise _map(exc)


@router.post("/{order_id}/reject", response_model=OrderDetailOut)
def reject_order(
    order_id: int,
    payload: ApprovalActionIn,
    user: Annotated[User, Depends(require_permission(MODULE, "approve_exception"))],
    svc: Service,
    authz: Authz,
) -> OrderDetailOut:
    try:
        return svc.reject(order_id=order_id, actor=user, scope=_scope_for(authz, user), note=payload.note)
    except Exception as exc:
        raise _map(exc)


# --- Cọc (P2) — quyền `record_deposit` (Kế toán) ------------------------------
@router.post("/{order_id}/deposits", response_model=OrderDetailOut)
def add_deposit(
    order_id: int,
    payload: OrderDepositIn,
    user: Annotated[User, Depends(require_permission(MODULE, "record_deposit"))],
    svc: Service,
    authz: Authz,
) -> OrderDetailOut:
    try:
        return svc.add_deposit(order_id=order_id, actor=user, scope=_scope_for(authz, user), payload=payload)
    except Exception as exc:
        raise _map(exc)


@router.put("/{order_id}/deposits/{deposit_id}", response_model=OrderDetailOut)
def update_deposit(
    order_id: int,
    deposit_id: int,
    payload: OrderDepositIn,
    user: Annotated[User, Depends(require_permission(MODULE, "record_deposit"))],
    svc: Service,
    authz: Authz,
) -> OrderDetailOut:
    try:
        return svc.update_deposit(order_id=order_id, deposit_id=deposit_id, actor=user, scope=_scope_for(authz, user), payload=payload)
    except Exception as exc:
        raise _map(exc)


@router.delete("/{order_id}/deposits/{deposit_id}", response_model=OrderDetailOut)
def delete_deposit(
    order_id: int,
    deposit_id: int,
    user: Annotated[User, Depends(require_permission(MODULE, "record_deposit"))],
    svc: Service,
    authz: Authz,
) -> OrderDetailOut:
    try:
        return svc.delete_deposit(order_id=order_id, deposit_id=deposit_id, actor=user, scope=_scope_for(authz, user))
    except Exception as exc:
        raise _map(exc)


# --- Đính kèm (chứng cứ khách đồng ý = `update`; minh chứng cọc = `record_deposit`) ---
@router.post("/{order_id}/attachments", response_model=OrderDetailOut)
async def upload_consent(
    order_id: int,
    user: Annotated[User, Depends(require_permission(MODULE, "update"))],
    svc: Service,
    authz: Authz,
    file: UploadFile = File(...),
) -> OrderDetailOut:
    data = await file.read()
    try:
        return svc.add_consent_attachment(order_id=order_id, actor=user, scope=_scope_for(authz, user),
            file_name=file.filename, content_type=file.content_type, data=data)
    except Exception as exc:
        raise _map(exc)


@router.delete("/{order_id}/attachments/{attachment_id}", response_model=OrderDetailOut)
def delete_consent(
    order_id: int,
    attachment_id: int,
    user: Annotated[User, Depends(require_permission(MODULE, "update"))],
    svc: Service,
    authz: Authz,
) -> OrderDetailOut:
    try:
        return svc.delete_consent_attachment(order_id=order_id, attachment_id=attachment_id,
            actor=user, scope=_scope_for(authz, user))
    except Exception as exc:
        raise _map(exc)


@router.post("/{order_id}/deposits/{deposit_id}/attachments", response_model=OrderDetailOut)
async def upload_deposit_proof(
    order_id: int,
    deposit_id: int,
    user: Annotated[User, Depends(require_permission(MODULE, "record_deposit"))],
    svc: Service,
    authz: Authz,
    file: UploadFile = File(...),
) -> OrderDetailOut:
    data = await file.read()
    try:
        return svc.add_deposit_attachment(order_id=order_id, deposit_id=deposit_id, actor=user,
            scope=_scope_for(authz, user), file_name=file.filename, content_type=file.content_type, data=data)
    except Exception as exc:
        raise _map(exc)


@router.delete("/{order_id}/deposits/{deposit_id}/attachments/{attachment_id}", response_model=OrderDetailOut)
def delete_deposit_proof(
    order_id: int,
    deposit_id: int,
    attachment_id: int,
    user: Annotated[User, Depends(require_permission(MODULE, "record_deposit"))],
    svc: Service,
    authz: Authz,
) -> OrderDetailOut:
    try:
        return svc.delete_deposit_attachment(order_id=order_id, deposit_id=deposit_id,
            attachment_id=attachment_id, actor=user, scope=_scope_for(authz, user))
    except Exception as exc:
        raise _map(exc)
