"""Vật liệu Kho router (module MỚI) — CRUD giấy/mực/bản. Chưa đăng ký main.py (unwired).

Dependency INLINE để không đụng deps.py. MODULE quyền = "kho" (thuộc Kho hàng).
"""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import require_permission
from ..models.user import User
from ..repositories.vat_lieu_kho_repo import VatLieuKhoRepository
from ..schemas.vat_lieu_kho import (
    BanKemIn, BanKemRow, GiayIn, GiayRow, ListOut, MucIn, MucRow,
)
from ..services.vat_lieu_kho_service import (
    VatLieuKhoDuplicate, VatLieuKhoNotFound, VatLieuKhoService, VatLieuKhoValidationError,
)

router = APIRouter(prefix="/api/vat-lieu-kho", tags=["vat-lieu-kho"])
MODULE = "kho"


def get_service(db: Annotated[Session, Depends(get_db)]) -> VatLieuKhoService:
    return VatLieuKhoService(VatLieuKhoRepository(db))


Service = Annotated[VatLieuKhoService, Depends(get_service)]
_ROW = {"giay": GiayRow, "muc": MucRow, "ban": BanKemRow}


def _err(e: Exception):
    if isinstance(e, VatLieuKhoNotFound):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    if isinstance(e, VatLieuKhoDuplicate):
        return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))


def _make_crud(kind: str, InModel, RowModel, path: str):
    @router.get(f"/{path}", response_model=ListOut, name=f"list_{kind}")
    def _list(
        svc: Service,
        _: Annotated[User, Depends(require_permission(MODULE, "read"))],
        q: str | None = Query(default=None),
        active: bool | None = Query(default=None),
        page: int = Query(default=1, ge=1),
        size: int = Query(default=50, ge=1, le=200),
    ) -> ListOut:
        rows, total = svc.list(kind, q=q, active=active, page=page, size=size)
        return ListOut(items=[RowModel.model_validate(r) for r in rows], total=total, page=page, size=size)

    @router.post(f"/{path}", response_model=RowModel, status_code=status.HTTP_201_CREATED, name=f"create_{kind}")
    def _create(
        payload: InModel,
        svc: Service,
        _: Annotated[User, Depends(require_permission(MODULE, "create"))],
    ):
        try:
            return RowModel.model_validate(svc.create(kind, payload.model_dump(exclude_unset=True)))
        except (VatLieuKhoDuplicate, VatLieuKhoValidationError) as e:
            raise _err(e) from None

    @router.put(f"/{path}/{{item_id}}", response_model=RowModel, name=f"update_{kind}")
    def _update(
        item_id: int,
        payload: InModel,
        svc: Service,
        _: Annotated[User, Depends(require_permission(MODULE, "update"))],
    ):
        try:
            return RowModel.model_validate(svc.update(kind, item_id, payload.model_dump(exclude_unset=True)))
        except (VatLieuKhoNotFound, VatLieuKhoDuplicate, VatLieuKhoValidationError) as e:
            raise _err(e) from None

    @router.delete(f"/{path}/{{item_id}}", status_code=status.HTTP_204_NO_CONTENT,
                   response_class=Response, name=f"delete_{kind}")
    def _delete(
        item_id: int,
        svc: Service,
        _: Annotated[User, Depends(require_permission(MODULE, "delete"))],
    ):
        try:
            svc.delete(kind, item_id)
        except VatLieuKhoNotFound as e:
            raise _err(e) from None
        return Response(status_code=status.HTTP_204_NO_CONTENT)


_make_crud("giay", GiayIn, GiayRow, "giay")
_make_crud("muc", MucIn, MucRow, "muc")
_make_crud("ban", BanKemIn, BanKemRow, "ban-kem")
