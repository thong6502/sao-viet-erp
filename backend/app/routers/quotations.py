"""Báo giá (Quotation) routes — spec-09-bao-gia (F1..F7).

Thin HTTP shell over QuotationService. Every route is guarded by
`require_permission('bao_gia', <action>)`; list/detail additionally narrow to the caller's
data scope (own/department/all). SEAM reads:
  - SEAM-13 (Tính giá result): the costing-picker endpoint surfaces "Tính giá chưa sẵn sàng"
    while the giá-vốn engine is TREO — never a fabricated cost.
  - SEAM-14 (CRM): CLOSED — the customer display name is resolved via the injected adapter.

The PDF (F6) is a tài liệu đối ngoại: it prints ONLY giá bán + lãi + chiết khấu and NEVER
số con/khổ, số tờ, số bản kẽm, bù hao or the cost buildup (L1132/L1218).
"""
from __future__ import annotations

import io
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status

from ..deps import (
    get_authorization_service,
    get_quotation_service,
    require_permission,
)
from ..models.quotation import QUOTATION_STATUSES, Quotation
from ..models.role import SCOPE_ALL, SCOPE_DEPARTMENT
from ..models.user import User
from ..schemas.quotation import (
    CostingPickerOut,
    CostingQtyOption,
    CustomerDisplayOut,
    EnumOption,
    QuotationCreate,
    QuotationDetailOut,
    QuotationEnumsOut,
    QuotationListOut,
    QuotationRow,
    QuotationUpdate,
    TransitionRequest,
    VersionRow,
)
from ..services.quotation_service import (
    CostingUnavailable,
    QuotationConflict,
    QuotationForbidden,
    QuotationLocked,
    QuotationNotFound,
    QuotationService,
    QuotationValidationError,
)
from ..services.quotation_state import TRANSITIONS
from ..services.rbac_service import AuthorizationService

router = APIRouter(prefix="/api/quotations", tags=["quotations"])

MODULE = "bao_gia"

Service = Annotated[QuotationService, Depends(get_quotation_service)]
Authz = Annotated[AuthorizationService, Depends(get_authorization_service)]

STATUS_LABELS = {
    "draft": "Nháp",
    "sent": "Đã gửi",
    "approved": "Đã duyệt",
    "rejected": "Từ chối",
    "expired": "Hết hạn",
    "cancelled": "Đã hủy",
    "on_hold": "Tạm giữ",
    "change_order": "Đã re-quote",
}


def _scope_for(authz: AuthorizationService, user: User) -> str:
    return authz.scope_for(user, MODULE) or "own"


def _can_approve(scope: str) -> bool:
    """ngưỡng X/Y — SVN-input, ⚠️ chưa xác nhận; at P0 = manager scope of bao_gia."""
    return scope in (SCOPE_DEPARTMENT, SCOPE_ALL)


def _allowed_transitions(current_status: str) -> list[str]:
    return [to for (frm, to) in TRANSITIONS if frm == current_status]


def _row(q: Quotation, customer_name: str | None) -> QuotationRow:
    return QuotationRow(
        id=q.id,
        code=q.code,
        version=q.version,
        customer_id=q.customer_id,
        customer_name=customer_name,
        total=q.total,
        status=q.status,
        valid_until=q.valid_until,
    )


def _detail(svc: QuotationService, q: Quotation, scope: str) -> QuotationDetailOut:
    ref = svc.customer_display(q)
    customer = (
        CustomerDisplayOut(
            customer_id=ref.customer_id,
            name=ref.name,
            tax_code=ref.tax_code,
            credit_status_display=ref.credit_status_display,
        )
        if ref is not None
        else None
    )
    out = QuotationDetailOut.model_validate(q)
    out.customer = customer
    out.allowed_transitions = _allowed_transitions(q.status)
    out.can_approve = _can_approve(scope)
    out.versions = [
        VersionRow(
            id=v.id, version=v.version, status=v.status, total=v.total, created_at=v.created_at
        )
        for v in svc.version_history(q)
    ]
    return out


# --- enums + Tính giá picker (SEAM-13) ----------------------------------------

@router.get("/enums", response_model=QuotationEnumsOut)
def quotation_enums(
    _: Annotated[User, Depends(require_permission(MODULE, "read"))],
) -> QuotationEnumsOut:
    return QuotationEnumsOut(
        statuses=[
            EnumOption(value=v, label=STATUS_LABELS.get(v, v)) for v in QUOTATION_STATUSES
        ]
    )


@router.get("/costings/{costing_id}", response_model=CostingPickerOut)
def read_costing(
    costing_id: int,
    svc: Service,
    _: Annotated[User, Depends(require_permission(MODULE, "read"))],
    quantity: int | None = Query(default=None, ge=1),
) -> CostingPickerOut:
    """Reference a Tính giá result (SEAM-13 — CLOSED). Returns the frozen giá vốn of the
    chosen quantity point + the other quantity points (bậc SL). When the estimate can't
    yield a result the reason is surfaced verbatim (never a fabricated cost_von_total)."""
    try:
        result = svc.costing_picker(costing_id, quantity=quantity)
    except CostingUnavailable as e:
        return CostingPickerOut(available=False, message=str(e))
    return CostingPickerOut(
        available=True,
        cost_von_total=result.cost_von_total,
        quantity=result.quantity,
        options=[
            CostingQtyOption(quantity=o["quantity"], total_cost=o["total_cost"])
            for o in (result.quantity_options or [])
        ],
    )


# --- list (F1) -----------------------------------------------------------------

@router.get("", response_model=QuotationListOut)
def list_quotations(
    svc: Service,
    authz: Authz,
    user: Annotated[User, Depends(require_permission(MODULE, "read"))],
    q: str | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
    sort: str = Query(default="-created_at"),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=200),
) -> QuotationListOut:
    scope = _scope_for(authz, user)
    rows, total, names = svc.list_quotations(
        scope=scope, actor=user, q=q, status=status_filter, sort=sort, page=page, size=size
    )
    return QuotationListOut(
        items=[_row(r, names.get(r.id)) for r in rows],
        total=total,
        page=page,
        size=size,
    )


# --- create / read / update (F2) ----------------------------------------------

@router.post("", response_model=QuotationDetailOut, status_code=status.HTTP_201_CREATED)
def create_quotation(
    payload: QuotationCreate,
    svc: Service,
    authz: Authz,
    user: Annotated[User, Depends(require_permission(MODULE, "create"))],
) -> QuotationDetailOut:
    scope = _scope_for(authz, user)
    try:
        q = svc.create_quotation(
            customer_id=payload.customer_id,
            costing_id=payload.costing_id,
            cost_von_total=payload.cost_von_total,
            margin=payload.margin,
            discount=payload.discount,
            valid_until=payload.valid_until,
            actor=user,
        )
    except QuotationValidationError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e)) from None
    return _detail(svc, q, scope)


@router.get("/{quotation_id}", response_model=QuotationDetailOut)
def get_quotation(
    quotation_id: int,
    svc: Service,
    authz: Authz,
    user: Annotated[User, Depends(require_permission(MODULE, "read"))],
) -> QuotationDetailOut:
    scope = _scope_for(authz, user)
    try:
        q = svc.get_quotation(quotation_id=quotation_id, scope=scope, actor=user)
    except QuotationNotFound:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Không tìm thấy báo giá.") from None
    except QuotationForbidden:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Không tìm thấy báo giá.") from None
    return _detail(svc, q, scope)


@router.put("/{quotation_id}", response_model=QuotationDetailOut)
def update_quotation(
    quotation_id: int,
    payload: QuotationUpdate,
    svc: Service,
    authz: Authz,
    user: Annotated[User, Depends(require_permission(MODULE, "update"))],
) -> QuotationDetailOut:
    scope = _scope_for(authz, user)
    try:
        q = svc.update_quotation(
            quotation_id=quotation_id, scope=scope, actor=user,
            customer_id=payload.customer_id,
            costing_id=payload.costing_id,
            cost_von_total=payload.cost_von_total,
            margin=payload.margin,
            discount=payload.discount,
            valid_until=payload.valid_until,
            row_version=payload.row_version,
        )
    except (QuotationNotFound, QuotationForbidden):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Không tìm thấy báo giá.") from None
    except QuotationLocked as e:
        raise HTTPException(status.HTTP_409_CONFLICT, str(e)) from None
    except QuotationConflict as e:
        raise HTTPException(status.HTTP_409_CONFLICT, str(e)) from None
    except QuotationValidationError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e)) from None
    return _detail(svc, q, scope)


# --- lifecycle transitions (F3/F4/F5) -----------------------------------------

@router.post("/{quotation_id}/transition", response_model=QuotationDetailOut)
def transition_quotation(
    quotation_id: int,
    payload: TransitionRequest,
    svc: Service,
    authz: Authz,
    user: Annotated[User, Depends(require_permission(MODULE, "update"))],
) -> QuotationDetailOut:
    scope = _scope_for(authz, user)
    try:
        q = svc.transition(
            quotation_id=quotation_id, to_status=payload.to_status, scope=scope, actor=user,
            row_version=payload.row_version, cancel_reason=payload.cancel_reason,
        )
    except (QuotationNotFound, QuotationForbidden) as e:
        # Approver-permission failure is a 403; not-found/out-of-scope is 404.
        if isinstance(e, QuotationForbidden) and "duyệt" in str(e):
            raise HTTPException(status.HTTP_403_FORBIDDEN, str(e)) from None
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Không tìm thấy báo giá.") from None
    except QuotationConflict as e:
        raise HTTPException(status.HTTP_409_CONFLICT, str(e)) from None
    except QuotationValidationError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e)) from None
    return _detail(svc, q, scope)


@router.post("/{quotation_id}/requote", response_model=QuotationDetailOut, status_code=status.HTTP_201_CREATED)
def requote_quotation(
    quotation_id: int,
    svc: Service,
    authz: Authz,
    user: Annotated[User, Depends(require_permission(MODULE, "create"))],
) -> QuotationDetailOut:
    scope = _scope_for(authz, user)
    try:
        new_v = svc.requote(quotation_id=quotation_id, scope=scope, actor=user)
    except (QuotationNotFound, QuotationForbidden):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Không tìm thấy báo giá.") from None
    except QuotationConflict as e:
        raise HTTPException(status.HTTP_409_CONFLICT, str(e)) from None
    return _detail(svc, new_v, scope)


# --- PDF đối ngoại (F6) --------------------------------------------------------

@router.get("/{quotation_id}/pdf")
def quotation_pdf(
    quotation_id: int,
    svc: Service,
    authz: Authz,
    user: Annotated[User, Depends(require_permission(MODULE, "read"))],
) -> Response:
    """1 PDF template đối ngoại: giá bán + lãi + chiết khấu ONLY. NEVER số con/khổ, số tờ,
    số bản kẽm, bù hao, hay cost buildup (L1132/L1218)."""
    scope = _scope_for(authz, user)
    try:
        q = svc.get_quotation(quotation_id=quotation_id, scope=scope, actor=user)
    except (QuotationNotFound, QuotationForbidden):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Không tìm thấy báo giá.") from None

    ref = svc.customer_display(q)
    pdf_bytes = _render_pdf(q, ref)
    # No Content-Disposition: the frontend fetches this as a blob and opens it in a new tab,
    # so a `Content-Disposition` would make Chromium intercept the response as a download and
    # abort the fetch ("Failed to fetch"). The blob URL + window.open handles presentation.
    return Response(content=pdf_bytes, media_type="application/pdf")


def _fmt_vnd(value: int | None) -> str:
    if value is None:
        return "—"
    return f"{value:,} đ".replace(",", ".")


def _render_pdf(q: Quotation, ref) -> bytes:
    """Build the customer-facing quotation PDF. Deliberately contains only the pricing the
    customer sees — the buildup is never referenced here."""
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.pdfgen import canvas

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    width, height = A4
    y = height - 30 * mm

    c.setFont("Helvetica-Bold", 18)
    c.drawString(25 * mm, y, "BAO GIA / QUOTATION")
    y -= 10 * mm
    c.setFont("Helvetica", 11)
    c.drawString(25 * mm, y, f"Ma: {q.code}  -  Version: {q.version}")
    y -= 7 * mm
    if ref is not None:
        c.drawString(25 * mm, y, f"Khach hang: {ref.name}")
        y -= 7 * mm
        if ref.tax_code:
            c.drawString(25 * mm, y, f"MST: {ref.tax_code}")
            y -= 7 * mm
    if q.valid_until is not None:
        c.drawString(25 * mm, y, f"Hieu luc den: {q.valid_until.isoformat()}")
        y -= 10 * mm

    # Pricing block — the ONLY figures on the document (đối ngoại).
    c.setFont("Helvetica-Bold", 12)
    c.drawString(25 * mm, y, "Bang gia ban")
    y -= 8 * mm
    c.setFont("Helvetica", 11)
    for label, val in (
        ("Gia von", q.cost_von_total),
        ("Lai", q.margin),
        ("Chiet khau", -q.discount if q.discount else 0),
    ):
        c.drawString(30 * mm, y, label)
        c.drawRightString(width - 25 * mm, y, _fmt_vnd(val))
        y -= 7 * mm
    y -= 2 * mm
    c.setFont("Helvetica-Bold", 12)
    c.drawString(30 * mm, y, "TONG GIA BAN")
    c.drawRightString(width - 25 * mm, y, _fmt_vnd(q.total))

    c.setFont("Helvetica-Oblique", 8)
    c.drawString(25 * mm, 15 * mm, "Tai lieu doi ngoai — khong the hien chi tiet gia thanh.")
    c.showPage()
    c.save()
    return buf.getvalue()
