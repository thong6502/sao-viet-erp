"""Máy thiết bị router (module MỚI) — CRUD + preview BHR.

Chưa đăng ký vào main.py (unwired) — wiring gom 1 pass sau. Dependency provider khai INLINE
để không đụng deps.py (file dùng chung, session song song đang sửa).
"""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import require_permission
from ..models.user import User
from ..repositories.may_thiet_bi_repo import MayThietBiRepository
from ..schemas.may_thiet_bi import (
    BhrBreakdownOut,
    MayThietBiIn,
    MayThietBiListOut,
    MayThietBiRow,
)
from ..services.may_thiet_bi_service import (
    MayThietBiDuplicate,
    MayThietBiNotFound,
    MayThietBiService,
    MayThietBiValidationError,
    compute_bhr_preview,
)

router = APIRouter(prefix="/api/may-thiet-bi", tags=["may-thiet-bi"])
MODULE = "dm_thiet_bi"


def get_service(db: Annotated[Session, Depends(get_db)]) -> MayThietBiService:
    return MayThietBiService(MayThietBiRepository(db))


Service = Annotated[MayThietBiService, Depends(get_service)]


@router.get("", response_model=MayThietBiListOut)
def list_items(
    svc: Service,
    _: Annotated[User, Depends(require_permission(MODULE, "read"))],
    q: str | None = Query(default=None),
    loai_may: str | None = Query(default=None),
    trang_thai: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=50, ge=1, le=200),
) -> MayThietBiListOut:
    rows, total = svc.list(q=q, loai_may=loai_may, trang_thai=trang_thai, page=page, size=size)
    return MayThietBiListOut(
        items=[MayThietBiRow.model_validate(r) for r in rows], total=total, page=page, size=size
    )


@router.get("/{may_id}", response_model=MayThietBiRow)
def get_item(
    may_id: int,
    svc: Service,
    _: Annotated[User, Depends(require_permission(MODULE, "read"))],
) -> MayThietBiRow:
    try:
        return MayThietBiRow.model_validate(svc.get(may_id))
    except MayThietBiNotFound as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from None


@router.get("/{may_id}/bhr", response_model=BhrBreakdownOut)
def bhr(
    may_id: int,
    svc: Service,
    _: Annotated[User, Depends(require_permission(MODULE, "read"))],
) -> BhrBreakdownOut:
    try:
        return BhrBreakdownOut(**svc.bhr(may_id))
    except MayThietBiNotFound as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from None
    except MayThietBiValidationError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e)) from None


@router.post("/bhr-preview", response_model=BhrBreakdownOut)
def bhr_preview(
    payload: dict,
    _: Annotated[User, Depends(require_permission(MODULE, "read"))],
) -> BhrBreakdownOut:
    """BHR preview từ dữ liệu form (máy CHƯA lưu) — nuôi block xem-trước trong drawer."""
    try:
        return BhrBreakdownOut(**compute_bhr_preview(payload))
    except MayThietBiValidationError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e)) from None
    except (TypeError, ValueError) as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e)) from None


@router.post("", response_model=MayThietBiRow, status_code=status.HTTP_201_CREATED)
def create_item(
    payload: MayThietBiIn,
    svc: Service,
    _: Annotated[User, Depends(require_permission(MODULE, "create"))],
) -> MayThietBiRow:
    try:
        return MayThietBiRow.model_validate(svc.create(payload.model_dump(exclude_unset=True)))
    except MayThietBiDuplicate as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e)) from None
    except MayThietBiValidationError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e)) from None


@router.put("/{may_id}", response_model=MayThietBiRow)
def update_item(
    may_id: int,
    payload: MayThietBiIn,
    svc: Service,
    _: Annotated[User, Depends(require_permission(MODULE, "update"))],
) -> MayThietBiRow:
    try:
        return MayThietBiRow.model_validate(svc.update(may_id, payload.model_dump(exclude_unset=True)))
    except MayThietBiNotFound as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from None
    except MayThietBiDuplicate as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e)) from None
    except MayThietBiValidationError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e)) from None


@router.delete("/{may_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
def delete_item(
    may_id: int,
    svc: Service,
    _: Annotated[User, Depends(require_permission(MODULE, "delete"))],
) -> Response:
    try:
        svc.delete(may_id)
    except MayThietBiNotFound as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from None
    return Response(status_code=status.HTTP_204_NO_CONTENT)
