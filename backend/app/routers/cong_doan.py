"""Công đoạn router (module MỚI) — CRUD danh mục. Chưa đăng ký main.py (unwired).

Dependency INLINE (không đụng deps.py). MODULE quyền = "dm_cong_doan".
"""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import require_any_permission, require_permission
from ..models.user import User
from ..repositories.cong_doan_repo import CongDoanRepository
from ..repositories.rbac_repo import DepartmentRepository
from ..schemas.cong_doan import CongDoanIn, CongDoanListOut, CongDoanRow, RefOption, RefOptionListOut
from ..services.cong_doan_service import (
    CongDoanDuplicate, CongDoanNotFound, CongDoanService, CongDoanValidationError,
)

router = APIRouter(prefix="/api/cong-doan", tags=["cong-doan"])
MODULE = "dm_cong_doan"


def get_service(db: Annotated[Session, Depends(get_db)]) -> CongDoanService:
    return CongDoanService(CongDoanRepository(db))


Service = Annotated[CongDoanService, Depends(get_service)]


def _err(e: Exception):
    if isinstance(e, CongDoanNotFound):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    if isinstance(e, CongDoanDuplicate):
        return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))


@router.get("", response_model=CongDoanListOut)
def list_items(
    svc: Service,
    # Danh mục THAM CHIẾU: đọc được nếu có quyền cấu hình Công đoạn HOẶC quyền Tính giá
    # (màn Tính giá cần đổ dropdown Công đoạn mà không phải mở màn cấu hình).
    _: Annotated[User, Depends(require_any_permission((MODULE, "read"), ("tinh_gia_thanh", "read")))],
    q: str | None = Query(default=None),
    nhom: str | None = Query(default=None),
    active: bool | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=50, ge=1, le=200),
) -> CongDoanListOut:
    rows, total = svc.list(q=q, nhom=nhom, active=active, page=page, size=size)
    return CongDoanListOut(items=[CongDoanRow.model_validate(r) for r in rows], total=total, page=page, size=size)


@router.get("/phong-ban", response_model=RefOptionListOut)
def list_phong_ban_options(
    db: Annotated[Session, Depends(get_db)],
    # Đọc được nếu có quyền cấu hình Công đoạn HOẶC Tính giá (đổ dropdown 'Phòng ban phụ trách').
    _: Annotated[User, Depends(require_any_permission((MODULE, "read"), ("tinh_gia_thanh", "read")))],
) -> RefOptionListOut:
    """Phòng ban / tổ cho dropdown 'Phòng ban phụ trách' ở form Công đoạn (khớp field ref: {id, ma, ten}).
    Lọc về khối SẢN XUẤT (§13.1) — chỉ tổ có `la_san_xuat` (tự/tổ tiên); chưa đánh dấu gì → tất cả."""
    depts = DepartmentRepository(db).production_departments()
    return RefOptionListOut(items=[RefOption(id=d.id, ma=d.code, ten=d.name) for d in depts])


@router.get("/{cd_id}", response_model=CongDoanRow)
def get_item(cd_id: int, svc: Service, _: Annotated[User, Depends(require_permission(MODULE, "read"))]):
    try:
        return CongDoanRow.model_validate(svc.get(cd_id))
    except CongDoanNotFound as e:
        raise _err(e) from None


@router.post("", response_model=CongDoanRow, status_code=status.HTTP_201_CREATED)
def create_item(payload: CongDoanIn, svc: Service, _: Annotated[User, Depends(require_permission(MODULE, "create"))]):
    try:
        return CongDoanRow.model_validate(svc.create(payload.model_dump(exclude_unset=True)))
    except (CongDoanDuplicate, CongDoanValidationError) as e:
        raise _err(e) from None


@router.put("/{cd_id}", response_model=CongDoanRow)
def update_item(cd_id: int, payload: CongDoanIn, svc: Service,
                _: Annotated[User, Depends(require_permission(MODULE, "update"))]):
    try:
        return CongDoanRow.model_validate(svc.update(cd_id, payload.model_dump(exclude_unset=True)))
    except (CongDoanNotFound, CongDoanDuplicate, CongDoanValidationError) as e:
        raise _err(e) from None


@router.delete("/{cd_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
def delete_item(cd_id: int, svc: Service, _: Annotated[User, Depends(require_permission(MODULE, "delete"))]):
    try:
        svc.delete(cd_id)
    except CongDoanNotFound as e:
        raise _err(e) from None
    return Response(status_code=status.HTTP_204_NO_CONTENT)
