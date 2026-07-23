"""Router Lệnh sản xuất (LSX) — bàn của bộ phận Kế hoạch sản xuất.

Prefix `/api/lsx`. RBAC MODULE = "san_xuat".

Luồng: Sale bấm "Chuyển xuống sản xuất" (đơn hàng) → đơn rơi vào `/hang-cho` → Kế hoạch mở
`/preview/{order_id}` xem danh sách lệnh DỰ KIẾN (dẫn xuất tại chỗ, chưa ghi DB) → tick dòng →
`POST /tao/{order_id}` sinh lệnh Nháp/Chờ bổ sung → sửa routing/số lượng → đánh dấu Sẵn sàng.
"""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import get_authorization_service, require_permission
from ..models.role import SCOPE_ALL, SCOPE_DEPARTMENT, SCOPE_OWN
from ..models.user import User
from ..realtime import hub
from ..repositories.audit_repo import AuditLogRepository
from ..repositories.document_sequence_repo import DocumentSequenceRepository
from ..repositories.lsx_repo import LsxRepository
from ..repositories.org_scope import dept_subtree_ids
from ..schemas.lsx import (
    HangChoOut,
    LsxActivityItem,
    LsxActivityOut,
    LsxListItem,
    LsxListOut,
    LsxOut,
    LsxUpdateIn,
    PreviewOut,
    RoutingReplaceIn,
    TaoLsxIn,
    TrangThaiIn,
)
from ..services.actor_display import actor_labels
from ..services.lsx_service import (
    LsxConflict,
    LsxNotFound,
    LsxService,
    LsxValidationError,
)
from ..services.rbac_service import AuthorizationService
from ..services.sequence_service import SequenceService

router = APIRouter(prefix="/api/lsx", tags=["lsx"])
MODULE = "san_xuat"
Authz = Annotated[AuthorizationService, Depends(get_authorization_service)]


def _svc(db: Session) -> LsxService:
    return LsxService(
        db,
        LsxRepository(db),
        AuditLogRepository(db),
        SequenceService(DocumentSequenceRepository(db)),
    )


def _map(exc: Exception) -> HTTPException:
    if isinstance(exc, LsxNotFound):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    if isinstance(exc, LsxConflict):
        return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    if isinstance(exc, LsxValidationError):
        return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    raise exc


def _owner_ids_for_scope(db: Session, user: User, authz: AuthorizationService) -> set[int] | None:
    """Tập user-id mà `user` được thấy lệnh theo scope module `san_xuat`. None = thấy TẤT CẢ.

    Lệnh KHÔNG thuộc sale (khác đơn hàng) nên phạm vi tính theo người phụ trách / người tạo lệnh:
    Kế hoạch SX cầm scope `all` → thấy hết; tổ trưởng/thợ scope `own` → chỉ lệnh của mình.
    """
    scope = authz.scope_for(user, MODULE) or SCOPE_OWN
    if scope == SCOPE_ALL:
        return None
    if scope == SCOPE_DEPARTMENT:
        dept_ids = dept_subtree_ids(db, user.department_id)
        if dept_ids:
            ids = db.execute(select(User.id).where(User.department_id.in_(dept_ids))).scalars().all()
            return set(ids) | {user.id}
    return {user.id}


def _guard_scope(db: Session, lsx, user: User, authz: AuthorizationService) -> None:
    owner_ids = _owner_ids_for_scope(db, user, authz)
    if owner_ids is None:
        return
    if lsx.nguoi_phu_trach_id in owner_ids or lsx.created_by in owner_ids:
        return
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy lệnh sản xuất")


def _out(svc: LsxService, lsx) -> LsxOut:
    return LsxOut.model_validate({**lsx.__dict__, **svc.detail_dict(lsx)})


# --- Hàng chờ tiếp nhận -------------------------------------------------------
@router.get("/hang-cho", response_model=HangChoOut)
def hang_cho(
    db: Annotated[Session, Depends(get_db)],
    authz: Authz,
    user: Annotated[User, Depends(require_permission(MODULE, "read"))],
) -> HangChoOut:
    """Đơn Sale đã chuyển xuống SX mà còn dòng chưa lên lệnh. Chỉ người có phạm vi TOÀN BỘ (Kế
    hoạch SX) mới thấy — đơn chưa lên lệnh thì chưa thuộc về ai bên sản xuất."""
    if _owner_ids_for_scope(db, user, authz) is not None:
        return HangChoOut(items=[], total=0)
    items = _svc(db).hang_cho()
    return HangChoOut(items=items, total=len(items))


# --- Xem trước danh sách lệnh dự kiến ----------------------------------------
@router.get("/preview/{order_id}", response_model=PreviewOut)
def preview(
    order_id: int,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(require_permission(MODULE, "read"))],
) -> PreviewOut:
    try:
        return PreviewOut.model_validate(_svc(db).preview(order_id))
    except Exception as exc:
        raise _map(exc)


@router.post("/tao/{order_id}", response_model=LsxListOut, status_code=status.HTTP_201_CREATED)
def tao(
    order_id: int,
    payload: TaoLsxIn,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(require_permission(MODULE, "create"))],
) -> LsxListOut:
    svc = _svc(db)
    try:
        created = svc.tao(order_id=order_id, order_line_ids=payload.order_line_ids, actor=user)
    except Exception as exc:
        raise _map(exc)
    ids = [c.id for c in created]
    rows = [r for r in svc.list_rows(order_id=order_id) if r["id"] in ids]
    # Đơn hàng + hàng chờ nhảy ngay (badge/đếm) — không bắt ai refresh.
    hub.broadcast({"type": "lsx_changed", "order_id": order_id})
    return LsxListOut(items=[LsxListItem.model_validate(r) for r in rows], total=len(rows))


# --- Danh sách / chi tiết -----------------------------------------------------
@router.get("", response_model=LsxListOut)
def list_items(
    db: Annotated[Session, Depends(get_db)],
    authz: Authz,
    user: Annotated[User, Depends(require_permission(MODULE, "read"))],
    order_id: int | None = Query(default=None),
    trang_thai: str | None = Query(default=None),
    q: str | None = Query(default=None),
) -> LsxListOut:
    rows = _svc(db).list_rows(
        order_id=order_id, trang_thai=trang_thai, q=q,
        owner_ids=_owner_ids_for_scope(db, user, authz),
    )
    return LsxListOut(items=[LsxListItem.model_validate(r) for r in rows], total=len(rows))


@router.get("/{lsx_id}", response_model=LsxOut)
def get_item(
    lsx_id: int,
    db: Annotated[Session, Depends(get_db)],
    authz: Authz,
    user: Annotated[User, Depends(require_permission(MODULE, "read"))],
) -> LsxOut:
    svc = _svc(db)
    try:
        lsx = svc.get(lsx_id)
    except Exception as exc:
        raise _map(exc)
    _guard_scope(db, lsx, user, authz)
    return _out(svc, lsx)


@router.put("/{lsx_id}", response_model=LsxOut)
def update_item(
    lsx_id: int,
    payload: LsxUpdateIn,
    db: Annotated[Session, Depends(get_db)],
    authz: Authz,
    user: Annotated[User, Depends(require_permission(MODULE, "update"))],
) -> LsxOut:
    svc = _svc(db)
    try:
        _guard_scope(db, svc.get(lsx_id), user, authz)
        lsx = svc.update(lsx_id=lsx_id, payload=payload, actor=user)
    except Exception as exc:
        raise _map(exc)
    hub.broadcast({"type": "lsx_changed", "order_id": lsx.order_id})
    return _out(svc, lsx)


@router.put("/{lsx_id}/routing", response_model=LsxOut)
def replace_routing(
    lsx_id: int,
    payload: RoutingReplaceIn,
    db: Annotated[Session, Depends(get_db)],
    authz: Authz,
    user: Annotated[User, Depends(require_permission(MODULE, "update"))],
) -> LsxOut:
    """REPLACE-ALL routing của LỆNH — không đụng phiếu tính giá, không ảnh hưởng lệnh khác."""
    svc = _svc(db)
    try:
        _guard_scope(db, svc.get(lsx_id), user, authz)
        lsx = svc.replace_routing(lsx_id=lsx_id, rows_in=payload.cong_doans, actor=user)
    except Exception as exc:
        raise _map(exc)
    hub.broadcast({"type": "lsx_changed", "order_id": lsx.order_id})
    return _out(svc, lsx)


@router.post("/{lsx_id}/trang-thai", response_model=LsxOut)
def set_trang_thai(
    lsx_id: int,
    payload: TrangThaiIn,
    db: Annotated[Session, Depends(get_db)],
    authz: Authz,
    user: Annotated[User, Depends(require_permission(MODULE, "update"))],
) -> LsxOut:
    svc = _svc(db)
    try:
        _guard_scope(db, svc.get(lsx_id), user, authz)
        lsx = svc.set_trang_thai(lsx_id=lsx_id, trang_thai=payload.trang_thai, actor=user)
    except Exception as exc:
        raise _map(exc)
    hub.broadcast({"type": "lsx_changed", "order_id": lsx.order_id})
    return _out(svc, lsx)


@router.delete("/{lsx_id}")
def delete_item(
    lsx_id: int,
    db: Annotated[Session, Depends(get_db)],
    authz: Authz,
    user: Annotated[User, Depends(require_permission(MODULE, "update"))],
) -> dict:
    """Xoá lệnh chưa phát hành → dòng đơn quay lại hàng chờ (thay cho 'hủy lệnh' ở lát này)."""
    svc = _svc(db)
    try:
        _guard_scope(db, svc.get(lsx_id), user, authz)
        order_id = svc.xoa(lsx_id=lsx_id, actor=user)
    except Exception as exc:
        raise _map(exc)
    hub.broadcast({"type": "lsx_changed", "order_id": order_id})
    return {"ok": True}


@router.get("/{lsx_id}/activity", response_model=LsxActivityOut)
def activity(
    lsx_id: int,
    db: Annotated[Session, Depends(get_db)],
    authz: Authz,
    user: Annotated[User, Depends(require_permission(MODULE, "read"))],
) -> LsxActivityOut:
    """Nhật ký của 1 lệnh (ai sửa gì, khi nào) — đọc audit theo target `lsx:{id}`, mới→cũ."""
    svc = _svc(db)
    try:
        _guard_scope(db, svc.get(lsx_id), user, authz)
    except Exception as exc:
        raise _map(exc)
    rows = AuditLogRepository(db).list_by_target(f"lsx:{lsx_id}")
    names = actor_labels(db, {r.actor_user_id for r in rows if r.actor_user_id is not None})
    return LsxActivityOut(items=[
        LsxActivityItem(
            action=r.action,
            actor_name=names.get(r.actor_user_id) if r.actor_user_id else None,
            detail=r.detail,
            at=r.created_at,
        )
        for r in rows
    ])
