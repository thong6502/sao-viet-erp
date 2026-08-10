"""Kho hàng router — CRUD danh mục KHAI BÁO kho.

Dependency INLINE. MODULE quyền = "dm_kho_hang" — quyền RIÊNG, tách khỏi `kho`: dựng danh sách
kho là việc cấu hình, chạy nhập/xuất hàng ngày là việc khác. ĐỌC thì vẫn mở cho `kho` (mọi màn
nghiệp vụ đều phải chọn kho trong dropdown).
Chỉ khai báo kho (mã / tên / vị trí / ghi chú); vận hành nhập/xuất/tồn ở router khác.
"""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import require_any_permission, require_permission
from ..models.user import User
from ..repositories.audit_repo import AuditLogRepository
from ..repositories.kho_hang_repo import KhoHangRepository
from ..schemas.kho_hang import KhoHangIn, KhoHangListOut, KhoHangRow
from ..services.kho_hang_service import (
    KhoHangDuplicate, KhoHangInUse, KhoHangNotFound, KhoHangService, KhoHangValidationError,
)

router = APIRouter(prefix="/api/kho", tags=["kho"])
MODULE = "dm_kho_hang"
# Đọc danh sách kho: người khai (module này) + mọi vai làm nghiệp vụ kho / mua hàng / sản xuất —
# họ phải chọn kho ở phiếu, không thì dropdown rỗng mà không hiểu vì sao.
_doc_kho = require_any_permission(
    (MODULE, "read"), ("kho", "read"), ("thu_mua", "read"), ("san_xuat", "read"))


def get_service(db: Annotated[Session, Depends(get_db)]) -> KhoHangService:
    return KhoHangService(KhoHangRepository(db), AuditLogRepository(db))


Service = Annotated[KhoHangService, Depends(get_service)]


def _err(e: Exception):
    if isinstance(e, KhoHangNotFound):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    if isinstance(e, (KhoHangDuplicate, KhoHangInUse)):
        return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))


@router.get("", response_model=KhoHangListOut)
def list_items(
    svc: Service,
    _: Annotated[User, Depends(_doc_kho)],
    q: str | None = Query(default=None),
    active: bool | None = Query(default=None),   # FE 'Khai báo kho' tự truyền active=true (xóa mềm)
    page: int = Query(default=1, ge=1),
    size: int = Query(default=50, ge=1, le=200),
) -> KhoHangListOut:
    rows, total = svc.list(q=q, active=active, page=page, size=size)
    return KhoHangListOut(items=[KhoHangRow.model_validate(r) for r in rows], total=total, page=page, size=size)


@router.get("/{kho_id}", response_model=KhoHangRow)
def get_item(kho_id: int, svc: Service, _: Annotated[User, Depends(_doc_kho)]):
    try:
        return KhoHangRow.model_validate(svc.get(kho_id))
    except KhoHangNotFound as e:
        raise _err(e) from None


@router.post("", response_model=KhoHangRow, status_code=status.HTTP_201_CREATED)
def create_item(payload: KhoHangIn, svc: Service, current_user: Annotated[User, Depends(require_permission(MODULE, "create"))]):
    try:
        return KhoHangRow.model_validate(svc.create(payload.model_dump(exclude_unset=True), created_by=current_user.id))
    except (KhoHangDuplicate, KhoHangValidationError) as e:
        raise _err(e) from None


@router.put("/{kho_id}", response_model=KhoHangRow)
def update_item(kho_id: int, payload: KhoHangIn, svc: Service,
                user: Annotated[User, Depends(require_permission(MODULE, "update"))]):
    try:
        return KhoHangRow.model_validate(svc.update(kho_id, payload.model_dump(exclude_unset=True), actor_id=user.id))
    except (KhoHangNotFound, KhoHangDuplicate, KhoHangValidationError) as e:
        raise _err(e) from None


@router.get("/{kho_id}/delete-check")
def delete_check(kho_id: int, svc: Service, _: Annotated[User, Depends(require_permission(MODULE, "delete"))]):
    """Soi kho trước khi xóa: liệt kê lý do chặn (còn tồn / phiếu chờ ghi sổ / đề nghị dở)."""
    try:
        blockers = svc.delete_blockers(kho_id)
    except KhoHangNotFound as e:
        raise _err(e) from None
    return {"can_delete": not blockers, "blockers": blockers}


@router.delete("/{kho_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
def delete_item(kho_id: int, svc: Service,
                user: Annotated[User, Depends(require_permission(MODULE, "delete"))]):
    try:
        svc.delete(kho_id, actor_id=user.id)
    except (KhoHangNotFound, KhoHangInUse) as e:
        raise _err(e) from None
    return Response(status_code=status.HTTP_204_NO_CONTENT)
