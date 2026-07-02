"""Khách hàng (CRM) routes — spec-06-khach-hang.

Thin HTTP shell over CustomerService. Every route is guarded by
`require_permission('khach_hang', <action>)`; list/detail additionally narrow to the
caller's data scope (own/department/all) resolved from their role. The read-only Công
nợ card is fed by SEAM-16 — when Công nợ is not built the port raises and we return an
explicit "unavailable" card (never a fabricated 0 balance).
"""
from __future__ import annotations

import io
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status

from ..deps import (
    get_audit_repository,
    get_authorization_service,
    get_customer_analytics_service,
    get_customer_service,
    get_user_repository,
    require_permission,
)
from ..models.customer import Customer
from ..models.user import User
from ..repositories.audit_repo import AuditLogRepository
from ..repositories.user_repo import UserRepository
from ..schemas.customer import (
    CustomerAuditOut,
    CustomerAuditRowOut,
    CustomerCreate,
    CustomerCreateOut,
    CustomerDashboardOut,
    CustomerDetailOut,
    CustomerKpis,
    CustomerListOut,
    CustomerRow,
    CustomerUpdate,
    DuplicateRef,
    HeatCellOut,
    MonthPointOut,
    OrderHistoryOut,
    OrderHistoryRowOut,
    ProductSliceOut,
    QuoteHistoryOut,
    QuoteHistoryRowOut,
    ReceivableCard,
    SaleOption,
)
from ..services.customer_analytics import CustomerAnalyticsService, CustomerStat
from ..services.customer_service import (
    CustomerForbidden,
    CustomerNotFound,
    CustomerService,
    CustomerValidationError,
    ReceivableUnavailable,
)
from ..services.rbac_service import AuthorizationService

router = APIRouter(prefix="/api/customers", tags=["customers"])

MODULE = "khach_hang"

Service = Annotated[CustomerService, Depends(get_customer_service)]
Analytics = Annotated[CustomerAnalyticsService, Depends(get_customer_analytics_service)]
Authz = Annotated[AuthorizationService, Depends(get_authorization_service)]
Users = Annotated[UserRepository, Depends(get_user_repository)]
Audit = Annotated[AuditLogRepository, Depends(get_audit_repository)]


def _scope_for(authz: AuthorizationService, user: User) -> str:
    """The caller's data scope on khach_hang (own/department/all). Defaults to `own`
    if somehow missing, so a read-permitted user never sees more than their own."""
    return authz.scope_for(user, MODULE) or "own"


def _row(
    customer: Customer,
    sale_names: dict[int, str],
    stat: CustomerStat | None = None,
) -> CustomerRow:
    row = CustomerRow.model_validate(customer)
    if customer.sale_user_id is not None:
        row.sale_name = sale_names.get(customer.sale_user_id)
    # Công nợ chỉ-đọc: chưa build → None + no_ar_module=True (KHÔNG số 0 giả).
    row.receivable = None
    row.no_ar_module = True
    # Derived-from-real-orders fields (default honest zeros when no history).
    if stat is not None:
        row.tier = stat.tier
        row.revenue_12m = stat.revenue_12m
        row.orders_total = stat.orders_total
        row.last_order_at = stat.last_order_at
    return row


def _sale_names(users: UserRepository, ids: set[int]) -> dict[int, str]:
    out: dict[int, str] = {}
    for uid in ids:
        u = users.get_by_id(uid)
        if u is not None:
            out[uid] = u.name or u.username
    return out


def _sort_key(sort: str):
    """Resolve a sort key over the scoped set. Derived columns (revenue/orders/last_order)
    are sorted in-Python from the analytics roll-up; identity columns fall back to the row."""
    desc = sort.startswith("-")
    key = sort[1:] if desc else sort
    return key, desc


@router.get("", response_model=CustomerListOut)
def list_customers(
    svc: Service,
    analytics: Analytics,
    authz: Authz,
    users: Users,
    user: Annotated[User, Depends(require_permission(MODULE, "read"))],
    q: str | None = Query(default=None),
    sale: int | None = Query(default=None),
    tier: str | None = Query(default=None),
    sort: str = Query(default="code"),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=200),
) -> CustomerListOut:
    """Danh bạ + KPI header. Every derived number (tier/LTV/#đơn) và mọi KPI được tính từ
    ĐƠN HÀNG THẬT (feat CRM-360). Filter/sort/paginate over the scoped book so the header
    reflects the whole book and the tier filter/derived sort are correct."""
    scope = _scope_for(authz, user)
    book = svc.list_scoped_all(scope=scope, actor=user)
    stats = analytics.list_stats(book)

    # Text search (name / MST / phone) — mirror the repo's q semantics.
    needle = (q or "").strip().lower()
    filtered = book
    if needle:
        filtered = [
            c
            for c in filtered
            if needle in c.name.lower()
            or needle in (c.tax_code or "").lower()
            or needle in (c.phone or "").lower()
        ]
    if sale is not None:
        filtered = [c for c in filtered if c.sale_user_id == sale]
    if tier:
        filtered = [c for c in filtered if stats.per_customer[c.id].tier == tier]

    key, is_desc = _sort_key(sort or "code")
    derived = {"revenue": "revenue_12m", "orders": "orders_total"}
    if key == "last_order":
        filtered.sort(
            key=lambda c: (stats.per_customer[c.id].last_order_at is not None,
                           stats.per_customer[c.id].last_order_at or _min_date()),
            reverse=is_desc,
        )
    elif key in derived:
        attr = derived[key]
        filtered.sort(key=lambda c: getattr(stats.per_customer[c.id], attr), reverse=is_desc)
    elif key == "name":
        filtered.sort(key=lambda c: c.name.lower(), reverse=is_desc)
    elif key == "credit_limit":
        filtered.sort(key=lambda c: c.credit_limit, reverse=is_desc)
    else:  # code (default) — stable, sequential
        filtered.sort(key=lambda c: c.code, reverse=is_desc)

    total = len(filtered)
    start = (page - 1) * size
    page_rows = filtered[start : start + size]

    sale_ids = {c.sale_user_id for c in page_rows if c.sale_user_id is not None}
    names = _sale_names(users, sale_ids)
    return CustomerListOut(
        items=[_row(c, names, stats.per_customer.get(c.id)) for c in page_rows],
        total=total,
        page=page,
        size=size,
        kpis=CustomerKpis(
            total_customers=stats.total_customers,
            loyal_count=stats.loyal_count,
            new_this_month=stats.new_this_month,
            avg_order_value=stats.avg_order_value,
        ),
    )


def _min_date():
    from datetime import date

    return date.min


@router.get("/sales", response_model=list[SaleOption])
def list_sale_options(
    authz: Authz,
    users: Users,
    user: Annotated[User, Depends(require_permission(MODULE, "read"))],
) -> list[SaleOption]:
    """Sales selectable as the "phụ trách" owner / list filter, scoped to what the
    caller may see (own → just themselves; department → the KD dept; all → everyone)."""
    scope = _scope_for(authz, user)
    if scope == "all":
        candidates = users.list_all()
    elif scope == "department" and user.department_id is not None:
        candidates = users.list_by_department(user.department_id)
    else:
        candidates = [user]
    return [SaleOption(id=u.id, name=u.name or u.username) for u in candidates]


@router.post("", response_model=CustomerCreateOut, status_code=status.HTTP_201_CREATED)
def create_customer(
    payload: CustomerCreate,
    svc: Service,
    users: Users,
    user: Annotated[User, Depends(require_permission(MODULE, "create"))],
) -> CustomerCreateOut:
    try:
        customer, duplicate = svc.create_customer(
            name=payload.name,
            tax_code=payload.tax_code,
            phone=payload.phone,
            email=payload.email,
            address=payload.address,
            contact_name=payload.contact_name,
            credit_limit=payload.credit_limit,
            sale_user_id=payload.sale_user_id,
            actor=user,
        )
    except CustomerValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e)
        ) from None
    names = _sale_names(
        users, {customer.sale_user_id} if customer.sale_user_id else set()
    )
    return CustomerCreateOut(
        customer=_row(customer, names),
        duplicate=_dup_ref(duplicate),
    )


@router.get("/{customer_id}", response_model=CustomerDetailOut)
def get_customer(
    customer_id: int,
    svc: Service,
    analytics: Analytics,
    authz: Authz,
    users: Users,
    user: Annotated[User, Depends(require_permission(MODULE, "read"))],
) -> CustomerDetailOut:
    scope = _scope_for(authz, user)
    customer = _load_scoped(svc, customer_id, scope, user)
    names = _sale_names(
        users, {customer.sale_user_id} if customer.sale_user_id else set()
    )
    stat = analytics.list_stats([customer]).per_customer.get(customer.id)
    return CustomerDetailOut(
        customer=_row(customer, names, stat),
        receivable=_receivable_card(svc, customer),
    )


# --- CRM-360 Object-page: Dashboard + history + Excel (computed from real data) ---


@router.get("/{customer_id}/dashboard", response_model=CustomerDashboardOut)
def customer_dashboard(
    customer_id: int,
    svc: Service,
    analytics: Analytics,
    authz: Authz,
    user: Annotated[User, Depends(require_permission(MODULE, "read"))],
) -> CustomerDashboardOut:
    """The Object-page Dashboard: doanh số 12T (bar), số đơn/TB/đơn, cơ cấu SP (donut), tần
    suất đặt (heatmap) — ALL from real orders/quotations. No history → has_data=False so the
    UI shows an honest empty state (không bịa số)."""
    scope = _scope_for(authz, user)
    customer = _load_scoped(svc, customer_id, scope, user)
    d = analytics.dashboard(customer)
    return CustomerDashboardOut(
        revenue_12m=d.revenue_12m,
        orders_12m=d.orders_12m,
        avg_order_value=d.avg_order_value,
        orders_total=d.orders_total,
        quotes_total=d.quotes_total,
        win_rate_pct=d.win_rate_pct,
        first_order_at=d.first_order_at,
        last_order_at=d.last_order_at,
        tier=d.tier,
        months=[MonthPointOut(**vars(m)) for m in d.months],
        product_mix=[ProductSliceOut(**vars(s)) for s in d.product_mix],
        heatmap=[HeatCellOut(**vars(h)) for h in d.heatmap],
        has_data=d.has_data,
        receivable=_receivable_card(svc, customer),
    )


@router.get("/{customer_id}/orders", response_model=OrderHistoryOut)
def customer_order_history(
    customer_id: int,
    svc: Service,
    analytics: Analytics,
    authz: Authz,
    user: Annotated[User, Depends(require_permission(MODULE, "read"))],
) -> OrderHistoryOut:
    """Lịch sử mua hàng — the customer's REAL orders (wired from Đơn hàng bán)."""
    scope = _scope_for(authz, user)
    _load_scoped(svc, customer_id, scope, user)  # scope guard (404 if out of scope)
    rows = analytics.order_history(customer_id)
    return OrderHistoryOut(items=[OrderHistoryRowOut(**vars(r)) for r in rows])


@router.get("/{customer_id}/quotations", response_model=QuoteHistoryOut)
def customer_quote_history(
    customer_id: int,
    svc: Service,
    analytics: Analytics,
    authz: Authz,
    user: Annotated[User, Depends(require_permission(MODULE, "read"))],
) -> QuoteHistoryOut:
    """Lịch sử báo giá — the customer's REAL quotations (wired from Báo giá)."""
    scope = _scope_for(authz, user)
    _load_scoped(svc, customer_id, scope, user)
    rows = analytics.quote_history(customer_id)
    return QuoteHistoryOut(items=[QuoteHistoryRowOut(**vars(r)) for r in rows])


_ORDER_STATUS_LABELS = {
    "draft": "Nháp",
    "ordered": "Đã chốt",
    "on_hold": "Tạm giữ",
    "change_order": "Đã đổi",
    "cancelled": "Đã hủy",
}
_ORDER_KIND_LABELS = {"moi": "Đơn mới", "bo_sung": "Đơn bổ sung"}
_QUOTE_STATUS_LABELS = {
    "draft": "Nháp",
    "sent": "Đã gửi",
    "approved": "Đã duyệt",
    "rejected": "Từ chối",
    "expired": "Hết hạn",
    "cancelled": "Đã hủy",
    "on_hold": "Tạm giữ",
    "change_order": "Re-quote",
}
_PROFILE_ACTION_LABELS = {
    "create_customer": "Tạo hồ sơ khách hàng",
    "update_customer": "Cập nhật hồ sơ",
}


@router.get("/{customer_id}/audit", response_model=CustomerAuditOut)
def customer_audit(
    customer_id: int,
    svc: Service,
    analytics: Analytics,
    authz: Authz,
    users: Users,
    audit: Audit,
    user: Annotated[User, Depends(require_permission(MODULE, "read"))],
) -> CustomerAuditOut:
    """Nhật ký khách hàng — a single, time-ordered timeline that merges profile edits
    (from the audit log) with REAL document events (đơn hàng / báo giá). Every row is an
    actual event; nothing is fabricated. Document rows carry ref_type/ref_id so the UI can
    drill through to the source document."""
    scope = _scope_for(authz, user)
    _load_scoped(svc, customer_id, scope, user)  # scope guard (404 if out of scope)

    items: list[CustomerAuditRowOut] = []

    # 1) Profile edits from the audit log (target == customer:<id>).
    for a in audit.list_by_target(f"customer:{customer_id}"):
        actor = users.get_by_id(a.actor_user_id) if a.actor_user_id is not None else None
        items.append(
            CustomerAuditRowOut(
                at=a.created_at,
                kind="profile",
                action=a.action,
                title=_PROFILE_ACTION_LABELS.get(a.action, a.action),
                detail=a.detail,
                actor_name=(actor.name or actor.username) if actor else None,
            )
        )

    # 2) Real order events.
    for o in analytics.order_history(customer_id):
        items.append(
            CustomerAuditRowOut(
                at=o.created_at,
                kind="order",
                action="order_placed",
                title=f"Đơn hàng {o.order_no}",
                detail=(
                    f"{_ORDER_KIND_LABELS.get(o.order_kind, o.order_kind)} · "
                    f"{_ORDER_STATUS_LABELS.get(o.status, o.status)}"
                    + (f" · {o.summary}" if o.summary and o.summary != '—' else "")
                ),
                ref_type="order",
                ref_id=o.id,
            )
        )

    # 3) Real quotation events.
    for qh in analytics.quote_history(customer_id):
        items.append(
            CustomerAuditRowOut(
                at=qh.created_at,
                kind="quote",
                action="quote_issued",
                title=f"Báo giá {qh.code} v{qh.version}",
                detail=_QUOTE_STATUS_LABELS.get(qh.status, qh.status),
                ref_type="quotation",
                ref_id=qh.id,
            )
        )

    items.sort(key=lambda r: r.at, reverse=True)
    return CustomerAuditOut(items=items)


@router.get("/{customer_id}/orders.csv")
def customer_order_history_csv(
    customer_id: int,
    svc: Service,
    analytics: Analytics,
    authz: Authz,
    user: Annotated[User, Depends(require_permission(MODULE, "read"))],
) -> Response:
    """Xuất Excel (CSV UTF-8 BOM mở được bằng Excel) — lịch sử mua hàng THẬT của khách."""
    scope = _scope_for(authz, user)
    customer = _load_scoped(svc, customer_id, scope, user)
    rows = analytics.order_history(customer_id)

    import csv

    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["Mã đơn", "Ngày", "Loại đơn", "Sản phẩm", "Trạng thái", "Thành tiền (VND)"])
    for r in rows:
        w.writerow(
            [
                r.order_no,
                r.created_at.date().isoformat(),
                _ORDER_KIND_LABELS.get(r.order_kind, r.order_kind),
                r.summary,
                _ORDER_STATUS_LABELS.get(r.status, r.status),
                r.total if r.total is not None else "",
            ]
        )
    # UTF-8 BOM so Excel opens Vietnamese correctly.
    data = b"\xef\xbb\xbf" + buf.getvalue().encode("utf-8")
    filename = f"lich-su-mua-hang-{customer.code}.csv"
    return Response(
        content=data,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.put("/{customer_id}", response_model=CustomerCreateOut)
def update_customer(
    customer_id: int,
    payload: CustomerUpdate,
    svc: Service,
    authz: Authz,
    users: Users,
    user: Annotated[User, Depends(require_permission(MODULE, "update"))],
) -> CustomerCreateOut:
    scope = _scope_for(authz, user)
    try:
        customer, duplicate = svc.update_customer(
            customer_id=customer_id,
            scope=scope,
            actor=user,
            name=payload.name,
            tax_code=payload.tax_code,
            phone=payload.phone,
            email=payload.email,
            address=payload.address,
            contact_name=payload.contact_name,
            credit_limit=payload.credit_limit,
            sale_user_id=payload.sale_user_id,
            status=payload.status,
        )
    except CustomerValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e)
        ) from None
    except (CustomerNotFound, CustomerForbidden):
        # Do not leak existence of out-of-scope customers.
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy khách hàng."
        ) from None
    names = _sale_names(
        users, {customer.sale_user_id} if customer.sale_user_id else set()
    )
    return CustomerCreateOut(
        customer=_row(customer, names), duplicate=_dup_ref(duplicate)
    )


# --- helpers ---------------------------------------------------------------


def _load_scoped(
    svc: CustomerService, customer_id: int, scope: str, user: User
) -> Customer:
    try:
        return svc.get_customer(customer_id=customer_id, scope=scope, actor=user)
    except (CustomerNotFound, CustomerForbidden):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy khách hàng."
        ) from None


def _dup_ref(duplicate: Customer | None) -> DuplicateRef | None:
    if duplicate is None:
        return None
    return DuplicateRef(id=duplicate.id, code=duplicate.code, name=duplicate.name)


def _receivable_card(svc: CustomerService, customer: Customer) -> ReceivableCard:
    """Build the read-only Công nợ card. On SEAM-16 (Công nợ chưa build) return an
    explicit unavailable card — NEVER a fabricated 0 (§34 L885 / spec KH-04)."""
    try:
        balance = svc.receivable_balance(customer.id)
    except ReceivableUnavailable:
        return ReceivableCard(
            available=False,
            credit_limit=customer.credit_limit,
            message="Chưa có phân hệ Công nợ",
        )
    limit = customer.credit_limit
    usage_pct = int(round(balance / limit * 100)) if limit > 0 else None
    return ReceivableCard(
        available=True,
        credit_limit=limit,
        balance=balance,
        usage_pct=usage_pct,
        # Vượt hạn mức = CẢNH BÁO, không chặn (§34 L885).
        over_limit=(limit > 0 and balance > limit),
    )
