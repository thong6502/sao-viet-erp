"""Đơn vị & quy đổi router — CRUD danh mục đơn vị đo + thử một phép đổi.

Dependency INLINE (bám `routers/bu_hao.py`). MODULE quyền = "dm_cong_doan": đơn vị là cấu hình sản
xuất, ai khai được công đoạn/bù hao thì khai được đơn vị — không đẻ ô quyền mới cho một danh mục.
"""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import require_permission
from ..models.user import User
from ..repositories.audit_repo import AuditLogRepository
from ..repositories.don_vi_do_repo import DonViDoRepository
from ..schemas.don_vi_do import (
    DonViDoIn, DonViDoListOut, DonViDoRow, HoListOut, QuyDoiIn, QuyDoiOut,
)
from ..services.don_vi_do_service import (
    DonViDoDuplicate, DonViDoNotFound, DonViDoService, DonViDoValidationError,
)
from ..services.quy_doi_service import don_vi_map, doi_theo_quy_cach

router = APIRouter(prefix="/api/don-vi", tags=["don-vi"])
MODULE = "dm_cong_doan"


def get_service(db: Annotated[Session, Depends(get_db)]) -> DonViDoService:
    return DonViDoService(DonViDoRepository(db), AuditLogRepository(db))


Service = Annotated[DonViDoService, Depends(get_service)]


def _err(e: Exception):
    if isinstance(e, DonViDoNotFound):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    if isinstance(e, DonViDoDuplicate):
        return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))


def _row(svc: DonViDoService, obj) -> DonViDoRow:
    row = DonViDoRow.model_validate(obj)
    row.canh_bao = svc.canh_bao(obj)
    return row


@router.get("", response_model=DonViDoListOut)
def list_items(
    svc: Service,
    _: Annotated[User, Depends(require_permission(MODULE, "read"))],
    q: str | None = Query(default=None),
    ho: str | None = Query(default=None),
    active: bool | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=50, ge=1, le=200),
) -> DonViDoListOut:
    rows, total = svc.list(q=q, ho=ho, active=active, page=page, size=size)
    return DonViDoListOut(
        items=[_row(svc, r) for r in rows], total=total, page=page, size=size,
    )


@router.get("/ho", response_model=HoListOut)
def list_ho(svc: Service, _: Annotated[User, Depends(require_permission(MODULE, "read"))]) -> HoListOut:
    return HoListOut(items=svc.ho_goi_y())


@router.post("/thu", response_model=QuyDoiOut)
def thu_quy_doi(
    payload: QuyDoiIn,
    svc: Service,
    _: Annotated[User, Depends(require_permission(MODULE, "read"))],
) -> QuyDoiOut:
    """Thử một phép đổi — trả kèm DIỄN GIẢI cách tính, hoặc nói rõ thiếu gì (không đoán)."""
    dvs = don_vi_map(svc.repo.all_active())
    kq = doi_theo_quy_cach(payload.gia_tri, payload.tu, payload.den, payload.quy_cach, dvs)
    return QuyDoiOut(**kq)


@router.get("/{dv_id}", response_model=DonViDoRow)
def get_item(dv_id: int, svc: Service,
             _: Annotated[User, Depends(require_permission(MODULE, "read"))]) -> DonViDoRow:
    try:
        return _row(svc, svc.get(dv_id))
    except DonViDoNotFound as e:
        raise _err(e) from None


@router.post("", response_model=DonViDoRow, status_code=status.HTTP_201_CREATED)
def create_item(payload: DonViDoIn, svc: Service,
                current_user: Annotated[User, Depends(require_permission(MODULE, "create"))]) -> DonViDoRow:
    try:
        obj = svc.create(payload.model_dump(exclude_unset=True), actor_id=current_user.id)
        return _row(svc, obj)
    except (DonViDoDuplicate, DonViDoValidationError) as e:
        raise _err(e) from None


@router.put("/{dv_id}", response_model=DonViDoRow)
def update_item(dv_id: int, payload: DonViDoIn, svc: Service,
                current_user: Annotated[User, Depends(require_permission(MODULE, "update"))]) -> DonViDoRow:
    try:
        obj = svc.update(dv_id, payload.model_dump(exclude_unset=True), actor_id=current_user.id)
        return _row(svc, obj)
    except (DonViDoNotFound, DonViDoDuplicate, DonViDoValidationError) as e:
        raise _err(e) from None


@router.delete("/{dv_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
def delete_item(dv_id: int, svc: Service,
                current_user: Annotated[User, Depends(require_permission(MODULE, "delete"))]):
    try:
        svc.delete(dv_id, actor_id=current_user.id)
    except DonViDoNotFound as e:
        raise _err(e) from None
    return Response(status_code=status.HTTP_204_NO_CONTENT)
