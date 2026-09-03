"""Báo giá (Quotation / Quote) routes — spec-09-bao-gia.
"""
from __future__ import annotations

import asyncio
import io
import json
from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    File,
    Header,
    HTTPException,
    Query,
    Request,
    Response,
    UploadFile,
    status,
)
from fastapi.responses import StreamingResponse
from sqlalchemy import select

from ..db import SessionLocal
from ..deps import (
    get_authorization_service,
    get_quotation_service,
    require_permission,
)
from ..realtime import hub
from ..repositories.user_repo import UserRepository
from ..security import decode_access_token
from ..services.auth_service import AuthError, AuthService
from ..services.pdf_font import DAM, THUONG, cat_vua, dang_ky_font
from ..models.quotation import (
    DEFAULT_TERMS,
    QUOTE_STATUSES,
    STATUS_CANCELLED,
    Quote,
    QuoteVersion,
)
from ..models.user import User
from ..schemas.quotation import (
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
    QuoteActivityItem,
    QuoteActivityOut,
    QuoteAttachmentOut,
    QuoteAttachmentsOut,
    RequoteRequest,
    TransitionRequest,
    VersionRow,
    QuoteItemOut,
)
from ..services.quotation_service import (
    QuotationConflict,
    QuotationForbidden,
    QuotationLocked,
    QuotationNotFound,
    QuotationService,
    QuotationValidationError,
)
from ..services.quotation_state import TRANSITIONS
from ..services.rbac_service import AuthorizationService
from ..storage import get_storage, key_from_url, make_key, url_from_key

router = APIRouter(prefix="/api/quotations", tags=["quotations"])

MODULE = "bao_gia"

Service = Annotated[QuotationService, Depends(get_quotation_service)]
Authz = Annotated[AuthorizationService, Depends(get_authorization_service)]

STATUS_LABELS = {
    # 7 trạng thái nghiệp vụ (redesign-bao-gia §3) — bám đúng chữ chủ đầu tư chốt.
    "draft": "Nháp",
    "pending_approval": "Chờ duyệt",   # đặc thù đã "Trình duyệt", chờ Giám đốc Kinh doanh
    "approved": "Đã duyệt",             # GĐ KD duyệt xong, CHỜ sale gửi khách (tách duyệt/gửi)
    "sent": "Đã gửi khách",             # sale tự gửi (tách khỏi "duyệt")
    "accepted": "Khách hàng đồng ý",
    "rejected": "Bị từ chối",   # khách từ chối HOẶC GĐ/TP từ chối đặc thù (phân biệt bằng banner/nhật ký)
    "expired": "Hết hiệu lực",
    "converted_to_order": "Đã lên đơn",
    "cancelled": "Hủy báo giá",
    # Trạng thái riêng của PHIÊN BẢN (không phải header) — pill lịch sử phiên bản dùng chung enum này.
    "locked": "Đã khóa",
    "superseded": "Đã thay thế",
}


def _scope_for(authz: AuthorizationService, user: User) -> str:
    return authz.scope_for(user, MODULE) or "own"


# "Tạo phiên bản mới" (requote) CHỈ khi báo giá BỊ TỪ CHỐI (khách từ chối HOẶC GĐ/TP từ chối đặc
# thù — cả hai đều status `rejected`) → sale sửa lại + trình duyệt/gửi lại. `change_order` KHÔNG
# phải transition state-machine nên gắn tay ở đây để FE hiện nút. KHỚP với svc.requote.
_REQUOTE_FROM = {"rejected"}


def _allowed_transitions(current_status: str) -> list[str]:
    trans = [to for (frm, to) in TRANSITIONS if frm == current_status]
    if current_status in _REQUOTE_FROM:
        trans.append("change_order")
    return trans


def _row(
    q: Quote,
    customer_name: str | None,
    user_names: dict[int, str] | None = None,
) -> QuotationRow:
    active_version = None
    for v in q.versions:
        if v.id == q.current_version_id:
            active_version = v
            break

    items = list(active_version.items) if active_version else []

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

        for item in active_version.items:
            items_out.append(
                QuoteItemOut(
                    id=item.id,
                    line_no=item.line_no,
                    po_code=item.po_code,
                    product_type=item.product_type,
                    product_name=item.product_name,
                    product_spec_text=item.product_spec_text,
                    dien_giai=item.dien_giai,
                    nhom=item.nhom,   # nhãn gộp dòng khi in cho khách
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
                    accepted=bool(item.accepted),
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
                total_cost=int(v.total_cost_snapshot) if v.total_cost_snapshot is not None else None,
                subtotal=int(v.subtotal_amount) if v.subtotal_amount is not None else None,
                discount=int(v.discount_amount) if v.discount_amount is not None else None,
                created_at=v.created_at,
                change_reason=v.change_reason,
            )
        )

    salesperson_name = (
        svc.user_names({q.salesperson_id}).get(q.salesperson_id) if q.salesperson_id else None
    )
    # Đơn hàng bán đã lập từ báo giá này (đơn đã hủy nhả chỗ → không tính) — để FE liên kết/ẩn nút Tạo đơn.
    from ..models.order import STATUS_CANCELLED as _ORDER_CANCELLED, Order as _Order

    linked_order = svc.quotations.db.execute(
        select(_Order)
        .where(_Order.quotation_id == q.id, _Order.status != _ORDER_CANCELLED)
        .order_by(_Order.id.desc())
        .limit(1)
    ).scalars().first()
    _contact = svc.effective_contact(q)
    return QuotationDetailOut(
        id=q.id,
        code=q.quote_number,
        version=active_version.version_number if active_version else 1,
        salesperson_id=q.salesperson_id,
        salesperson_name=salesperson_name,
        customer_id=q.customer_id,
        customer=customer,
        phieu_tinh_gia_id=q.phieu_tinh_gia_id,
        phieu_tinh_gia_ma=svc.phieu_tinh_gia_ref(q)["ma"],
        valid_until=q.valid_until,
        status=q.status,
        cancel_reason=q.cancel_reason,
        terms_text=q.terms_text or DEFAULT_TERMS,
        delivery_address=q.delivery_address,
        contact_name_snapshot=_contact["name"],
        contact_phone_snapshot=_contact["phone"],
        contact_title_snapshot=_contact["title"],
        contact_email_snapshot=_contact["email"],
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
        order_id=linked_order.id if linked_order else None,
        order_no=linked_order.order_no if linked_order else None,
        **_gate_fields(svc, q, can_approve_exception),
    )


def _gate_fields(svc: QuotationService, q: Quote, can_see_numbers: bool = True) -> dict:
    """Khối 'báo giá đặc thù' cho detail. Số markup (`markup_pct`, % trên GIÁ VỐN) HIỆN cho mọi vai
    đọc được báo giá: NV Sales tự gõ markup khi soạn nên không còn giấu con số (redesign-bao-gia §10,
    cập nhật sau P7). Giữ tham số cũ để không phải sửa toàn bộ call-site."""
    del can_see_numbers  # không còn strip theo vai
    return svc.quote_gate(q)


# --- enums + Tính giá picker (SEAM-13) ----------------------------------------

@router.get("/enums", response_model=QuotationEnumsOut)
def quotation_enums(
    _: Annotated[User, Depends(require_permission(MODULE, "read"))],
) -> QuotationEnumsOut:
    return QuotationEnumsOut(
        statuses=[
            EnumOption(value=v, label=STATUS_LABELS.get(v, v))
            for v in (*QUOTE_STATUSES, "locked", "superseded")
        ]
    )


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

    # Bulk map cho hiển thị 2 tầng: tên người phụ trách
    user_ids: set[int] = {r.salesperson_id for r in rows if r.salesperson_id}
    user_names = svc.user_names(user_ids)

    return QuotationListOut(
        items=[_row(r, names.get(r.id), user_names) for r in rows],
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


@router.get("/pending-approval-count")
def pending_approval_count(
    svc: Service,
    authz: Authz,
    user: Annotated[User, Depends(require_permission(MODULE, "read"))],
) -> dict:
    """Badge nav 'Báo giá in ấn' = số báo giá 'Chờ duyệt' trong phạm vi — CHỈ ai có quyền duyệt
    đặc thù mới có số (người khác = 0). Sidebar gọi để hiển thị con số 'chờ tôi duyệt'."""
    scope = _scope_for(authz, user)
    can_approve = authz.can(user, MODULE, "approve_exception")
    return {"count": svc.pending_approval_count(scope=scope, actor=user, can_approve=can_approve)}


# --- Real-time luồng gửi duyệt (SSE) — CLAUDE.md "gửi nội bộ = real-time" ------

@router.get("/notify-summary")
def notify_summary(
    svc: Service,
    authz: Authz,
    user: Annotated[User, Depends(require_permission(MODULE, "read"))],
) -> dict:
    """Số nuôi badge/toast real-time (SSE snapshot khi connect + REST fallback khi có event):
    `pending_approval_count` (chờ TÔI duyệt) + `my_decided_unseen` (quyết định cho báo giá của TÔI
    chưa xem)."""
    scope = _scope_for(authz, user)
    can_approve = authz.can(user, MODULE, "approve_exception")
    return svc.notify_summary(scope=scope, actor=user, can_approve=can_approve)


@router.post("/decisions/seen")
def mark_decisions_seen(
    svc: Service,
    _: Annotated[User, Depends(require_permission(MODULE, "read"))],
) -> dict:
    """Người soạn xác nhận đã xem các quyết định duyệt/từ chối → đóng badge/toast phía Sale."""
    svc.mark_decisions_seen(actor=_)
    return {"ok": True}


def _authenticate_sse(token: str | None) -> int:
    """Xác thực bearer token cho SSE mà KHÔNG giữ session request-scoped (stream sống lâu — 200 kết
    nối giữ session sẽ cạn pool). Mở session ngắn, validate, đóng ngay; trả user_id."""
    unauth = HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated",
                           headers={"WWW-Authenticate": "Bearer"})
    if not token:
        raise unauth
    claims = decode_access_token(token)
    if claims is None:
        raise unauth
    db = SessionLocal()
    try:
        user = AuthService(UserRepository(db)).user_from_token_subject(claims.get("sub"))
    except AuthError:
        raise unauth from None
    finally:
        db.close()
    if claims.get("tv") != user.token_version or not user.is_active:
        raise unauth
    return user.id


@router.get("/events")
async def quote_events(
    request: Request,
    access_token: Annotated[str | None, Query()] = None,
    authorization: Annotated[str | None, Header()] = None,
) -> StreamingResponse:
    """Kênh SSE đẩy sự kiện luồng gửi duyệt (in-process, 1 worker). Client dùng fetch-reader gắn
    `Authorization: Bearer` (EventSource gốc không set được header) — cũng nhận `?access_token=` để
    dự phòng. Sự kiện chỉ là tín hiệu nhẹ (`quote_decision`, `quote_pending_changed`); số chính xác
    lấy qua `/notify-summary` để không giữ DB suốt stream."""
    token = access_token
    if not token and authorization and authorization.lower().startswith("bearer "):
        token = authorization[7:]
    user_id = _authenticate_sse(token)
    queue = hub.subscribe(user_id)

    async def stream():
        try:
            yield ": connected\n\n"
            while True:
                if await request.is_disconnected():
                    break
                try:
                    evt = await asyncio.wait_for(queue.get(), timeout=20.0)
                except asyncio.TimeoutError:
                    yield ": ping\n\n"   # heartbeat giữ kết nối sống qua proxy
                    continue
                yield f"data: {json.dumps(evt, ensure_ascii=False)}\n\n"
        finally:
            hub.unsubscribe(user_id, queue)

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",   # nginx: tắt buffering cho stream này
            "Connection": "keep-alive",
        },
    )


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
            margin_percent=payload.margin_percent,
            valid_until=payload.valid_until,
            terms_text=payload.terms_text,
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


@router.post("/resync-from-ptg/{phieu_tinh_gia_id}")
def resync_quote_from_ptg(
    phieu_tinh_gia_id: int,
    svc: Service,
    authz: Authz,
    # Đồng bộ = sửa báo giá theo phiếu tính giá mới → cần quyền SỬA báo giá (gộp P8).
    user: Annotated[User, Depends(require_permission(MODULE, "update"))],
) -> dict:
    """PTG đổi số → đồng bộ sang báo giá đang hiệu lực (Phương án A). Nháp = cập nhật tại chỗ;
    đã chốt = tạo phiên bản mới. Trả `{quote_id, quote_number, mode}` để màn PTG điều hướng + báo."""
    scope = _scope_for(authz, user)
    try:
        quote, mode = svc.resync_from_ptg(
            phieu_tinh_gia_id=phieu_tinh_gia_id, scope=scope, actor=user
        )
    except (QuotationNotFound, QuotationForbidden):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Không tìm thấy báo giá.") from None
    except QuotationValidationError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e)) from None
    except QuotationConflict as e:
        raise HTTPException(status.HTTP_409_CONFLICT, str(e)) from None
    return {"quote_id": quote.id, "quote_number": quote.quote_number, "mode": mode}


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
            terms_text=payload.terms_text,
            customer_note=payload.customer_note,
            internal_note=payload.internal_note,
            delivery_address=payload.delivery_address,
            contact_name_snapshot=payload.contact_name_snapshot,
            contact_phone_snapshot=payload.contact_phone_snapshot,
            contact_title_snapshot=payload.contact_title_snapshot,
            contact_email_snapshot=payload.contact_email_snapshot,
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
    # Vòng đời báo giá (gửi khách · ghi nhận Khách đồng ý/từ chối · hủy · hết hạn) là thao tác THƯỜNG:
    # ai SỬA được báo giá thì làm được — KHÔNG tách quyền chi tiết vụn (chủ đầu tư chốt P8). Riêng báo giá
    # ĐẶC THÙ vẫn bị chặn: phải TRÌNH DUYỆT (service) + chỉ approve_exception mới duyệt (record_approval).
    if not authz.can(user, MODULE, "update"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Bạn không có quyền thao tác báo giá.")
    try:
        q = svc.transition(
            quotation_id=quotation_id,
            to_status=payload.to_status,
            scope=scope,
            actor=user,
            cancel_reason=payload.cancel_reason,
            accepted_item_ids=payload.accepted_item_ids,
        )
    except (QuotationNotFound, QuotationForbidden) as e:
        if isinstance(e, QuotationForbidden) and "duyệt" in str(e):
            raise HTTPException(status.HTTP_403_FORBIDDEN, str(e)) from None
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Không tìm thấy báo giá.") from None
    except QuotationConflict as e:
        raise HTTPException(status.HTTP_409_CONFLICT, str(e)) from None
    except QuotationValidationError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e)) from None
    # Real-time: TRÌNH DUYỆT (thêm vào 'chờ duyệt') hoặc HỦY (rời 'chờ duyệt') → báo người duyệt
    # ngay (họ tự refetch 'chờ tôi duyệt'; badge nhảy + toast khi số tăng).
    if payload.to_status in ("pending_approval", "cancelled"):
        hub.broadcast({"type": "quote_pending_changed", "code": q.quote_number})
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
    # Real-time: báo NGƯỜI SOẠN kết quả duyệt/từ chối NGAY (toast + badge); và báo người duyệt danh
    # sách 'chờ tôi duyệt' đã đổi (báo giá vừa rời khỏi hàng chờ).
    if q.salesperson_id:
        hub.publish(q.salesperson_id, {
            "type": "quote_decision", "quote_id": q.id,
            "code": q.quote_number, "decision": payload.decision,
        })
    hub.broadcast({"type": "quote_pending_changed", "code": q.quote_number})
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
    payload: RequoteRequest,
    svc: Service,
    authz: Authz,
    # Tạo bản mới = thao tác thường: ai SỬA được báo giá thì làm được (gộp vào `update`, P8).
    user: Annotated[User, Depends(require_permission(MODULE, "update"))],
) -> QuotationDetailOut:
    scope = _scope_for(authz, user)
    try:
        new_v = svc.requote(
            quotation_id=quotation_id, scope=scope, actor=user,
            change_reason=payload.change_reason,
        )
    except (QuotationNotFound, QuotationForbidden):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Không tìm thấy báo giá.") from None
    except QuotationValidationError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e)) from None
    except QuotationConflict as e:
        raise HTTPException(status.HTTP_409_CONFLICT, str(e)) from None
    return _detail(svc, new_v, scope, can_approve=authz.can(user, MODULE, "approve"),
        can_approve_exception=authz.can(user, MODULE, "approve_exception"))


@router.get("/{quotation_id}/activity", response_model=QuoteActivityOut)
def quotation_activity(
    quotation_id: int,
    svc: Service,
    authz: Authz,
    user: Annotated[User, Depends(require_permission(MODULE, "read"))],
) -> QuoteActivityOut:
    """Feed Hoạt động — nhật ký tương tác THẬT (ai làm gì) của báo giá này."""
    scope = _scope_for(authz, user)
    try:
        rows = svc.activity(quotation_id=quotation_id, scope=scope, actor=user)
    except (QuotationNotFound, QuotationForbidden):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Không tìm thấy báo giá.") from None
    return QuoteActivityOut(items=[QuoteActivityItem(**r) for r in rows])


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
    """Bảng báo giá A4 gửi khách — TIẾNG VIỆT CÓ DẤU.

    Bản trước bỏ dấu toàn bộ (`_ascii`, gỡ 02/09/2026) vì font mặc định Helvetica của ReportLab
    không có glyph chữ có dấu. Chủ dự án bác: đây là giấy gửi ra ngoài mang tên khách và tên sản
    phẩm, "Cong ty TNHH An Phat" / "Hop thuoc 10 vi" là sai chính tả tên riêng chứ không phải
    viết tắt. Nay nhúng DejaVu Sans qua `services/pdf_font.py` (dùng chung với phiếu công nghệ).

    Ký hiệu tiền "đ" của `_fmt_vnd` cũng nằm ngoài Helvetica — trước đây nó đi thẳng vào
    `drawRightString` KHÔNG qua `_ascii`, nên cột Đơn giá / Thành tiền in ra ô vuông thiếu glyph.
    Đổi font là hết luôn lỗi đó.

    KHÔNG có bản nghiêng trong repo ⇒ dòng "Ghi chú" của từng dòng hàng dùng chữ THƯỜNG cỡ nhỏ
    thay cho `Helvetica-Oblique`: thà chữ đứng có dấu còn hơn chữ nghiêng mất dấu.

    Hai lỗi BÀY BIỆN thấy trên bản in mẫu lúc nghiệm thu đổi font, sửa cùng lượt: dòng hàng đầu
    tiên vẽ ĐÈ lên gạch ngang dưới tiêu đề cột, và tên sản phẩm dài chạy đè lên cột Số lượng /
    Đơn giá (bản cũ không cắt, không xuống dòng). Đây là bản in gửi khách nên hai lỗi đó làm hỏng
    tờ giấy y như việc bỏ dấu.
    """
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.pdfbase.pdfmetrics import stringWidth
    from reportlab.pdfgen import canvas

    dang_ky_font()

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    width, height = A4
    y = height - 30 * mm

    c.setFont(DAM, 18)
    c.drawString(25 * mm, y, "BẢNG BÁO GIÁ")
    y -= 10 * mm
    c.setFont(THUONG, 11)

    active_version = None
    for v in q.versions:
        if v.id == q.current_version_id:
            active_version = v
            break

    c.drawString(25 * mm, y, f"Số báo giá: {q.quote_number}")
    y -= 7 * mm
    if ref is not None:
        c.drawString(25 * mm, y, f"Khách hàng: {ref.name}")
        y -= 7 * mm
        if ref.tax_code:
            c.drawString(25 * mm, y, f"MST: {ref.tax_code}")
            y -= 7 * mm
    if q.valid_until is not None:
        c.drawString(25 * mm, y, f"Hiệu lực đến: {q.valid_until.isoformat()}")
        y -= 10 * mm

    # Draw Items table
    c.setFont(DAM, 12)
    c.drawString(25 * mm, y, "Chi tiết báo giá")
    y -= 10 * mm

    # Draw table headers
    c.setFont(DAM, 10)
    c.drawString(25 * mm, y, "STT")
    c.drawString(38 * mm, y, "Tên sản phẩm / Quy cách")
    c.drawRightString(110 * mm, y, "Số lượng")
    c.drawRightString(135 * mm, y, "Đơn giá")
    c.drawRightString(160 * mm, y, "VAT %")
    c.drawRightString(width - 25 * mm, y, "Thành tiền")
    y -= 5 * mm
    c.line(25 * mm, y + 2 * mm, width - 25 * mm, y + 2 * mm)
    # Chừa dòng đầu tiên xuống dưới gạch ngang: `y` đang là chân chữ tiêu đề cột, vẽ dòng hàng ở
    # đúng đó thì chữ nằm ĐÈ lên vạch (thấy trên bản in mẫu 02/09/2026).
    y -= 4 * mm

    c.setFont(THUONG, 10)
    if active_version:
        for idx, item in enumerate(active_version.items, 1):
            c.drawString(25 * mm, y, str(idx))
            # Cột Tên bắt đầu ở 38mm, cột Số lượng CANH PHẢI ở 110mm — mép trái của nó phụ thuộc
            # con số dài bao nhiêu ("1.000" khác "1.000.000"), nên bề rộng còn lại cho tên phải
            # tính theo TỪNG DÒNG chứ không chốt một hằng số. Chừa 2mm khe giữa hai cột.
            so_luong = f"{item.quantity:,}".replace(",", ".")
            rong_ten = 110 * mm - stringWidth(so_luong, THUONG, 10) - 38 * mm - 2 * mm
            c.drawString(38 * mm, y, cat_vua(f"{item.product_name} ({item.product_type})",
                                             rong_ten, THUONG, 10))
            c.drawRightString(110 * mm, y, so_luong)
            c.drawRightString(135 * mm, y, _fmt_vnd(item.unit_price))
            c.drawRightString(160 * mm, y, f"{int(item.vat_percent)}%")
            c.drawRightString(width - 25 * mm, y, _fmt_vnd(item.final_amount))
            y -= 7 * mm

            if item.note:
                c.setFont(THUONG, 8)
                # Ghi chú chạy hết bề ngang khung (không có cột nào bên phải nó ở dòng này) —
                # cắt theo mép phải 25mm để không tràn ra ngoài lề giấy.
                c.drawString(38 * mm, y + 1 * mm,
                             cat_vua(f"Ghi chú: {item.note}", width - 25 * mm - 38 * mm,
                                     THUONG, 8))
                c.setFont(THUONG, 10)
                y -= 5 * mm

    y -= 5 * mm
    c.line(25 * mm, y + 7 * mm, width - 25 * mm, y + 7 * mm)

    # Điều khoản — mỗi dòng của `terms_text` = 1 điều khoản, đánh số 1..N như bản in trên màn hình.
    lines = [ln.strip() for ln in (q.terms_text or DEFAULT_TERMS).splitlines() if ln.strip()]
    if lines:
        c.setFont(DAM, 11)
        c.drawString(25 * mm, y, "Điều khoản:")
        y -= 6 * mm
        c.setFont(THUONG, 10)
        for idx, ln in enumerate(lines, 1):
            c.drawString(30 * mm, y, f"{idx}. {ln}")
            y -= 5 * mm

    c.showPage()
    c.save()
    return buf.getvalue()


# --- Tài liệu đính kèm (NỘI BỘ) -----------------------------------------------
# File khách gửi / mẫu thiết kế / ảnh tham khảo — neo vào báo giá, KHÔNG in ra bản gửi khách.
# Lưu qua storage (đọc lại qua /api/files/bao-gia/... có kiểm quyền `bao_gia`), mẫu = đính kèm KH.

_BAO_GIA_SUBDIR = "bao-gia"
_MAX_ATTACH_BYTES = 25 * 1024 * 1024   # 25MB/tệp (chặn ở cả FE lẫn BE)


def _quote_404():
    return HTTPException(status.HTTP_404_NOT_FOUND, "Không tìm thấy báo giá.")


@router.get("/{quotation_id}/attachments", response_model=QuoteAttachmentsOut)
def list_quote_attachments(
    quotation_id: int,
    svc: Service,
    authz: Authz,
    user: Annotated[User, Depends(require_permission(MODULE, "read"))],
) -> QuoteAttachmentsOut:
    try:
        items = svc.list_attachments(
            quotation_id=quotation_id, scope=_scope_for(authz, user), actor=user
        )
    except (QuotationNotFound, QuotationForbidden):
        raise _quote_404() from None
    return QuoteAttachmentsOut(items=[QuoteAttachmentOut.model_validate(a) for a in items])


@router.post("/{quotation_id}/attachments", response_model=QuoteAttachmentOut, status_code=201)
def upload_quote_attachment(
    quotation_id: int,
    svc: Service,
    authz: Authz,
    user: Annotated[User, Depends(require_permission(MODULE, "update"))],
    file: UploadFile = File(...),
) -> QuoteAttachmentOut:
    scope = _scope_for(authz, user)
    # Kiểm quyền truy cập + trạng thái TRƯỚC khi ghi file (né ghi rác cho phiếu ngoài phạm vi / đã hủy).
    try:
        quote = svc.get_quotation(quotation_id=quotation_id, scope=scope, actor=user)
    except (QuotationNotFound, QuotationForbidden):
        raise _quote_404() from None
    if quote.status == STATUS_CANCELLED:
        raise HTTPException(status.HTTP_409_CONFLICT, "Báo giá đã hủy — không đính kèm tài liệu được.")

    data = file.file.read()
    if not data:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Tệp rỗng.")
    if len(data) > _MAX_ATTACH_BYTES:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "Tệp vượt quá 25MB.")

    key, safe = make_key(_BAO_GIA_SUBDIR, quotation_id, file.filename)
    get_storage().save(key, data, file.content_type)
    try:
        att = svc.add_attachment(
            quotation_id=quotation_id, scope=scope, actor=user,
            file_name=safe, file_url=url_from_key(key), file_type=file.content_type,
        )
    except (QuotationNotFound, QuotationForbidden):
        get_storage().delete(key)
        raise _quote_404() from None
    except QuotationLocked as exc:
        get_storage().delete(key)
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from None
    return QuoteAttachmentOut.model_validate(att)


@router.delete("/{quotation_id}/attachments/{attachment_id}", status_code=204)
def delete_quote_attachment(
    quotation_id: int,
    attachment_id: int,
    svc: Service,
    authz: Authz,
    user: Annotated[User, Depends(require_permission(MODULE, "update"))],
):
    try:
        file_url = svc.delete_attachment(
            quotation_id=quotation_id, attachment_id=attachment_id,
            scope=_scope_for(authz, user), actor=user,
        )
    except (QuotationNotFound, QuotationForbidden):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Không tìm thấy tài liệu.") from None
    except QuotationLocked as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from None
    # Dọn object trong storage (best-effort) — xóa row mới là việc chính.
    key = key_from_url(file_url)
    if key:
        get_storage().delete(key)
