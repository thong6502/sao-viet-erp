"""Đơn hàng bán (Order) routes — spec-10-don-hang-ban (F1/F2 làm-ngay; F3/F8 scaffolded).

Thin HTTP shell over OrderService. Every route is guarded by
`require_permission('don_hang_ban', <action>)`; list/detail additionally narrow to the caller's
data scope (own/department/all). SEAM reads:
  - SEAM-04 (quotation_ref, Báo giá LIVE): the approved-quotation picker + create read the live
    quotations; the deposit half (Payment) is TREO → the gate shows deposit_available=false
    (never a fabricated cọc).
  - SEAM-05/06/01/02 (proof / customer paper / progress / delivery): TREO — surfaced read-only
    in F4/F6/F7 (feat-049); not wired here.

The physical layer (khổ giấy / số màu / số kẽm / imposition / PrintForm) is NEVER in any
response shape — ẩn khỏi Sale (§29 P0, §43 #1).
"""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status

from ..deps import (
    get_authorization_service,
    get_order_service,
    require_permission,
)
from ..models.order import ORDER_KINDS, ORDER_STATUSES, ORDER_TYPES, Order
from ..models.user import User
from ..schemas.order import (
    ApprovedQuotationListOut,
    ApprovedQuotationRow,
    CustomerDisplayOut,
    EnumOption,
    GateOut,
    OrderCreate,
    OrderDetailOut,
    OrderEnumsOut,
    OrderListOut,
    OrderRow,
    TransitionRequest,
)
from ..services.order_service import (
    DepositUnavailable,
    OrderConflict,
    OrderForbidden,
    OrderNotFound,
    OrderService,
    OrderValidationError,
    QuotationNotSelectable,
)
from ..services.order_state import TRANSITIONS as _TRANS
from ..services.rbac_service import AuthorizationService

router = APIRouter(prefix="/api/orders", tags=["orders"])

MODULE = "don_hang_ban"

Service = Annotated[OrderService, Depends(get_order_service)]
Authz = Annotated[AuthorizationService, Depends(get_authorization_service)]

TYPE_LABELS = {"noi_bo": "Nội bộ", "theo_yc": "Theo yêu cầu"}
KIND_LABELS = {"moi": "Đơn mới", "bo_sung": "Đơn bổ sung"}
STATUS_LABELS = {
    "draft": "Nháp",
    "ordered": "Đã chốt",
    "on_hold": "Tạm giữ",
    "change_order": "Đã đổi (re-quote)",
    "cancelled": "Đã hủy",
}


def _scope_for(authz: AuthorizationService, user: User) -> str:
    return authz.scope_for(user, MODULE) or "own"


_ALL_TRANSITIONS = list(_TRANS.keys())


def _allowed_transitions(current_status: str) -> list[str]:
    return [to for (frm, to) in _ALL_TRANSITIONS if frm == current_status]


def _detail(svc: OrderService, order: Order) -> OrderDetailOut:
    out = OrderDetailOut.model_validate(order)
    ref = svc.customer_display(order)
    out.customer = CustomerDisplayOut(**ref) if ref is not None else None
    out.gate = GateOut(**svc.gate_status(order))
    out.allowed_transitions = _allowed_transitions(order.status)
    return out


# --- enums + approved-quotation picker (F1, SEAM-04 quotation_ref) -------------

@router.get("/enums", response_model=OrderEnumsOut)
def order_enums(
    _: Annotated[User, Depends(require_permission(MODULE, "read"))],
) -> OrderEnumsOut:
    return OrderEnumsOut(
        order_types=[EnumOption(value=v, label=TYPE_LABELS.get(v, v)) for v in ORDER_TYPES],
        order_kinds=[EnumOption(value=v, label=KIND_LABELS.get(v, v)) for v in ORDER_KINDS],
        statuses=[EnumOption(value=v, label=STATUS_LABELS.get(v, v)) for v in ORDER_STATUSES],
    )


@router.get("/approved-quotations", response_model=ApprovedQuotationListOut)
def approved_quotations(
    svc: Service,
    authz: Authz,
    user: Annotated[User, Depends(require_permission(MODULE, "read"))],
) -> ApprovedQuotationListOut:
    """Báo giá đã duyệt còn hạn choosable for an order (F1). Reads the live Báo giá via
    SEAM-04 (quotation_ref). When Báo giá is not wired the port raises → empty picker with a
    clear state (the frontend shows 'phân hệ Báo giá chưa sẵn sàng')."""
    scope = _scope_for(authz, user)
    try:
        rows, names = svc.approved_quotations(scope=scope, actor=user)
    except NotImplementedError:
        # SEAM-04 (quotation_ref) not wired — no fabricated list.
        return ApprovedQuotationListOut(items=[])
    items = []
    for q in rows:
        active = next((v for v in q.versions if v.id == q.current_version_id), None)
        items.append(
            ApprovedQuotationRow(
                id=q.id,
                code=q.quote_number,
                version=active.version_number if active else 1,
                customer_id=q.customer_id,
                customer_name=names.get(q.id) or q.customer_name_snapshot,
                total=int(active.final_amount) if active else None,
                valid_until=q.valid_until,
            )
        )
    return ApprovedQuotationListOut(items=items)


# --- list (F1) -----------------------------------------------------------------

@router.get("", response_model=OrderListOut)
def list_orders(
    svc: Service,
    authz: Authz,
    user: Annotated[User, Depends(require_permission(MODULE, "read"))],
    q: str | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
    order_kind: str | None = Query(default=None),
    sort: str = Query(default="-created_at"),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=200),
) -> OrderListOut:
    scope = _scope_for(authz, user)
    rows, total, names, totals = svc.list_orders(
        scope=scope, actor=user, q=q, status=status_filter, order_kind=order_kind,
        sort=sort, page=page, size=size,
    )
    items = []
    for r in rows:
        # ③→④ gate flag: pinned from an approved quotation is the approved side; the cọc side
        # is TREO (SEAM-04 Payment) so the gate is not yet met — honest false, not a fake pass.
        gate = svc.gate_status(r)
        items.append(
            OrderRow(
                id=r.id,
                order_no=r.order_no,
                customer_id=r.customer_id,
                customer_name=names.get(r.id),
                order_type=r.order_type,
                order_kind=r.order_kind,
                status=r.status,
                total_estimate=totals.get(r.id),
                has_customer_paper=r.has_customer_paper,
                gate_ordered_ok=gate["can_confirm"],
                created_at=r.created_at,
            )
        )
    return OrderListOut(items=items, total=total, page=page, size=size)


# --- create (F1/F2) ------------------------------------------------------------

@router.post("", response_model=OrderDetailOut, status_code=status.HTTP_201_CREATED)
def create_order(
    payload: OrderCreate,
    svc: Service,
    user: Annotated[User, Depends(require_permission(MODULE, "create"))],
) -> OrderDetailOut:
    try:
        order = svc.create_order(
            quotation_id=payload.quotation_id,
            order_type=payload.order_type,
            order_kind=payload.order_kind,
            parent_order_id=payload.parent_order_id,
            has_customer_paper=payload.has_customer_paper,
            vat_pct_estimate=payload.vat_pct_estimate,
            actor=user,
        )
    except QuotationNotSelectable as e:
        # Báo giá không hợp lệ (chưa duyệt / hết hạn / không tồn tại) — chặn chọn + lý do.
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e)) from None
    except OrderValidationError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e)) from None
    return _detail(svc, order)


@router.get("/{order_id}", response_model=OrderDetailOut)
def get_order(
    order_id: int,
    svc: Service,
    authz: Authz,
    user: Annotated[User, Depends(require_permission(MODULE, "read"))],
) -> OrderDetailOut:
    scope = _scope_for(authz, user)
    try:
        order = svc.get_order(order_id=order_id, scope=scope, actor=user)
    except (OrderNotFound, OrderForbidden):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Không tìm thấy đơn hàng.") from None
    return _detail(svc, order)


# --- lifecycle transitions (F8; chốt gated F3) --------------------------------

@router.post("/{order_id}/transition", response_model=OrderDetailOut)
def transition_order(
    order_id: int,
    payload: TransitionRequest,
    svc: Service,
    authz: Authz,
    user: Annotated[User, Depends(require_permission(MODULE, "update"))],
) -> OrderDetailOut:
    scope = _scope_for(authz, user)
    try:
        order = svc.transition(
            order_id=order_id, to_status=payload.to_status, scope=scope, actor=user,
            cancel_reason=payload.cancel_reason,
        )
    except (OrderNotFound, OrderForbidden):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Không tìm thấy đơn hàng.") from None
    except OrderConflict as e:
        raise HTTPException(status.HTTP_409_CONFLICT, str(e)) from None
    except DepositUnavailable as e:
        # Chốt cần cọc, nhưng ghi cọc TREO (SEAM-04 Payment) — 409, nêu rõ chờ phân hệ.
        raise HTTPException(status.HTTP_409_CONFLICT, str(e)) from None
    except OrderValidationError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e)) from None
    return _detail(svc, order)
