"""Loại sản phẩm router (module MỚI) — CRUD template. Chưa đăng ký main.py (unwired).

Dependency INLINE (không đụng deps.py). MODULE quyền = "dm_loai_san_pham".
"""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import require_permission
from ..models.user import User
from ..repositories.loai_san_pham_repo import LoaiSanPhamRepository
from ..schemas.loai_san_pham import LoaiSanPhamIn, LoaiSanPhamListOut, LoaiSanPhamRow
from ..services.loai_san_pham_service import (
    LoaiSanPhamDuplicate, LoaiSanPhamNotFound, LoaiSanPhamService, LoaiSanPhamValidationError,
)

router = APIRouter(prefix="/api/loai-san-pham", tags=["loai-san-pham"])
MODULE = "dm_loai_san_pham"


def get_service(db: Annotated[Session, Depends(get_db)]) -> LoaiSanPhamService:
    return LoaiSanPhamService(LoaiSanPhamRepository(db))


Service = Annotated[LoaiSanPhamService, Depends(get_service)]


def _err(e: Exception):
    if isinstance(e, LoaiSanPhamNotFound):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    if isinstance(e, LoaiSanPhamDuplicate):
        return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))


@router.get("", response_model=LoaiSanPhamListOut)
def list_items(
    svc: Service,
    _: Annotated[User, Depends(require_permission(MODULE, "read"))],
    q: str | None = Query(default=None),
    structural_type: str | None = Query(default=None),
    active: bool | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=50, ge=1, le=200),
) -> LoaiSanPhamListOut:
    rows, total = svc.list(q=q, structural_type=structural_type, active=active, page=page, size=size)
    return LoaiSanPhamListOut(items=[LoaiSanPhamRow.model_validate(r) for r in rows],
                             total=total, page=page, size=size)


@router.get("/{sp_id}", response_model=LoaiSanPhamRow)
def get_item(sp_id: int, svc: Service, _: Annotated[User, Depends(require_permission(MODULE, "read"))]):
    try:
        return LoaiSanPhamRow.model_validate(svc.get(sp_id))
    except LoaiSanPhamNotFound as e:
        raise _err(e) from None


@router.post("", response_model=LoaiSanPhamRow, status_code=status.HTTP_201_CREATED)
def create_item(payload: LoaiSanPhamIn, svc: Service,
                _: Annotated[User, Depends(require_permission(MODULE, "create"))]):
    try:
        return LoaiSanPhamRow.model_validate(svc.create(payload.model_dump(exclude_unset=True)))
    except (LoaiSanPhamDuplicate, LoaiSanPhamValidationError) as e:
        raise _err(e) from None


@router.put("/{sp_id}", response_model=LoaiSanPhamRow)
def update_item(sp_id: int, payload: LoaiSanPhamIn, svc: Service,
                _: Annotated[User, Depends(require_permission(MODULE, "update"))]):
    try:
        return LoaiSanPhamRow.model_validate(svc.update(sp_id, payload.model_dump(exclude_unset=True)))
    except (LoaiSanPhamNotFound, LoaiSanPhamDuplicate, LoaiSanPhamValidationError) as e:
        raise _err(e) from None


@router.delete("/{sp_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
def delete_item(sp_id: int, svc: Service, _: Annotated[User, Depends(require_permission(MODULE, "delete"))]):
    try:
        svc.delete(sp_id)
    except LoaiSanPhamNotFound as e:
        raise _err(e) from None
    return Response(status_code=status.HTTP_204_NO_CONTENT)
