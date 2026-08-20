"""Router nhãn công đoạn (bước lệnh) — bản sao của phần nhãn ở `routers/customers.py`.

Prefix `/api/cong-doan-tags`. RBAC MODULE = "san_xuat" (bước thuộc kế hoạch/thực thi sản xuất).
Dùng chung cho bước LSX (`buoc_loai=lsx`) và bước Bài ghép 2 (`buoc_loai=bai_ghep`).
"""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import require_permission
from ..models.user import User
from ..repositories.audit_repo import AuditLogRepository
from ..repositories.cong_doan_tag_repo import CongDoanTagRepository
from ..schemas.cong_doan_tag import (
    KhoNhanOut,
    KhoNhanRow,
    KhoNhanXoaOut,
    TagIn,
    TagOut,
    TagsOut,
)
from ..services.cong_doan_tag_service import (
    CongDoanTagNotFound,
    CongDoanTagService,
    CongDoanTagValidationError,
)

router = APIRouter(prefix="/api/cong-doan-tags", tags=["cong-doan-tags"])
MODULE = "san_xuat"


def _svc(db: Session) -> CongDoanTagService:
    return CongDoanTagService(db, CongDoanTagRepository(db), AuditLogRepository(db))


def _map(exc: Exception) -> HTTPException:
    if isinstance(exc, CongDoanTagNotFound):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    if isinstance(exc, CongDoanTagValidationError):
        return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    raise exc


# --- Kho nhãn dùng chung ------------------------------------------------------
# ⚠️ Ba route `/kho*` phải đứng TRƯỚC `/{buoc_loai}/{buoc_id}`: cùng số đoạn nên để sau thì
# "kho" bị nuốt thành `buoc_loai`. Cùng lý do ở router khách hàng.
@router.get("/kho", response_model=KhoNhanOut)
def list_kho_nhan(
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(require_permission(MODULE, "read"))],
) -> KhoNhanOut:
    return KhoNhanOut(items=[KhoNhanRow(**r) for r in _svc(db).list_kho_nhan()])


@router.post("/kho", response_model=KhoNhanRow, status_code=201)
def them_nhan_kho(
    payload: TagIn,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(require_permission(MODULE, "update"))],
) -> KhoNhanRow:
    try:
        row = _svc(db).them_nhan_kho(label=payload.label, actor=user)
    except (CongDoanTagValidationError, CongDoanTagNotFound) as exc:
        raise _map(exc) from exc
    return KhoNhanRow(id=row.id, label=row.label, so_buoc=0)


@router.delete("/kho/{nhan_id}", response_model=KhoNhanXoaOut)
def xoa_nhan_kho(
    nhan_id: int,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(require_permission(MODULE, "update"))],
) -> KhoNhanXoaOut:
    try:
        so = _svc(db).xoa_nhan_kho(nhan_id=nhan_id, actor=user)
    except (CongDoanTagValidationError, CongDoanTagNotFound) as exc:
        raise _map(exc) from exc
    return KhoNhanXoaOut(so_buoc_da_go=so)


# --- Nhãn đã gán cho một bước -------------------------------------------------
@router.get("/{buoc_loai}/{buoc_id}", response_model=TagsOut)
def list_tags(
    buoc_loai: str,
    buoc_id: int,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(require_permission(MODULE, "read"))],
) -> TagsOut:
    try:
        items = _svc(db).list_tags(buoc_loai=buoc_loai, buoc_id=buoc_id)
    except (CongDoanTagValidationError, CongDoanTagNotFound) as exc:
        raise _map(exc) from exc
    return TagsOut(items=[TagOut.model_validate(t) for t in items])


@router.post("/{buoc_loai}/{buoc_id}", response_model=TagOut, status_code=201)
def add_tag(
    buoc_loai: str,
    buoc_id: int,
    payload: TagIn,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(require_permission(MODULE, "update"))],
) -> TagOut:
    try:
        tag = _svc(db).add_tag(buoc_loai=buoc_loai, buoc_id=buoc_id, label=payload.label, actor=user)
    except (CongDoanTagValidationError, CongDoanTagNotFound) as exc:
        raise _map(exc) from exc
    return TagOut.model_validate(tag)


@router.delete("/{buoc_loai}/{buoc_id}/{tag_id}", status_code=204)
def delete_tag(
    buoc_loai: str,
    buoc_id: int,
    tag_id: int,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(require_permission(MODULE, "update"))],
):
    try:
        _svc(db).remove_tag(buoc_loai=buoc_loai, buoc_id=buoc_id, tag_id=tag_id, actor=user)
    except (CongDoanTagValidationError, CongDoanTagNotFound) as exc:
        raise _map(exc) from exc
