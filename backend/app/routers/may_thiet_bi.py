"""Máy thiết bị router (module MỚI) — CRUD + preview BHR.

Chưa đăng ký vào main.py (unwired) — wiring gom 1 pass sau. Dependency provider khai INLINE
để không đụng deps.py (file dùng chung, session song song đang sửa).
"""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import require_any_permission, require_permission
from ..models.user import User
from ..repositories.audit_repo import AuditLogRepository
from ..repositories.may_thiet_bi_repo import MayThietBiRepository
from ..models.may_thiet_bi import MayThietBi
from ..schemas.may_thiet_bi import (
    MayThietBiIn,
    MayThietBiListOut,
    MayThietBiRow,
    NhomMayIn,
    NhomMayListOut,
    NhomMayRow,
    TrangThaiMayOut,
    TrangThaiMayRow,
)
from ..services.may_thiet_bi_service import (
    MayThietBiDuplicate,
    MayThietBiNotFound,
    MayThietBiService,
    MayThietBiValidationError,
    NhomMayService,
)
from ..services.may_trang_thai import trang_thai_may

router = APIRouter(prefix="/api/may-thiet-bi", tags=["may-thiet-bi"])
MODULE = "dm_thiet_bi"


def get_service(db: Annotated[Session, Depends(get_db)]) -> MayThietBiService:
    return MayThietBiService(MayThietBiRepository(db), AuditLogRepository(db))


Service = Annotated[MayThietBiService, Depends(get_service)]


@router.get("", response_model=MayThietBiListOut)
def list_items(
    svc: Service,
    # Danh mục THAM CHIẾU: đọc được nếu có quyền cấu hình Máy HOẶC quyền Tính giá
    # (màn Tính giá cần đổ dropdown Máy mà không phải mở màn cấu hình).
    _: Annotated[User, Depends(require_any_permission((MODULE, "read"), ("tinh_gia_thanh", "read")))],
    q: str | None = Query(default=None),
    loai_may: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=50, ge=1, le=200),
) -> MayThietBiListOut:
    rows, total = svc.list(q=q, loai_may=loai_may, page=page, size=size)
    return MayThietBiListOut(
        items=[MayThietBiRow.model_validate(r) for r in rows], total=total, page=page, size=size,
        # `facets` KHÔNG lọc theo `loai_may` — tab đang không được chọn vẫn phải khoe số của nó.
        facets=svc.dem_theo_loai(q=q),
    )


@router.get("/trang-thai", response_model=TrangThaiMayOut)
def trang_thai(
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[User, Depends(require_permission(MODULE, "read"))],
) -> TrangThaiMayOut:
    """Máy nào đang nằm / đang chạy NGAY LÚC NÀY — cột "Trạng thái" của màn Thiết bị.

    ⚠️ Phải khai TRƯỚC `GET /{may_id}`: FastAPI khớp route theo thứ tự, để sau thì "trang-thai"
    rơi vào `{may_id}` và ăn 422 vì không ép được sang int.
    """
    may_ids = [int(i) for i in db.execute(select(MayThietBi.id)).scalars()]
    return TrangThaiMayOut(
        items={k: TrangThaiMayRow(**v) for k, v in trang_thai_may(db, may_ids).items()}
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


@router.post("", response_model=MayThietBiRow, status_code=status.HTTP_201_CREATED)
def create_item(
    payload: MayThietBiIn,
    svc: Service,
    user: Annotated[User, Depends(require_permission(MODULE, "create"))],
) -> MayThietBiRow:
    try:
        return MayThietBiRow.model_validate(
            svc.create(payload.model_dump(exclude_unset=True), actor_id=user.id))
    except MayThietBiDuplicate as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e)) from None
    except MayThietBiValidationError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e)) from None


@router.put("/{may_id}", response_model=MayThietBiRow)
def update_item(
    may_id: int,
    payload: MayThietBiIn,
    svc: Service,
    user: Annotated[User, Depends(require_permission(MODULE, "update"))],
) -> MayThietBiRow:
    try:
        return MayThietBiRow.model_validate(
            svc.update(may_id, payload.model_dump(exclude_unset=True), actor_id=user.id))
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
    user: Annotated[User, Depends(require_permission(MODULE, "delete"))],
) -> Response:
    try:
        svc.delete(may_id, actor_id=user.id)
    except MayThietBiNotFound as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from None
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --- Danh mục NHÓM MÁY (/api/nhom-may) ---------------------------------------
# Router RIÊNG nhưng CÙNG module quyền `dm_thiet_bi` với màn Máy — nhờ vậy ai khai được máy thì
# thêm/xoá được nhóm ngay tại ô, không có cảnh thấy nút rồi ăn 403 (bài học từ tab "Loại nghỉ").

nhom_may_router = APIRouter(prefix="/api/nhom-may", tags=["may-thiet-bi"])


def get_nhom_may_service(db: Annotated[Session, Depends(get_db)]) -> NhomMayService:
    return NhomMayService(db)


NhomService = Annotated[NhomMayService, Depends(get_nhom_may_service)]


@nhom_may_router.get("", response_model=NhomMayListOut)
def list_nhom_may(
    svc: NhomService,
    # Đọc được nếu có quyền cấu hình Máy HOẶC Tính giá — cùng lý do với danh sách máy ở trên.
    _: Annotated[User, Depends(require_any_permission((MODULE, "read"), ("tinh_gia_thanh", "read")))],
) -> NhomMayListOut:
    rows = svc.list()
    return NhomMayListOut(items=[NhomMayRow.model_validate(r) for r in rows], total=len(rows))


@nhom_may_router.post("", response_model=NhomMayRow, status_code=status.HTTP_201_CREATED)
def create_nhom_may(
    payload: NhomMayIn,
    svc: NhomService,
    _: Annotated[User, Depends(require_permission(MODULE, "create"))],
) -> NhomMayRow:
    try:
        return NhomMayRow.model_validate(svc.create(payload.ten))
    except MayThietBiDuplicate as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e)) from None
    except MayThietBiValidationError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e)) from None


@nhom_may_router.delete("/{nhom_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
def delete_nhom_may(
    nhom_id: int,
    svc: NhomService,
    _: Annotated[User, Depends(require_permission(MODULE, "delete"))],
) -> Response:
    try:
        svc.delete(nhom_id)
    except MayThietBiNotFound as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from None
    except MayThietBiValidationError as e:
        # 409 chứ không 422: dữ liệu gửi lên hợp lệ, chỉ là TRẠNG THÁI không cho xoá.
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e)) from None
    return Response(status_code=status.HTTP_204_NO_CONTENT)
