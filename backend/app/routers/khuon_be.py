"""Khuôn bế router — CRUD danh mục KHAI BÁO nơi lưu trữ khuôn bế.

Dependency INLINE. MODULE quyền RIÊNG = "khuon_be" (tích quyền độc lập trong ma trận).
Chỉ khai báo (mã / tên / khách / số kệ / ngày làm / tình trạng / ghi chú) — khai tay.
"""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import require_permission
from ..models.user import User
from ..repositories.audit_repo import AuditLogRepository
from ..repositories.khuon_be_repo import KhuonBeRepository
from ..schemas.khuon_be import KhuonBeIn, KhuonBeListOut, KhuonBeRow
from ..services.khuon_be_service import (
    KhuonBeDuplicate, KhuonBeNotFound, KhuonBeService, KhuonBeValidationError,
)

router = APIRouter(prefix="/api/khuon-be", tags=["khuon-be"])
MODULE = "khuon_be"


def get_service(db: Annotated[Session, Depends(get_db)]) -> KhuonBeService:
    return KhuonBeService(KhuonBeRepository(db), AuditLogRepository(db))


Service = Annotated[KhuonBeService, Depends(get_service)]


def _err(e: Exception):
    if isinstance(e, KhuonBeNotFound):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    if isinstance(e, KhuonBeDuplicate):
        return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))


@router.get("", response_model=KhuonBeListOut)
def list_items(
    svc: Service,
    _: Annotated[User, Depends(require_permission(MODULE, "read"))],
    q: str | None = Query(default=None),
    active: bool | None = Query(default=None),
    # Tab lọc của màn Khuôn bế (Còn dùng · Hỏng · Trả khách…). Trước 14/08/2026 màn tự lọc trong
    # JS trên toàn bộ danh mục đã tải về; nay bảng chỉ cầm 20 dòng nên việc lọc phải về đây.
    tinh_trang: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=50, ge=1, le=200),
) -> KhuonBeListOut:
    rows, total = svc.list(q=q, active=active, tinh_trang=tinh_trang, page=page, size=size)
    return KhuonBeListOut(
        items=[KhuonBeRow.model_validate(r) for r in rows], total=total, page=page, size=size,
        # `facets` KHÔNG lọc theo `tinh_trang` — tab đang không được chọn vẫn phải khoe số của nó.
        facets=svc.dem_theo_tinh_trang(q=q, active=active),
    )


@router.get("/{item_id}", response_model=KhuonBeRow)
def get_item(item_id: int, svc: Service, _: Annotated[User, Depends(require_permission(MODULE, "read"))]):
    try:
        return KhuonBeRow.model_validate(svc.get(item_id))
    except KhuonBeNotFound as e:
        raise _err(e) from None


@router.post("", response_model=KhuonBeRow, status_code=status.HTTP_201_CREATED)
def create_item(payload: KhuonBeIn, svc: Service, current_user: Annotated[User, Depends(require_permission(MODULE, "create"))]):
    try:
        return KhuonBeRow.model_validate(svc.create(payload.model_dump(exclude_unset=True), created_by=current_user.id))
    except (KhuonBeDuplicate, KhuonBeValidationError) as e:
        raise _err(e) from None


@router.put("/{item_id}", response_model=KhuonBeRow)
def update_item(item_id: int, payload: KhuonBeIn, svc: Service,
                user: Annotated[User, Depends(require_permission(MODULE, "update"))]):
    try:
        return KhuonBeRow.model_validate(svc.update(item_id, payload.model_dump(exclude_unset=True), actor_id=user.id))
    except (KhuonBeNotFound, KhuonBeDuplicate, KhuonBeValidationError) as e:
        raise _err(e) from None


@router.delete("/{item_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
def delete_item(item_id: int, svc: Service,
                user: Annotated[User, Depends(require_permission(MODULE, "delete"))]):
    try:
        svc.delete(item_id, actor_id=user.id)
    except KhuonBeNotFound as e:
        raise _err(e) from None
    return Response(status_code=status.HTTP_204_NO_CONTENT)
