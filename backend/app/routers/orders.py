"""Đơn hàng bán (Order) routes — redesign-don-hang-ban.md (P1 khung đơn).

P1: list / get / enums / activity / create (TỪ BÁO GIÁ) / update (khi nháp).
Cọc/chốt/hủy = P2–P5.

ĐÃ GỠ: nhánh tạo đơn nhập tay + 3 route duyệt đơn đặc thù (submit-approval / approve / reject).
HỦY ĐƠN ĐÃ CHỐT: từ 24/08/2026 MẶC ĐỊNH BẬT cho vai có `update` đơn — công tắc chi tiết
`approve_exception` (từng gác riêng việc này) đã gỡ khỏi ma trận phân quyền; cột DB giữ nguyên.
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
    OrderActivityOut,
    OrderCancelIn,
    OrderCreate,
    OrderDepositReceiptIn,
    OrderDetailOut,
    OrderEnumsOut,
    OrderListOut,
    OrderStatsOut,
    OrderProductionHintIn,
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
from ..realtime import hub

router = APIRouter(prefix="/api/orders", tags=["orders"])


def _order_changed(order_no: str | None = None) -> None:
    """Tín hiệu 'danh sách chờ (duyệt/ghi cọc/chốt) đã đổi' — mọi vai tự refetch notify-summary
    (badge nhảy + toast khi số 'chờ TÔI' tăng). Bám đúng logic SSE báo giá (kênh hub chung)."""
    hub.broadcast({"type": "order_pending_changed", "code": order_no})

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
    view_scope: str | None = Query(default=None),
    sort: str = Query(default="-created_at"),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=200),
) -> OrderListOut:
    scope = _effective_scope(_scope_for(authz, user), view_scope)
    return svc.list(
        actor=user, scope=scope, q=q, status=status_filter, order_kind=order_kind,
        sort=sort, page=page, size=size,
    )


@router.get("/stats", response_model=OrderStatsOut)
def get_stats(
    user: Annotated[User, Depends(require_permission(MODULE, "read"))],
    svc: Service,
    authz: Authz,
    view_scope: str | None = Query(default=None),
) -> OrderStatsOut:
    return svc.stats(actor=user, scope=_effective_scope(_scope_for(authz, user), view_scope))


@router.get("/notify-summary")
def notify_summary(
    user: Annotated[User, Depends(require_permission(MODULE, "read"))],
    svc: Service,
    authz: Authz,
) -> dict:
    """Số nuôi badge/toast real-time Đơn hàng bán — 'việc chờ TÔI xử lý' theo vai (SSE snapshot lúc
    connect + REST fallback khi có event). Kế toán=chờ ghi cọc; Sale=sẵn sàng chốt."""
    return svc.notify_summary(
        actor=user, scope=_scope_for(authz, user),
        can_record_deposit=authz.can(user, MODULE, "record_deposit"),
        can_manage_status=authz.can(user, MODULE, "manage_status"),
    )


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
        d = svc.create(actor=user, scope=_scope_for(authz, user), payload=payload)
    except Exception as exc:
        raise _map(exc)
    _order_changed(d.order_no)   # đơn nháp mới → Kế toán thấy 'chờ ghi cọc'
    return d


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


# --- Sale đổi hint sản xuất (gấp / lưu ý SX) SAU khi đã chốt → realtime bàn Kế hoạch ---
@router.post("/{order_id}/production-hint", response_model=OrderDetailOut)
def update_production_hint(
    order_id: int,
    payload: OrderProductionHintIn,
    user: Annotated[User, Depends(require_permission(MODULE, "update"))],
    svc: Service,
    authz: Authz,
) -> OrderDetailOut:
    try:
        d = svc.update_production_hint(
            order_id=order_id, actor=user, scope=_scope_for(authz, user), payload=payload,
        )
    except Exception as exc:
        raise _map(exc)
    # Bàn Kế hoạch SX 'ting': đơn chuyển gấp / cập nhật lưu ý (badge nhảy; nội dung note FE refetch).
    hub.broadcast(
        {"type": "order_sx_hint_changed", "code": d.order_no, "order_id": order_id, "is_rush": d.is_rush}
    )
    return d


# --- Chuyển đơn (đã chốt) xuống Sản xuất → vào hàng chờ Kế hoạch (handoff) -----
@router.post("/{order_id}/release-production", response_model=OrderDetailOut)
def release_production(
    order_id: int,
    user: Annotated[User, Depends(require_permission(MODULE, "update"))],
    svc: Service,
    authz: Authz,
) -> OrderDetailOut:
    try:
        d = svc.release_production(order_id=order_id, actor=user, scope=_scope_for(authz, user))
    except Exception as exc:
        raise _map(exc)
    # Đơn 'bắn xuống' hàng chờ Kế hoạch (badge nhảy, không refresh).
    hub.broadcast({"type": "order_ordered", "code": d.order_no, "order_id": order_id})
    return d


# --- Hủy đơn (P5) — nháp hay đã chốt đều cần `update` (hủy đã chốt mặc định bật) ----
@router.post("/{order_id}/cancel", response_model=OrderDetailOut)
def cancel_order(
    order_id: int,
    payload: OrderCancelIn,
    user: Annotated[User, Depends(require_permission(MODULE, "update"))],
    svc: Service,
    authz: Authz,
) -> OrderDetailOut:
    # Hủy đơn đã chốt MẶC ĐỊNH BẬT cho vai có `update` đơn (gỡ quyền `approve_exception` 24/08/2026).
    elevated = True
    try:
        d = svc.cancel(
            order_id=order_id, actor=user, scope=_scope_for(authz, user),
            reason=payload.reason, fault=payload.fault, can_cancel_ordered=elevated,
        )
    except Exception as exc:
        raise _map(exc)
    _order_changed(d.order_no)   # hủy nháp → rời tập chờ, badge 'chờ xử lý' các vai tụt
    return d


# --- Chốt đơn (P4) — quyền `manage_status` ------------------------------------
@router.post("/{order_id}/confirm", response_model=OrderDetailOut)
def confirm_order(
    order_id: int,
    user: Annotated[User, Depends(require_permission(MODULE, "manage_status"))],
    svc: Service,
    authz: Authz,
) -> OrderDetailOut:
    try:
        d = svc.confirm(order_id=order_id, actor=user, scope=_scope_for(authz, user))
    except Exception as exc:
        raise _map(exc)
    _order_changed(d.order_no)   # chốt → rời tập nháp, badge 'sẵn sàng chốt' của Sale tụt
    # Chốt = chốt THÔNG TIN → báo KẾ TOÁN "đơn chờ ghi cọc" (popup module Phiếu thu). KHÔNG dùng
    # order_ordered ở đây (đó là tín hiệu 'đã Chuyển SX' cho bàn Kế hoạch — chốt CHƯA vào hàng chờ).
    hub.broadcast(
        {"type": "order_deposit_needed", "code": d.order_no, "order_id": order_id, "amount": d.deposit_required}
    )
    return d


# --- Gia hạn báo giá nguồn (Việc 4) — quyền `update` (Sale + TP/GĐ) -----------
@router.post("/{order_id}/extend-quote", response_model=OrderDetailOut)
def extend_quote(
    order_id: int,
    user: Annotated[User, Depends(require_permission(MODULE, "update"))],
    svc: Service,
    authz: Authz,
) -> OrderDetailOut:
    """Gỡ blocker 'báo giá hết hạn' ở cổng chốt: gia hạn báo giá nguồn +30 ngày ngay từ đơn.
    Không broadcast — badge notify-summary không phụ thuộc hạn báo giá; actor nhận detail mới
    (blocker biến mất) ngay trong response."""
    try:
        return svc.extend_source_quote(order_id=order_id, actor=user, scope=_scope_for(authz, user))
    except Exception as exc:
        raise _map(exc)


# --- Cọc (V5) — Kế toán LẬP PHIẾU THU CỌC THẬT, quyền `record_deposit` --------
@router.post("/{order_id}/deposit-receipts", response_model=OrderDetailOut)
def add_deposit_receipt(
    order_id: int,
    payload: OrderDepositReceiptIn,
    user: Annotated[User, Depends(require_permission(MODULE, "record_deposit"))],
    svc: Service,
    authz: Authz,
) -> OrderDetailOut:
    """Kế toán bấm trên drawer đơn → tạo PaymentReceipt(nguồn đơn, received) gắn order_id. Cổng đủ
    cọc = Σ phiếu thu received ≥ deposit_required."""
    try:
        d = svc.add_deposit_receipt(order_id=order_id, actor=user, scope=_scope_for(authz, user), payload=payload)
    except Exception as exc:
        raise _map(exc)
    if d.deposit_ok and d.sale_user_id:   # Kế toán thu ĐỦ cọc → báo Sale 'chốt được rồi' (Việc 3)
        hub.publish(d.sale_user_id, {"type": "order_deposit_ok", "code": d.order_no})
    _order_changed(d.order_no)
    return d


# --- Đính kèm chứng cứ khách đồng ý (`update`) — minh chứng đã thu cọc nằm ở màn Phiếu thu Kế toán ---
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
