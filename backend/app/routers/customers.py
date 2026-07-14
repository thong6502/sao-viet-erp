"""Khách hàng (CRM) routes — spec-06-khach-hang.

Thin HTTP shell over CustomerService. Every route is guarded by
`require_permission('khach_hang', <action>)`; list/detail additionally narrow to the
caller's data scope (own/department/all) resolved from their role. The read-only Công
nợ card is fed by SEAM-16 — when Công nợ is not built the port raises and we return an
explicit "unavailable" card (never a fabricated 0 balance).
"""
from __future__ import annotations

import csv
import io
import secrets
from pathlib import Path
from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    Response,
    UploadFile,
    status,
)

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
    AddressIn,
    AddressOut,
    AddressesOut,
    CareEventIn,
    CareEventOut,
    CareEventsOut,
    CareTaskIn,
    CareTaskOut,
    CareTaskStatusIn,
    CareTasksOut,
    ContactIn,
    ContactOut,
    ContactsOut,
    FollowupRow,
    FollowupsOut,
    CustomerAttachmentOut,
    CustomerAttachmentsOut,
    CustomerAuditOut,
    CustomerAuditRowOut,
    CustomerCreate,
    CustomerCreateOut,
    CustomerDashboardOut,
    CustomerDetailOut,
    CustomerFinancialIn,
    CustomerKpis,
    CustomerListOut,
    CustomerReassignIn,
    CustomerReassignOut,
    CustomerRow,
    CustomerUpdate,
    DuplicateRef,
    DuplicateWarn,
    HeatCellOut,
    ImportResultOut,
    ImportRowResult,
    MonthPointOut,
    OrderHistoryOut,
    OrderHistoryRowOut,
    ProductSliceOut,
    QuoteHistoryOut,
    QuoteHistoryRowOut,
    ReceivableCard,
    SaleOption,
    TagIn,
    TagOut,
    TagsOut,
)
from ..services.customer_analytics import CustomerAnalyticsService, CustomerStat
from ..services.customer_service import (
    CustomerForbidden,
    CustomerNotFound,
    CustomerService,
    CustomerValidationError,
    ReassignForbidden,
    ReceivableUnavailable,
)
from ..services.rbac_service import AuthorizationService

router = APIRouter(prefix="/api/customers", tags=["customers"])

MODULE = "khach_hang"

# Tài liệu KH nằm dưới <backend>/static/crm, serve read-only tại /static (mirror hr).
_STATIC_DIR = Path(__file__).resolve().parents[2] / "static"

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
    *,
    tags: list[str] | None = None,
) -> CustomerRow:
    # customer_kind + rào chiết khấu/biên + điều khoản tự nạp từ ORM (from_attributes).
    # Redesign spec-06 v2: mọi số tài chính AI CŨNG XEM (không ẩn); bỏ tier.
    row = CustomerRow.model_validate(customer)
    row.tags = tags or []
    if customer.sale_user_id is not None:
        row.sale_name = sale_names.get(customer.sale_user_id)
    # Công nợ chỉ-đọc: chưa build → None + no_ar_module=True (KHÔNG số 0 giả).
    row.receivable = None
    row.no_ar_module = True
    # Derived-from-real-orders fields (default honest zeros when no history).
    if stat is not None:
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
    followup: bool = Query(default=False),
    tag: str | None = Query(default=None),
    sort: str = Query(default="code"),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=200),
) -> CustomerListOut:
    """Danh bạ + KPI header. Số dẫn xuất (doanh số/#đơn) + KPI tính từ ĐƠN HÀNG THẬT.
    Redesign spec-06 v2: bỏ lọc theo tier/trạng thái; lọc theo THẺ gán tay + "Cần theo dõi"."""
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
    if followup:  # tab "Cần theo dõi" — việc chăm sóc đến/quá hạn (số thật, care-task)
        due_followups = svc.list_due_followups(scope=scope, actor=user)
        followup_customer_ids = {c.id for _, c, _, _ in due_followups}
        filtered = [c for c in filtered if c.id in followup_customer_ids]
    if tag and tag.strip():
        # Lọc theo nhãn thủ công (#7) — case-insensitive.
        tagged_ids = svc.customers.ids_with_label(tag)
        filtered = [c for c in filtered if c.id in tagged_ids]

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
    tag_map = svc.customers.tags_for([c.id for c in page_rows])
    return CustomerListOut(
        items=[
            _row(c, names, stats.per_customer.get(c.id), tags=tag_map.get(c.id))
            for c in page_rows
        ],
        total=total,
        page=page,
        size=size,
        kpis=CustomerKpis(
            total_customers=stats.total_customers,
            new_this_month=stats.new_this_month,
            avg_order_value=stats.avg_order_value,
            total_revenue=stats.total_revenue,
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


@router.post("/reassign", response_model=CustomerReassignOut)
def reassign_customers(
    payload: CustomerReassignIn,
    svc: Service,
    authz: Authz,
    users: Users,
    user: Annotated[User, Depends(require_permission(MODULE, "reassign"))],
) -> CustomerReassignOut:
    """Điều chuyển toàn bộ khách của một Sale sang Sale khác. Dành cho trưởng phòng KD
    (scope `department`) hoặc quản lý (scope `all`); Sale thường (scope `own`) bị 403.
    Ở scope `department`, cả Sale nguồn và đích phải cùng phòng với người thực hiện."""
    scope = _scope_for(authz, user)
    if scope == "own":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Bạn không có quyền điều chuyển khách hàng.",
        )
    to_u = users.get_by_id(payload.to_sale_user_id)
    if to_u is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy nhân viên đích."
        )
    # Ở scope `department`, nhân viên đích phải cùng phòng với người thực hiện.
    if scope == "department" and (
        user.department_id is None or to_u.department_id != user.department_id
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Nhân viên đích phải thuộc phòng của bạn.",
        )

    try:
        if payload.customer_ids:
            moved, skipped = svc.reassign_selected(
                customer_ids=payload.customer_ids,
                to_sale_user_id=payload.to_sale_user_id,
                scope=scope,
                actor=user,
            )
            return CustomerReassignOut(moved=moved, skipped=skipped)
        if payload.from_sale_user_id is not None:
            from_u = users.get_by_id(payload.from_sale_user_id)
            if from_u is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Không tìm thấy nhân viên nguồn.",
                )
            if scope == "department" and from_u.department_id != user.department_id:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Nhân viên nguồn phải thuộc phòng của bạn.",
                )
            moved = svc.reassign_customers(
                from_sale_user_id=payload.from_sale_user_id,
                to_sale_user_id=payload.to_sale_user_id,
                scope=scope,
                actor=user,
            )
            return CustomerReassignOut(moved=moved)
    except CustomerValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e)
        ) from None
    except CustomerForbidden as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e)) from None

    raise HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail="Cần chọn khách hàng hoặc nhân viên nguồn để điều chuyển.",
    )


# --- check trùng tức thời (#8: cảnh báo ngay trên form, trước khi chào hàng) --


@router.get("/check-duplicate", response_model=list[DuplicateWarn])
def check_duplicate(
    svc: Service,
    user: Annotated[User, Depends(require_permission(MODULE, "read"))],
    tax_code: str | None = Query(default=None),
    name: str | None = Query(default=None),
    email: str | None = Query(default=None),
    exclude_id: int | None = Query(default=None),
) -> list[DuplicateWarn]:
    """Soft check theo MST + tên cty + email (#15). Cảnh báo, KHÔNG chặn — form gọi
    khi người dùng rời ô nhập để hiện link tới khách đã có."""
    return _dup_warns(
        svc.customers.find_duplicates(
            tax_code=(tax_code or "").strip() or None,
            name=name,
            email=email,
            exclude_id=exclude_id,
        )
    )


# --- nhãn thủ công (#7: sales gán tay) -------------------------------------------


@router.get("/tags", response_model=list[str])
def list_tag_labels(
    svc: Service,
    authz: Authz,
    user: Annotated[User, Depends(require_permission(MODULE, "read"))],
) -> list[str]:
    """Mọi nhãn đã dùng trên các khách trong scope — gợi ý khi gõ + option lọc."""
    return svc.customers.distinct_labels(scope=_scope_for(authz, user), actor=user)


@router.get("/{customer_id}/tags", response_model=TagsOut)
def list_customer_tags(
    customer_id: int,
    svc: Service,
    authz: Authz,
    user: Annotated[User, Depends(require_permission(MODULE, "read"))],
) -> TagsOut:
    try:
        items = svc.list_tags(
            customer_id=customer_id, scope=_scope_for(authz, user), actor=user
        )
    except (CustomerNotFound, CustomerForbidden):
        raise _not_found() from None
    return TagsOut(items=[TagOut.model_validate(t) for t in items])


@router.post("/{customer_id}/tags", response_model=TagOut, status_code=201)
def add_customer_tag(
    customer_id: int,
    payload: TagIn,
    svc: Service,
    authz: Authz,
    user: Annotated[User, Depends(require_permission(MODULE, "update"))],
) -> TagOut:
    try:
        tag = svc.add_tag(
            customer_id=customer_id, scope=_scope_for(authz, user), actor=user,
            label=payload.label,
        )
    except CustomerValidationError as e:
        raise HTTPException(status_code=422, detail=str(e)) from None
    except (CustomerNotFound, CustomerForbidden):
        raise _not_found() from None
    return TagOut.model_validate(tag)


@router.delete("/{customer_id}/tags/{tag_id}", status_code=204)
def delete_customer_tag(
    customer_id: int,
    tag_id: int,
    svc: Service,
    authz: Authz,
    user: Annotated[User, Depends(require_permission(MODULE, "update"))],
):
    try:
        svc.remove_tag(
            customer_id=customer_id, tag_id=tag_id,
            scope=_scope_for(authz, user), actor=user,
        )
    except (CustomerNotFound, CustomerForbidden):
        raise _not_found() from None


# --- panel "Cần chăm sóc" (#28: việc đến hạn / quá hạn, nhắc lần 1-2-3) --------


@router.get("/care-followups", response_model=FollowupsOut)
def care_followups(
    svc: Service,
    authz: Authz,
    users: Users,
    user: Annotated[User, Depends(require_permission(MODULE, "read"))],
) -> FollowupsOut:
    """Việc chăm sóc đang mở đã đến hạn (tính đến hết hôm nay) trên các khách trong scope
    của người gọi — mức nhắc 1/2/3 tính từ số ngày quá hạn, không bịa."""
    scope = _scope_for(authz, user)
    rows = svc.list_due_followups(scope=scope, actor=user)
    names = _sale_names(
        users, {t.assignee_user_id for t, _, _, _ in rows if t.assignee_user_id}
    )
    return FollowupsOut(
        items=[
            FollowupRow(
                id=t.id,
                customer_id=c.id,
                customer_code=c.code,
                customer_name=c.name,
                note=t.note,
                due_date=t.due_date,
                remind_level=level,
                overdue_days=overdue,
                assignee_name=names.get(t.assignee_user_id) if t.assignee_user_id else None,
            )
            for t, c, level, overdue in rows
        ]
    )


# --- import / export danh bạ (#23) -------------------------------------------

_KIND_LABELS = {"ca_nhan": "Cá nhân", "cong_ty": "Công ty"}
# Redesign spec-06 v2: import chỉ nạp thông tin ĐỊNH DANH (bỏ Hạn mức/Trạng thái, thêm Loại).
_IMPORT_HEADERS = [
    "Tên khách hàng", "Loại", "MST", "Điện thoại", "Email", "Địa chỉ", "Người liên hệ",
]


def _csv_response(rows: list[list], filename: str) -> Response:
    buf = io.StringIO()
    w = csv.writer(buf)
    for r in rows:
        w.writerow(r)
    # UTF-8 BOM so Excel opens Vietnamese correctly.
    data = b"\xef\xbb\xbf" + buf.getvalue().encode("utf-8")
    return Response(
        content=data,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/export.csv")
def export_customers_csv(
    svc: Service,
    authz: Authz,
    users: Users,
    user: Annotated[User, Depends(require_permission(MODULE, "export"))],
) -> Response:
    """Xuất toàn bộ danh bạ trong scope của người gọi (CSV UTF-8 BOM mở bằng Excel).
    Redesign spec-06 v2: định danh + chính sách tài chính (ai cũng xem); bỏ Trạng thái + CK cũ."""
    scope = _scope_for(authz, user)
    book = svc.list_scoped_all(scope=scope, actor=user)
    book.sort(key=lambda c: c.code)
    names = _sale_names(users, {c.sale_user_id for c in book if c.sale_user_id})

    header = [
        "Mã KH", *_IMPORT_HEADERS, "NV phụ trách", "Hạn mức (VND)", "Số ngày công nợ",
        "CK tối thiểu (%)", "CK tối đa (%)", "Biên tối thiểu (%)", "Biên tối đa (%)",
    ]
    rows: list[list] = [header]
    for c in book:
        rows.append([
            c.code, c.name, _KIND_LABELS.get(c.customer_kind, ""), c.tax_code or "",
            c.phone or "", c.email or "", c.address or "", c.contact_name or "",
            names.get(c.sale_user_id, "") if c.sale_user_id else "",
            c.credit_limit,
            c.payment_term_days if c.payment_term_days is not None else "",
            c.discount_min_pct if c.discount_min_pct is not None else "",
            c.discount_max_pct if c.discount_max_pct is not None else "",
            c.margin_min_pct if c.margin_min_pct is not None else "",
            c.margin_max_pct if c.margin_max_pct is not None else "",
        ])
    return _csv_response(rows, "danh-ba-khach-hang.csv")


@router.get("/import-template.csv")
def import_template_csv(
    user: Annotated[User, Depends(require_permission(MODULE, "create"))],
) -> Response:
    """File mẫu import (header tiếng Việt + 1 dòng ví dụ). Chỉ thông tin định danh."""
    return _csv_response(
        [
            _IMPORT_HEADERS,
            ["Công ty TNHH ABC", "Công ty", "0101234567", "0912345678", "lienhe@abc.vn",
             "Số 1 Phố X, Hà Nội", "Chị Lan"],
        ],
        "mau-import-khach-hang.csv",
    )


@router.post("/import", response_model=ImportResultOut)
def import_customers_csv(
    svc: Service,
    user: Annotated[User, Depends(require_permission(MODULE, "create"))],
    file: UploadFile = File(...),
    dry_run: bool = Form(default=True),
) -> ImportResultOut:
    """Import danh bạ từ CSV (#23 — Excel Save-As CSV). `dry_run=true` (mặc định) chỉ
    KIỂM TRA và trả kết quả từng dòng để xem trước; gửi lại với dry_run=false mới ghi.
    Trùng MST/tên/email = cảnh báo mềm, vẫn tạo (§34) — người dùng thấy trước ở preview."""
    raw = file.file.read()
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="File phải là CSV mã hóa UTF-8 (Excel: Save As → CSV UTF-8).",
        ) from None
    reader = csv.reader(io.StringIO(text))
    lines = [r for r in reader if any((cell or "").strip() for cell in r)]
    if not lines:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="File rỗng."
        )
    header = [h.strip().lower() for h in lines[0]]
    col_map: dict[int, str] = {}
    for idx, h in enumerate(header):
        key = CustomerService.IMPORT_COLUMNS.get(h)
        if key:
            col_map[idx] = key
    if "name" not in col_map.values():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail='Thiếu cột "Tên khách hàng" — tải file mẫu để lấy đúng header.',
        )
    rows = [
        {key: (line[idx].strip() if idx < len(line) else "") for idx, key in col_map.items()}
        for line in lines[1:]
    ]
    if not rows:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="File chỉ có header, không có dòng dữ liệu.",
        )

    results = svc.import_rows(rows=rows, actor=user, dry_run=dry_run)
    out_rows = [
        ImportRowResult(
            row=no, status=st, message=msg,
            code=c.code if c else None, name=c.name if c else (rows[no - 1].get("name") or None),
        )
        for no, st, msg, c in results
    ]
    return ImportResultOut(
        dry_run=dry_run,
        total=len(out_rows),
        created=sum(1 for r in out_rows if r.status in ("created", "warning") and not dry_run),
        warnings=sum(1 for r in out_rows if r.status == "warning"),
        errors=sum(1 for r in out_rows if r.status == "error"),
        rows=out_rows,
    )


@router.post("", response_model=CustomerCreateOut, status_code=status.HTTP_201_CREATED)
def create_customer(
    payload: CustomerCreate,
    svc: Service,
    authz: Authz,
    users: Users,
    user: Annotated[User, Depends(require_permission(MODULE, "create"))],
) -> CustomerCreateOut:
    try:
        customer, duplicates = svc.create_customer(
            name=payload.name,
            customer_kind=payload.customer_kind,
            tax_code=payload.tax_code,
            phone=payload.phone,
            email=payload.email,
            address=payload.address,
            contact_name=payload.contact_name,
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
        duplicate=_first_dup(duplicates),
        duplicates=_dup_warns(duplicates),
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
    tag_map = svc.customers.tags_for([customer.id])
    return CustomerDetailOut(
        customer=_row(customer, names, stat, tags=tag_map.get(customer.id)),
        receivable=_receivable_card(
            svc, customer, can_view=authz.can(user, MODULE, "view_debt")
        ),
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
        months=[MonthPointOut(**vars(m)) for m in d.months],
        product_mix=[ProductSliceOut(**vars(s)) for s in d.product_mix],
        heatmap=[HeatCellOut(**vars(h)) for h in d.heatmap],
        has_data=d.has_data,
        receivable=_receivable_card(
            svc, customer, can_view=authz.can(user, MODULE, "view_debt")
        ),
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
    "reassign_customer": "Điều chuyển phụ trách",
}
_CARE_KIND_LABELS = {
    "goi_dien": "Gọi điện",
    "nhan_tin": "Nhắn tin",
    "email": "Email",
    "gap_truc_tiep": "Gặp trực tiếp",
    "khac": "Chăm sóc khác",
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

    # 3) Care events (#20) — hoạt động chăm sóc gộp vào cùng dòng thời gian.
    for ev in svc.list_care_events(customer_id=customer_id, scope=scope, actor=user):
        actor_u = users.get_by_id(ev.created_by) if ev.created_by is not None else None
        items.append(
            CustomerAuditRowOut(
                at=ev.happened_at,
                kind="care",
                action="care_event",
                title=_CARE_KIND_LABELS.get(ev.kind, ev.kind),
                detail=ev.note,
                actor_name=(actor_u.name or actor_u.username) if actor_u else None,
            )
        )

    # 4) Real quotation events.
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
    user: Annotated[User, Depends(require_permission(MODULE, "export"))],
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
        customer, duplicates = svc.update_customer(
            customer_id=customer_id,
            scope=scope,
            actor=user,
            name=payload.name,
            customer_kind=payload.customer_kind,
            tax_code=payload.tax_code,
            phone=payload.phone,
            email=payload.email,
            address=payload.address,
            contact_name=payload.contact_name,
            sale_user_id=payload.sale_user_id,
            allow_reassign=authz.can(user, MODULE, "reassign"),
        )
    except ReassignForbidden as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e)) from None
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
        customer=_row(customer, names),
        duplicate=_first_dup(duplicates),
        duplicates=_dup_warns(duplicates),
    )


@router.put("/{customer_id}/financial", response_model=CustomerDetailOut)
def update_customer_financial(
    customer_id: int,
    payload: CustomerFinancialIn,
    svc: Service,
    analytics: Analytics,
    authz: Authz,
    users: Users,
    user: Annotated[User, Depends(require_permission(MODULE, "update"))],
) -> CustomerDetailOut:
    """Sửa CHÍNH SÁCH TÀI CHÍNH khách (hạn mức + số ngày công nợ tối đa + rào chiết khấu/biên)
    — endpoint RIÊNG (redesign spec-06 v2), gate quyền chi tiết `set_credit_terms`. Ai cũng
    XEM qua GET detail; chỉ quyền này mới SỬA (thiếu → 403, KHÔNG đụng field định danh)."""
    if not authz.can(user, MODULE, "set_credit_terms"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Bạn không có quyền thiết lập chính sách tài chính khách hàng.",
        )
    scope = _scope_for(authz, user)
    try:
        customer = svc.update_financial(
            customer_id=customer_id,
            scope=scope,
            actor=user,
            credit_limit=payload.credit_limit,
            payment_term_days=payload.payment_term_days,
            discount_min_pct=payload.discount_min_pct,
            discount_max_pct=payload.discount_max_pct,
            margin_min_pct=payload.margin_min_pct,
            margin_max_pct=payload.margin_max_pct,
        )
    except CustomerValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e)
        ) from None
    except (CustomerNotFound, CustomerForbidden):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy khách hàng."
        ) from None
    names = _sale_names(
        users, {customer.sale_user_id} if customer.sale_user_id else set()
    )
    stat = analytics.list_stats([customer]).per_customer.get(customer.id)
    tag_map = svc.customers.tags_for([customer.id])
    return CustomerDetailOut(
        customer=_row(customer, names, stat, tags=tag_map.get(customer.id)),
        receivable=_receivable_card(
            svc, customer, can_view=authz.can(user, MODULE, "view_debt")
        ),
    )


# --- người liên hệ (#10–#11) --------------------------------------------------


@router.get("/{customer_id}/contacts", response_model=ContactsOut)
def list_contacts(
    customer_id: int,
    svc: Service,
    authz: Authz,
    user: Annotated[User, Depends(require_permission(MODULE, "read"))],
) -> ContactsOut:
    try:
        items = svc.list_contacts(
            customer_id=customer_id, scope=_scope_for(authz, user), actor=user
        )
    except (CustomerNotFound, CustomerForbidden):
        raise _not_found() from None
    return ContactsOut(items=[ContactOut.model_validate(c) for c in items])


@router.post("/{customer_id}/contacts", response_model=ContactOut, status_code=201)
def add_contact(
    customer_id: int,
    payload: ContactIn,
    svc: Service,
    authz: Authz,
    user: Annotated[User, Depends(require_permission(MODULE, "update"))],
) -> ContactOut:
    try:
        contact = svc.add_contact(
            customer_id=customer_id, scope=_scope_for(authz, user), actor=user,
            name=payload.name, title=payload.title, duty=payload.duty,
            phone=payload.phone, email=payload.email, is_primary=payload.is_primary,
        )
    except CustomerValidationError as e:
        raise HTTPException(status_code=422, detail=str(e)) from None
    except (CustomerNotFound, CustomerForbidden):
        raise _not_found() from None
    return ContactOut.model_validate(contact)


@router.put("/{customer_id}/contacts/{contact_id}", response_model=ContactOut)
def update_contact(
    customer_id: int,
    contact_id: int,
    payload: ContactIn,
    svc: Service,
    authz: Authz,
    user: Annotated[User, Depends(require_permission(MODULE, "update"))],
) -> ContactOut:
    try:
        contact = svc.update_contact(
            customer_id=customer_id, contact_id=contact_id,
            scope=_scope_for(authz, user), actor=user,
            name=payload.name, title=payload.title, duty=payload.duty,
            phone=payload.phone, email=payload.email, is_primary=payload.is_primary,
        )
    except CustomerValidationError as e:
        raise HTTPException(status_code=422, detail=str(e)) from None
    except (CustomerNotFound, CustomerForbidden):
        raise _not_found() from None
    return ContactOut.model_validate(contact)


@router.delete("/{customer_id}/contacts/{contact_id}", status_code=204)
def delete_contact(
    customer_id: int,
    contact_id: int,
    svc: Service,
    authz: Authz,
    user: Annotated[User, Depends(require_permission(MODULE, "update"))],
):
    try:
        svc.delete_contact(
            customer_id=customer_id, contact_id=contact_id,
            scope=_scope_for(authz, user), actor=user,
        )
    except (CustomerNotFound, CustomerForbidden):
        raise _not_found() from None


# --- địa chỉ giao hàng (#9) -----------------------------------------------------


@router.get("/{customer_id}/addresses", response_model=AddressesOut)
def list_addresses(
    customer_id: int,
    svc: Service,
    authz: Authz,
    user: Annotated[User, Depends(require_permission(MODULE, "read"))],
) -> AddressesOut:
    try:
        items = svc.list_addresses(
            customer_id=customer_id, scope=_scope_for(authz, user), actor=user
        )
    except (CustomerNotFound, CustomerForbidden):
        raise _not_found() from None
    return AddressesOut(items=[AddressOut.model_validate(a) for a in items])


@router.post("/{customer_id}/addresses", response_model=AddressOut, status_code=201)
def add_address(
    customer_id: int,
    payload: AddressIn,
    svc: Service,
    authz: Authz,
    user: Annotated[User, Depends(require_permission(MODULE, "update"))],
) -> AddressOut:
    try:
        row = svc.add_address(
            customer_id=customer_id, scope=_scope_for(authz, user), actor=user,
            label=payload.label, address=payload.address, phone=payload.phone,
            note=payload.note, is_default=payload.is_default,
        )
    except CustomerValidationError as e:
        raise HTTPException(status_code=422, detail=str(e)) from None
    except (CustomerNotFound, CustomerForbidden):
        raise _not_found() from None
    return AddressOut.model_validate(row)


@router.put("/{customer_id}/addresses/{address_id}", response_model=AddressOut)
def update_address(
    customer_id: int,
    address_id: int,
    payload: AddressIn,
    svc: Service,
    authz: Authz,
    user: Annotated[User, Depends(require_permission(MODULE, "update"))],
) -> AddressOut:
    try:
        row = svc.update_address(
            customer_id=customer_id, address_id=address_id,
            scope=_scope_for(authz, user), actor=user,
            label=payload.label, address=payload.address, phone=payload.phone,
            note=payload.note, is_default=payload.is_default,
        )
    except CustomerValidationError as e:
        raise HTTPException(status_code=422, detail=str(e)) from None
    except (CustomerNotFound, CustomerForbidden):
        raise _not_found() from None
    return AddressOut.model_validate(row)


@router.delete("/{customer_id}/addresses/{address_id}", status_code=204)
def delete_address(
    customer_id: int,
    address_id: int,
    svc: Service,
    authz: Authz,
    user: Annotated[User, Depends(require_permission(MODULE, "update"))],
):
    try:
        svc.delete_address(
            customer_id=customer_id, address_id=address_id,
            scope=_scope_for(authz, user), actor=user,
        )
    except (CustomerNotFound, CustomerForbidden):
        raise _not_found() from None


# --- chăm sóc: nhật ký + lịch hẹn (#20/#27/#28) --------------------------------


def _care_event_out(ev, names: dict[int, str]) -> CareEventOut:
    out = CareEventOut.model_validate(ev)
    if ev.created_by is not None:
        out.actor_name = names.get(ev.created_by)
    return out


def _care_task_out(svc: CustomerService, t, names: dict[int, str]) -> CareTaskOut:
    out = CareTaskOut.model_validate(t)
    if t.assignee_user_id is not None:
        out.assignee_name = names.get(t.assignee_user_id)
    if t.status == "open":
        out.remind_level, out.overdue_days = svc.remind_level(t.due_date)
    return out


@router.get("/{customer_id}/care", response_model=CareEventsOut)
def list_care_events(
    customer_id: int,
    svc: Service,
    authz: Authz,
    users: Users,
    user: Annotated[User, Depends(require_permission(MODULE, "read"))],
) -> CareEventsOut:
    try:
        items = svc.list_care_events(
            customer_id=customer_id, scope=_scope_for(authz, user), actor=user
        )
    except (CustomerNotFound, CustomerForbidden):
        raise _not_found() from None
    names = _sale_names(users, {e.created_by for e in items if e.created_by})
    return CareEventsOut(items=[_care_event_out(e, names) for e in items])


@router.post("/{customer_id}/care", response_model=CareEventOut, status_code=201)
def add_care_event(
    customer_id: int,
    payload: CareEventIn,
    svc: Service,
    authz: Authz,
    users: Users,
    user: Annotated[User, Depends(require_permission(MODULE, "update"))],
) -> CareEventOut:
    try:
        ev = svc.add_care_event(
            customer_id=customer_id, scope=_scope_for(authz, user), actor=user,
            kind=payload.kind, note=payload.note, happened_at=payload.happened_at,
        )
    except CustomerValidationError as e:
        raise HTTPException(status_code=422, detail=str(e)) from None
    except (CustomerNotFound, CustomerForbidden):
        raise _not_found() from None
    names = _sale_names(users, {ev.created_by} if ev.created_by else set())
    return _care_event_out(ev, names)


@router.get("/{customer_id}/care-tasks", response_model=CareTasksOut)
def list_care_tasks(
    customer_id: int,
    svc: Service,
    authz: Authz,
    users: Users,
    user: Annotated[User, Depends(require_permission(MODULE, "read"))],
) -> CareTasksOut:
    try:
        items = svc.list_care_tasks(
            customer_id=customer_id, scope=_scope_for(authz, user), actor=user
        )
    except (CustomerNotFound, CustomerForbidden):
        raise _not_found() from None
    names = _sale_names(users, {t.assignee_user_id for t in items if t.assignee_user_id})
    on_time, late, overdue_open = svc.care_stats(items)
    return CareTasksOut(
        items=[_care_task_out(svc, t, names) for t in items],
        done_on_time=on_time,
        done_late=late,
        overdue_open=overdue_open,
    )


@router.post("/{customer_id}/care-tasks", response_model=CareTaskOut, status_code=201)
def add_care_task(
    customer_id: int,
    payload: CareTaskIn,
    svc: Service,
    authz: Authz,
    users: Users,
    user: Annotated[User, Depends(require_permission(MODULE, "update"))],
) -> CareTaskOut:
    try:
        task = svc.add_care_task(
            customer_id=customer_id, scope=_scope_for(authz, user), actor=user,
            note=payload.note, due_date=payload.due_date,
            assignee_user_id=payload.assignee_user_id,
        )
    except CustomerValidationError as e:
        raise HTTPException(status_code=422, detail=str(e)) from None
    except (CustomerNotFound, CustomerForbidden):
        raise _not_found() from None
    names = _sale_names(
        users, {task.assignee_user_id} if task.assignee_user_id else set()
    )
    return _care_task_out(svc, task, names)


@router.put("/{customer_id}/care-tasks/{task_id}/status", response_model=CareTaskOut)
def set_care_task_status(
    customer_id: int,
    task_id: int,
    payload: CareTaskStatusIn,
    svc: Service,
    authz: Authz,
    users: Users,
    user: Annotated[User, Depends(require_permission(MODULE, "update"))],
) -> CareTaskOut:
    try:
        task = svc.set_care_task_status(
            customer_id=customer_id, task_id=task_id,
            scope=_scope_for(authz, user), actor=user,
            status=payload.status, log_kind=payload.log_kind, log_note=payload.log_note,
        )
    except CustomerValidationError as e:
        raise HTTPException(status_code=422, detail=str(e)) from None
    except (CustomerNotFound, CustomerForbidden):
        raise _not_found() from None
    names = _sale_names(
        users, {task.assignee_user_id} if task.assignee_user_id else set()
    )
    return _care_task_out(svc, task, names)


# --- tài liệu đính kèm (#21) ------------------------------------------------------


@router.get("/{customer_id}/attachments", response_model=CustomerAttachmentsOut)
def list_attachments(
    customer_id: int,
    svc: Service,
    authz: Authz,
    user: Annotated[User, Depends(require_permission(MODULE, "read"))],
) -> CustomerAttachmentsOut:
    try:
        items = svc.list_attachments(
            customer_id=customer_id, scope=_scope_for(authz, user), actor=user
        )
    except (CustomerNotFound, CustomerForbidden):
        raise _not_found() from None
    return CustomerAttachmentsOut(
        items=[CustomerAttachmentOut.model_validate(a) for a in items]
    )


@router.post("/{customer_id}/attachments", response_model=CustomerAttachmentOut, status_code=201)
def upload_attachment(
    customer_id: int,
    svc: Service,
    authz: Authz,
    user: Annotated[User, Depends(require_permission(MODULE, "update"))],
    file: UploadFile = File(...),
    doc_kind: str = Form(default="khac"),
) -> CustomerAttachmentOut:
    scope = _scope_for(authz, user)
    # Access check first so we don't write a file for an inaccessible customer.
    _load_scoped(svc, customer_id, scope, user)

    safe_name = Path(file.filename or "file").name
    token = secrets.token_hex(4)
    dest_dir = _STATIC_DIR / "crm" / str(customer_id)
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"{token}_{safe_name}"
    with dest.open("wb") as f:
        f.write(file.file.read())
    file_url = f"/static/crm/{customer_id}/{token}_{safe_name}"

    try:
        att = svc.add_attachment(
            customer_id=customer_id, scope=scope, actor=user, doc_kind=doc_kind,
            file_name=safe_name, file_url=file_url, file_type=file.content_type,
        )
    except (CustomerNotFound, CustomerForbidden):
        raise _not_found() from None
    return CustomerAttachmentOut.model_validate(att)


@router.delete("/{customer_id}/attachments/{attachment_id}", status_code=204)
def delete_attachment(
    customer_id: int,
    attachment_id: int,
    svc: Service,
    authz: Authz,
    user: Annotated[User, Depends(require_permission(MODULE, "update"))],
):
    try:
        svc.delete_attachment(
            customer_id=customer_id, attachment_id=attachment_id,
            scope=_scope_for(authz, user), actor=user,
        )
    except (CustomerNotFound, CustomerForbidden):
        raise _not_found() from None


# --- helpers ---------------------------------------------------------------


def _not_found() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy khách hàng."
    )


def _load_scoped(
    svc: CustomerService, customer_id: int, scope: str, user: User
) -> Customer:
    try:
        return svc.get_customer(customer_id=customer_id, scope=scope, actor=user)
    except (CustomerNotFound, CustomerForbidden):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy khách hàng."
        ) from None


def _dup_warns(duplicates: list[tuple[str, Customer]]) -> list[DuplicateWarn]:
    return [
        DuplicateWarn(field=f, id=c.id, code=c.code, name=c.name) for f, c in duplicates
    ]


def _first_dup(duplicates: list[tuple[str, Customer]]) -> DuplicateRef | None:
    """Back-compat: cảnh báo MST đầu tiên (shape cũ) — None nếu không trùng MST."""
    for f, c in duplicates:
        if f == "tax_code":
            return DuplicateRef(id=c.id, code=c.code, name=c.name)
    return None


def _receivable_card(
    svc: CustomerService, customer: Customer, *, can_view: bool = True
) -> ReceivableCard:
    """Build the read-only Công nợ card. On SEAM-16 (Công nợ chưa build) return an
    explicit unavailable card — NEVER a fabricated 0 (§34 L885 / spec KH-04).
    `can_view=False` (quyền chi tiết `view_debt` tắt) → ẩn số liệu công nợ."""
    if not can_view:
        return ReceivableCard(
            available=False,
            credit_limit=customer.credit_limit,
            message="Bạn không có quyền xem công nợ",
        )
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
