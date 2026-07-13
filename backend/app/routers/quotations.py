"""Báo giá (Quotation / Quote) routes — spec-09-bao-gia.
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
from ..models.quotation import (
    QUOTE_STATUSES,
    STATUS_ACCEPTED,
    STATUS_CANCELLED,
    Quote,
    QuoteVersion,
)
from ..models.user import User
from ..schemas.quotation import (
    CostingPickerOut,
    CostingQtyOption,
    CustomerDisplayOut,
    EnumOption,
    QuotationCreate,
    QuotationDetailOut,
    QuotationEnumsOut,
    QuoteApprovalIn,
    QuoteApprovalListOut,
    QuoteApprovalOut,
    QuotationListOut,
    QuotationRow,
    QuotationStatsOut,
    QuotationUpdate,
    TransitionRequest,
    VersionRow,
    QuoteItemOut,
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
    # 7 trạng thái nghiệp vụ (redesign-bao-gia §3) — bám đúng chữ chủ đầu tư chốt.
    "draft": "Nháp",
    "pending_approval": "Chờ duyệt",   # đặc thù đã "Trình duyệt", chờ Giám đốc Kinh doanh
    "sent": "Đã duyệt",                 # gộp "đã gửi khách" (Q2 không tách)
    "accepted": "Khách hàng đồng ý",
    "rejected": "Khách hàng từ chối",
    "expired": "Hết hiệu lực",
    "converted_to_order": "Đã lên đơn",
    "cancelled": "Hủy báo giá",
}


def _scope_for(authz: AuthorizationService, user: User) -> str:
    return authz.scope_for(user, MODULE) or "own"


def _allowed_transitions(current_status: str) -> list[str]:
    return [to for (frm, to) in TRANSITIONS if frm == current_status]


def _row(
    q: Quote,
    customer_name: str | None,
    est_numbers: dict[int, str] | None = None,
    user_names: dict[int, str] | None = None,
) -> QuotationRow:
    active_version = None
    for v in q.versions:
        if v.id == q.current_version_id:
            active_version = v
            break

    est_numbers = est_numbers or {}
    items = list(active_version.items) if active_version else []

    # ↳ các mã phiếu tính giá tham chiếu (item-level trước, header fallback)
    ref_ids: list[int] = []
    for it in items:
        eid = it.estimate_id or q.estimate_id
        if eid and eid not in ref_ids:
            ref_ids.append(eid)
    if not ref_ids and q.estimate_id:
        ref_ids.append(q.estimate_id)
    estimate_refs = [est_numbers[i] for i in ref_ids if i in est_numbers]

    # "Catalogue A4 + 2 SP khác"
    product_summary = None
    if items:
        names_seen: list[str] = []
        for it in items:
            if it.product_name not in names_seen:
                names_seen.append(it.product_name)
        product_summary = names_seen[0] + (f" + {len(names_seen) - 1} SP khác" if len(names_seen) > 1 else "")

    return QuotationRow(
        id=q.id,
        code=q.quote_number,
        version=active_version.version_number if active_version else 1,
        customer_id=q.customer_id,
        customer_name=customer_name or q.customer_name_snapshot,
        total=int(active_version.final_amount) if active_version else 0,
        status=q.status,
        valid_until=q.valid_until,
        version_count=len(q.versions),
        sent_at=active_version.sent_at if active_version else None,
        margin_percent=float(items[0].margin_percent) if items else None,
        estimate_refs=estimate_refs,
        product_summary=product_summary,
        updated_at=q.updated_at,
        salesperson_name=(user_names or {}).get(q.salesperson_id),
    )


def _detail(
    svc: QuotationService, q: Quote, scope: str, *,
    can_approve: bool = False, can_approve_exception: bool = False,
) -> QuotationDetailOut:
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

    active_version = None
    for v in q.versions:
        if v.id == q.current_version_id:
            active_version = v
            break

    total_cost = 0.0
    subtotal_amount = 0.0
    discount_amount = 0.0
    vat_amount = 0.0
    total = 0.0
    items_out = []

    if active_version:
        total_cost = float(active_version.total_cost_snapshot or 0.0)
        subtotal_amount = float(active_version.subtotal_amount or 0.0)
        discount_amount = float(active_version.discount_amount or 0.0)
        vat_amount = float(active_version.vat_amount or 0.0)
        total = float(active_version.final_amount or 0.0)

        est_numbers = svc.estimate_numbers(
            {it.estimate_id or q.estimate_id for it in active_version.items} | ({q.estimate_id} if q.estimate_id else set())
        )
        for item in active_version.items:
            item_est_id = item.estimate_id or q.estimate_id
            items_out.append(
                QuoteItemOut(
                    id=item.id,
                    estimate_id=item_est_id,
                    estimate_number=est_numbers.get(item_est_id),
                    estimate_option_id=item.estimate_option_id,
                    line_no=item.line_no,
                    po_code=item.po_code,
                    product_type=item.product_type,
                    product_name=item.product_name,
                    product_spec_text=item.product_spec_text,
                    quantity=item.quantity,
                    unit=item.unit,
                    total_cost_snapshot=float(item.total_cost_snapshot),
                    margin_percent=float(item.margin_percent),
                    selling_price=float(item.selling_price),
                    unit_price=float(item.unit_price),
                    discount_amount=float(item.discount_amount),
                    vat_percent=float(item.vat_percent),
                    vat_amount=float(item.vat_amount),
                    final_amount=float(item.final_amount),
                    note=item.note,
                )
            )

    versions_out = []
    for v in svc.version_history(q):
        versions_out.append(
            VersionRow(
                id=v.id,
                version=v.version_number,
                status=v.status,
                total=int(v.final_amount),
                created_at=v.created_at,
                change_reason=v.change_reason,
            )
        )

    return QuotationDetailOut(
        id=q.id,
        code=q.quote_number,
        version=active_version.version_number if active_version else 1,
        customer_id=q.customer_id,
        customer=customer,
        estimate_id=q.estimate_id,
        phieu_tinh_gia_id=q.phieu_tinh_gia_id,
        phieu_tinh_gia_ma=svc.phieu_tinh_gia_ref(q)["ma"],
        valid_until=q.valid_until,
        status=q.status,
        cancel_reason=q.cancel_reason,
        payment_terms=q.payment_terms,
        delivery_terms=q.delivery_terms,
        delivery_address=q.delivery_address,
        contact_name_snapshot=q.contact_name_snapshot,
        contact_phone_snapshot=q.contact_phone_snapshot,
        contact_title_snapshot=q.contact_title_snapshot,
        customer_note=q.customer_note,
        internal_note=q.internal_note,
        total_cost=total_cost,
        subtotal_amount=subtotal_amount,
        discount_amount=discount_amount,
        vat_amount=vat_amount,
        total=total,
        versions=versions_out,
        items=items_out,
        allowed_transitions=_allowed_transitions(q.status),
        can_approve=can_approve,
        **_gate_fields(svc, q, can_approve_exception),
    )


def _gate_fields(svc: QuotationService, q: Quote, can_see_numbers: bool = True) -> dict:
    """Khối 'báo giá đặc thù' cho detail. Số biên (`margin_pct`) HIỆN cho mọi vai đọc được báo giá:
    NV Sales tự set biên khi soạn (thanh gói biên/slider) nên không còn giấu con số (redesign-bao-gia
    §10, cập nhật sau P7). Giữ tham số cũ để không phải sửa toàn bộ call-site."""
    del can_see_numbers  # không còn strip theo vai
    return svc.quote_gate(q)


# --- enums + Tính giá picker (SEAM-13) ----------------------------------------

@router.get("/enums", response_model=QuotationEnumsOut)
def quotation_enums(
    _: Annotated[User, Depends(require_permission(MODULE, "read"))],
) -> QuotationEnumsOut:
    return QuotationEnumsOut(
        statuses=[
            EnumOption(value=v, label=STATUS_LABELS.get(v, v)) for v in QUOTE_STATUSES
        ]
    )


@router.get("/costings/{costing_id}", response_model=CostingPickerOut)
def read_costing(
    costing_id: int,
    svc: Service,
    _: Annotated[User, Depends(require_permission(MODULE, "read"))],
) -> CostingPickerOut:
    """Reference an Estimate result. Returns the details of all calculated options."""
    try:
        if svc._estimates is None:
            return CostingPickerOut(available=False, message="Module Tính giá chưa sẵn sàng.")
        est = svc._estimates.get_by_id(costing_id)
        if est is None:
            return CostingPickerOut(available=False, message="Không tìm thấy phương án tính giá.")
        if est.status != "calculated":
            return CostingPickerOut(available=False, message="Phương án tính giá chưa được tính toán.")

        options_out = []
        for opt in est.options:
            pricing = svc.calculate_pricing(
                total_cost=float(opt.total_cost),
                margin_percent=float(opt.margin_percent or 20.0),
                vat_percent=float(opt.vat_percent or 10.0),
                quantity=opt.quantity
            )
            options_out.append(
                CostingQtyOption(
                    id=opt.id,
                    quantity=opt.quantity,
                    total_cost=int(opt.total_cost),
                    margin_percent=float(opt.margin_percent or 20.0),
                    selling_price=pricing["selling_price"],
                    discount_amount=pricing["discount_amount"],
                    vat_percent=float(opt.vat_percent or 10.0),
                    final_price=pricing["final_amount"],
                    unit_price=pricing["unit_price"],
                    actual_margin=pricing["actual_margin"],
                )
            )
        return CostingPickerOut(available=True, options=options_out)
    except CostingUnavailable as e:
        return CostingPickerOut(available=False, message=str(e))
    except Exception as e:
        return CostingPickerOut(available=False, message=f"Không tải được phương án: {e}")


# --- list ---------------------------------------------------------------------

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

    # Bulk map cho hiển thị 2 tầng: mã phiếu tính giá + tên người phụ trách
    est_ids: set[int] = set()
    user_ids: set[int] = set()
    for r in rows:
        if r.estimate_id:
            est_ids.add(r.estimate_id)
        if r.salesperson_id:
            user_ids.add(r.salesperson_id)
        for v in r.versions:
            if v.id == r.current_version_id:
                for it in v.items:
                    if it.estimate_id:
                        est_ids.add(it.estimate_id)
    est_numbers = svc.estimate_numbers(est_ids)
    user_names = svc.user_names(user_ids)

    return QuotationListOut(
        items=[_row(r, names.get(r.id), est_numbers, user_names) for r in rows],
        total=total,
        page=page,
        size=size,
    )


@router.get("/stats", response_model=QuotationStatsOut)
def quotation_stats(
    svc: Service,
    _: Annotated[User, Depends(require_permission(MODULE, "read"))],
) -> QuotationStatsOut:
    """Số đếm cho thanh tab list Báo giá."""
    return QuotationStatsOut(**svc.stats())


# --- create / read / update ---------------------------------------------------

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
            phieu_tinh_gia_id=payload.phieu_tinh_gia_id,
            estimate_id=payload.estimate_id,
            selected_option_ids=payload.selected_option_ids,
            picks=[p.model_dump() for p in payload.picks] if payload.picks else None,
            margin_percent=payload.margin_percent,
            valid_until=payload.valid_until,
            payment_terms=payload.payment_terms,
            delivery_terms=payload.delivery_terms,
            delivery_address=payload.delivery_address,
            customer_note=payload.customer_note,
            internal_note=payload.internal_note,
            actor=user,
        )
    except QuotationValidationError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e)) from None
    except QuotationConflict as e:
        # BG-1: PTG đã có báo giá đang hiệu lực (1 PTG → 1 BG).
        raise HTTPException(status.HTTP_409_CONFLICT, str(e)) from None
    return _detail(svc, q, scope, can_approve=authz.can(user, MODULE, "approve"),
        can_approve_exception=authz.can(user, MODULE, "approve_exception"))


@router.get("/by-phieu/{phieu_tinh_gia_id}")
def quote_id_for_phieu(
    phieu_tinh_gia_id: int,
    svc: Service,
    _: Annotated[User, Depends(require_permission(MODULE, "read"))],
) -> dict:
    """BG-1: báo giá ĐANG HIỆU LỰC của 1 Phiếu tính giá (để màn PTG quyết 'Tạo mới' hay 'Mở BG có sẵn').
    Trả `{quote_id, quote_number}` hoặc `{quote_id: null}` nếu chưa có."""
    existing = svc.quotations.active_for_phieu(phieu_tinh_gia_id)
    if existing is None:
        return {"quote_id": None, "quote_number": None}
    return {"quote_id": existing.id, "quote_number": existing.quote_number}


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
    return _detail(svc, q, scope, can_approve=authz.can(user, MODULE, "approve"),
        can_approve_exception=authz.can(user, MODULE, "approve_exception"))


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
        items_payload_list = None
        if payload.items is not None:
            items_payload_list = [item.model_dump() for item in payload.items]

        q = svc.update_quotation(
            quotation_id=quotation_id,
            scope=scope,
            actor=user,
            customer_id=payload.customer_id,
            valid_until=payload.valid_until,
            payment_terms=payload.payment_terms,
            delivery_terms=payload.delivery_terms,
            delivery_address=payload.delivery_address,
            customer_note=payload.customer_note,
            internal_note=payload.internal_note,
            items_payload=items_payload_list,
        )
    except (QuotationNotFound, QuotationForbidden):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Không tìm thấy báo giá.") from None
    except QuotationLocked as e:
        raise HTTPException(status.HTTP_409_CONFLICT, str(e)) from None
    except QuotationConflict as e:
        raise HTTPException(status.HTTP_409_CONFLICT, str(e)) from None
    except QuotationValidationError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e)) from None
    return _detail(svc, q, scope, can_approve=authz.can(user, MODULE, "approve"),
        can_approve_exception=authz.can(user, MODULE, "approve_exception"))


# --- lifecycle transitions ----------------------------------------------------

@router.post("/{quotation_id}/transition", response_model=QuotationDetailOut)
def transition_quotation(
    quotation_id: int,
    payload: TransitionRequest,
    svc: Service,
    authz: Authz,
    user: Annotated[User, Depends(require_permission(MODULE, "read"))],
) -> QuotationDetailOut:
    scope = _scope_for(authz, user)
    # Mỗi chuyển trạng thái tách thành quyền chi tiết riêng (tách hẳn khỏi "sửa nội dung"):
    #   - Khách duyệt (accepted)      → `approve`
    #   - Hủy (cancelled)             → `cancel`
    #   - Gửi / Từ chối / Hết hạn / … → `manage_status` (thao tác trạng thái chung)
    to_status = payload.to_status
    if to_status == STATUS_ACCEPTED:
        if not authz.can(user, MODULE, "approve"):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Bạn không có quyền duyệt báo giá.")
    elif to_status == STATUS_CANCELLED:
        if not authz.can(user, MODULE, "cancel"):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Bạn không có quyền hủy báo giá.")
    elif not authz.can(user, MODULE, "manage_status"):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "Bạn không có quyền thao tác trạng thái báo giá."
        )
    try:
        q = svc.transition(
            quotation_id=quotation_id,
            to_status=payload.to_status,
            scope=scope,
            actor=user,
            cancel_reason=payload.cancel_reason,
        )
    except (QuotationNotFound, QuotationForbidden) as e:
        if isinstance(e, QuotationForbidden) and "duyệt" in str(e):
            raise HTTPException(status.HTTP_403_FORBIDDEN, str(e)) from None
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Không tìm thấy báo giá.") from None
    except QuotationConflict as e:
        raise HTTPException(status.HTTP_409_CONFLICT, str(e)) from None
    except QuotationValidationError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e)) from None
    return _detail(svc, q, scope, can_approve=authz.can(user, MODULE, "approve"),
        can_approve_exception=authz.can(user, MODULE, "approve_exception"))


# --- BG-2: GĐ duyệt "báo giá đặc thù" → mở khóa "gửi khách" --------------------

@router.post("/{quotation_id}/approval", response_model=QuotationDetailOut)
def record_quote_approval(
    quotation_id: int,
    payload: QuoteApprovalIn,
    svc: Service,
    authz: Authz,
    user: Annotated[User, Depends(require_permission(MODULE, "approve_exception"))],
) -> QuotationDetailOut:
    """GĐ DUYỆT / TỪ CHỐI báo giá đặc thù (perm `approve_exception` — CHỈ Giám đốc). Duyệt 'bao phủ' →
    cho 'gửi khách'. Trả về báo giá kèm khối gate cập nhật (người duyệt có quyền → thấy số biên)."""
    scope = _scope_for(authz, user)
    try:
        svc.record_approval(
            quotation_id=quotation_id, decision=payload.decision, note=payload.note,
            scope=scope, actor=user,
        )
        q = svc.get_quotation(quotation_id=quotation_id, scope=scope, actor=user)
    except (QuotationNotFound, QuotationForbidden):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Không tìm thấy báo giá.") from None
    except QuotationValidationError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e)) from None
    return _detail(svc, q, scope, can_approve=authz.can(user, MODULE, "approve"),
        can_approve_exception=authz.can(user, MODULE, "approve_exception"))


@router.get("/{quotation_id}/approvals", response_model=QuoteApprovalListOut)
def list_quote_approvals(
    quotation_id: int,
    svc: Service,
    authz: Authz,
    user: Annotated[User, Depends(require_permission(MODULE, "approve_exception"))],
) -> QuoteApprovalListOut:
    """Lịch sử duyệt/từ chối báo giá đặc thù — chứa số biên/giá vốn nên CHỈ người có quyền duyệt (GĐ)."""
    scope = _scope_for(authz, user)
    try:
        items = svc.list_approvals(quotation_id=quotation_id, scope=scope, actor=user)
    except (QuotationNotFound, QuotationForbidden):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Không tìm thấy báo giá.") from None
    return QuoteApprovalListOut(items=[QuoteApprovalOut.model_validate(a) for a in items])


@router.post("/{quotation_id}/requote", response_model=QuotationDetailOut, status_code=status.HTTP_201_CREATED)
def requote_quotation(
    quotation_id: int,
    svc: Service,
    authz: Authz,
    user: Annotated[User, Depends(require_permission(MODULE, "requote"))],
) -> QuotationDetailOut:
    scope = _scope_for(authz, user)
    try:
        new_v = svc.requote(quotation_id=quotation_id, scope=scope, actor=user)
    except (QuotationNotFound, QuotationForbidden):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Không tìm thấy báo giá.") from None
    except QuotationConflict as e:
        raise HTTPException(status.HTTP_409_CONFLICT, str(e)) from None
    return _detail(svc, new_v, scope, can_approve=authz.can(user, MODULE, "approve"),
        can_approve_exception=authz.can(user, MODULE, "approve_exception"))


# --- PDF đối ngoại ------------------------------------------------------------

@router.get("/{quotation_id}/pdf")
def quotation_pdf(
    quotation_id: int,
    svc: Service,
    authz: Authz,
    user: Annotated[User, Depends(require_permission(MODULE, "export"))],
) -> Response:
    scope = _scope_for(authz, user)
    try:
        q = svc.get_quotation(quotation_id=quotation_id, scope=scope, actor=user)
    except (QuotationNotFound, QuotationForbidden):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Không tìm thấy báo giá.") from None

    ref = svc.customer_display(q)
    pdf_bytes = _render_pdf(q, ref)
    return Response(content=pdf_bytes, media_type="application/pdf")


def _fmt_vnd(value: float | None) -> str:
    if value is None:
        return "—"
    return f"{int(value):,} đ".replace(",", ".")


def _render_pdf(q: Quote, ref) -> bytes:
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

    active_version = None
    for v in q.versions:
        if v.id == q.current_version_id:
            active_version = v
            break

    ver_num = active_version.version_number if active_version else 1
    c.drawString(25 * mm, y, f"Ma: {q.quote_number}  -  Version: {ver_num}")
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

    # Draw Items table
    c.setFont("Helvetica-Bold", 12)
    c.drawString(25 * mm, y, "Danh sach san pham / Pricing breakdown")
    y -= 10 * mm

    # Draw table headers
    c.setFont("Helvetica-Bold", 10)
    c.drawString(25 * mm, y, "STT")
    c.drawString(38 * mm, y, "Ten san pham / Quy cach")
    c.drawRightString(110 * mm, y, "So luong")
    c.drawRightString(135 * mm, y, "Don gia")
    c.drawRightString(160 * mm, y, "VAT %")
    c.drawRightString(width - 25 * mm, y, "Thanh tien")
    y -= 5 * mm
    c.line(25 * mm, y + 2 * mm, width - 25 * mm, y + 2 * mm)

    c.setFont("Helvetica", 10)
    if active_version:
        for idx, item in enumerate(active_version.items, 1):
            c.drawString(25 * mm, y, str(idx))
            c.drawString(38 * mm, y, f"{item.product_name} ({item.product_type})")
            c.drawRightString(110 * mm, y, f"{item.quantity:,}".replace(",", "."))
            c.drawRightString(135 * mm, y, _fmt_vnd(item.unit_price))
            c.drawRightString(160 * mm, y, f"{int(item.vat_percent)}%")
            c.drawRightString(width - 25 * mm, y, _fmt_vnd(item.final_amount))
            y -= 7 * mm

            if item.note:
                c.setFont("Helvetica-Oblique", 8)
                c.drawString(38 * mm, y + 1 * mm, f"Ghi chu: {item.note}")
                c.setFont("Helvetica", 10)
                y -= 5 * mm

    y -= 5 * mm
    c.line(25 * mm, y + 7 * mm, width - 25 * mm, y + 7 * mm)

    # Draw terms & notes if any
    c.setFont("Helvetica-Bold", 11)
    if q.payment_terms:
        c.drawString(25 * mm, y, "Dieu khoan thanh toan:")
        c.setFont("Helvetica", 10)
        c.drawString(75 * mm, y, q.payment_terms)
        y -= 6 * mm
    if q.delivery_terms:
        c.setFont("Helvetica-Bold", 11)
        c.drawString(25 * mm, y, "Dieu khoan giao hang:")
        c.setFont("Helvetica", 10)
        c.drawString(75 * mm, y, q.delivery_terms)
        y -= 6 * mm

    c.setFont("Helvetica-Oblique", 8)
    c.drawString(25 * mm, 15 * mm, "Tai lieu doi ngoai — khong the hien chi tiet gia thanh.")
    c.showPage()
    c.save()
    return buf.getvalue()
