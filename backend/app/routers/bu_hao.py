"""Bù hao router — CRUD danh mục bù hao (bảng tra số tờ theo bài in × bậc SL).

Dependency INLINE. MODULE quyền = "dm_cong_doan" (bù hao thuộc cấu hình sản xuất).
"""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import require_permission
from ..models.user import User
from ..repositories.bu_hao_repo import BuHaoRepository
from ..schemas.bu_hao import BuHaoIn, BuHaoListOut, BuHaoRow
from ..services.bu_hao_service import (
    BuHaoDuplicate, BuHaoNotFound, BuHaoService, BuHaoValidationError,
)

router = APIRouter(prefix="/api/bu-hao", tags=["bu-hao"])
MODULE = "dm_cong_doan"


def get_service(db: Annotated[Session, Depends(get_db)]) -> BuHaoService:
    return BuHaoService(BuHaoRepository(db))


Service = Annotated[BuHaoService, Depends(get_service)]


def _err(e: Exception):
    if isinstance(e, BuHaoNotFound):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    if isinstance(e, BuHaoDuplicate):
        return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))


@router.get("", response_model=BuHaoListOut)
def list_items(
    svc: Service,
    _: Annotated[User, Depends(require_permission(MODULE, "read"))],
    q: str | None = Query(default=None),
    truc: str | None = Query(default=None),
    active: bool | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=50, ge=1, le=200),
) -> BuHaoListOut:
    rows, total = svc.list(q=q, truc=truc, active=active, page=page, size=size)
    return BuHaoListOut(items=[BuHaoRow.model_validate(r) for r in rows], total=total, page=page, size=size)


@router.get("/{bh_id}", response_model=BuHaoRow)
def get_item(bh_id: int, svc: Service, _: Annotated[User, Depends(require_permission(MODULE, "read"))]):
    try:
        return BuHaoRow.model_validate(svc.get(bh_id))
    except BuHaoNotFound as e:
        raise _err(e) from None


@router.post("", response_model=BuHaoRow, status_code=status.HTTP_201_CREATED)
def create_item(payload: BuHaoIn, svc: Service, _: Annotated[User, Depends(require_permission(MODULE, "create"))]):
    try:
        return BuHaoRow.model_validate(svc.create(payload.model_dump(exclude_unset=True)))
    except (BuHaoDuplicate, BuHaoValidationError) as e:
        raise _err(e) from None


@router.put("/{bh_id}", response_model=BuHaoRow)
def update_item(bh_id: int, payload: BuHaoIn, svc: Service,
                _: Annotated[User, Depends(require_permission(MODULE, "update"))]):
    try:
        return BuHaoRow.model_validate(svc.update(bh_id, payload.model_dump(exclude_unset=True)))
    except (BuHaoNotFound, BuHaoDuplicate, BuHaoValidationError) as e:
        raise _err(e) from None


@router.delete("/{bh_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
def delete_item(bh_id: int, svc: Service, _: Annotated[User, Depends(require_permission(MODULE, "delete"))]):
    try:
        svc.delete(bh_id)
    except BuHaoNotFound as e:
        raise _err(e) from None
    return Response(status_code=status.HTTP_204_NO_CONTENT)
