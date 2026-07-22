"""Vật liệu Kho router (module MỚI) — CRUD giấy/mực/bản. Chưa đăng ký main.py (unwired).

Dependency INLINE để không đụng deps.py. MODULE quyền = "kho" (thuộc Kho hàng).
"""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import require_any_permission, require_permission
from ..models.user import User
from ..repositories.vat_lieu_kho_repo import VatLieuKhoRepository
from ..schemas.vat_lieu_kho import (
    ChungLoaiGiayIn, ChungLoaiGiayRow, GiayGiaVersionIn, GiayGiaVersionRow, GiayIn, GiayRow,
    ListOut, VatTuIn, VatTuRow,
)
from ..services.vat_lieu_kho_service import (
    VatLieuKhoDuplicate, VatLieuKhoNotFound, VatLieuKhoService, VatLieuKhoValidationError,
)

router = APIRouter(prefix="/api/vat-lieu-kho", tags=["vat-lieu-kho"])
MODULE = "kho"


def get_service(db: Annotated[Session, Depends(get_db)]) -> VatLieuKhoService:
    return VatLieuKhoService(VatLieuKhoRepository(db))


Service = Annotated[VatLieuKhoService, Depends(get_service)]


def _err(e: Exception):
    if isinstance(e, VatLieuKhoNotFound):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    if isinstance(e, VatLieuKhoDuplicate):
        return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))


def _make_crud(kind: str, InModel, RowModel, path: str):
    # NOTE: `from __future__ import annotations` biến mọi annotation thành CHUỖI. `payload: InModel`
    # thành "InModel" mà FastAPI không resolve được (InModel là biến cục bộ factory) → tưởng query.
    # Nên: bỏ annotation `payload` ở nguồn, gán `__annotations__["payload"] = InModel` (class thật),
    # rồi đăng ký route THỦ CÔNG sau khi gán (decorator chạy lúc def nên không kịp).
    def _list(
        svc: Service,
        # Danh mục THAM CHIẾU (giấy/mực/bản): đọc được nếu có quyền Kho HOẶC Tính giá HOẶC Sản xuất
        # (Tính giá đổ dropdown Giấy; Kế hoạch SX cần đổi giấy cùng chủng loại ở lệnh — không mở Kho).
        _: Annotated[User, Depends(require_any_permission(
            (MODULE, "read"), ("tinh_gia_thanh", "read"), ("san_xuat", "read")))],
        q: str | None = Query(default=None),
        active: bool | None = Query(default=None),
        page: int = Query(default=1, ge=1),
        size: int = Query(default=50, ge=1, le=200),
    ) -> ListOut:
        rows, total = svc.list(kind, q=q, active=active, page=page, size=size)
        return ListOut(items=[RowModel.model_validate(r) for r in rows], total=total, page=page, size=size)

    def _create(payload, svc: Service,
                _: Annotated[User, Depends(require_permission(MODULE, "create"))]):
        try:
            return RowModel.model_validate(svc.create(kind, payload.model_dump(exclude_unset=True)))
        except (VatLieuKhoDuplicate, VatLieuKhoValidationError) as e:
            raise _err(e) from None
    _create.__annotations__["payload"] = InModel

    def _update(item_id: int, payload, svc: Service,
                _: Annotated[User, Depends(require_permission(MODULE, "update"))]):
        try:
            return RowModel.model_validate(svc.update(kind, item_id, payload.model_dump(exclude_unset=True)))
        except (VatLieuKhoNotFound, VatLieuKhoDuplicate, VatLieuKhoValidationError) as e:
            raise _err(e) from None
    _update.__annotations__["payload"] = InModel

    def _delete(item_id: int, svc: Service,
                _: Annotated[User, Depends(require_permission(MODULE, "delete"))]):
        try:
            svc.delete(kind, item_id)
        except VatLieuKhoNotFound as e:
            raise _err(e) from None
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    router.get(f"/{path}", response_model=ListOut, name=f"list_{kind}")(_list)
    router.post(f"/{path}", response_model=RowModel, status_code=status.HTTP_201_CREATED,
                name=f"create_{kind}")(_create)
    router.put(f"/{path}/{{item_id}}", response_model=RowModel, name=f"update_{kind}")(_update)
    router.delete(f"/{path}/{{item_id}}", status_code=status.HTTP_204_NO_CONTENT,
                  response_class=Response, name=f"delete_{kind}")(_delete)


_make_crud("chung_loai_giay", ChungLoaiGiayIn, ChungLoaiGiayRow, "chung-loai-giay")
_make_crud("giay", GiayIn, GiayRow, "giay")
_make_crud("vat_tu", VatTuIn, VatTuRow, "vat-tu-in-an")


# -- Phiên bản giá giấy (lịch sử) — route custom (không theo factory CRUD) --
@router.get("/giay/{giay_id}/versions", response_model=list[GiayGiaVersionRow], name="list_giay_versions")
def list_giay_versions(
    giay_id: int,
    svc: Service,
    _: Annotated[User, Depends(require_permission(MODULE, "read"))],
) -> list[GiayGiaVersionRow]:
    try:
        rows = svc.list_giay_versions(giay_id)
    except VatLieuKhoNotFound as e:
        raise _err(e) from None
    return [GiayGiaVersionRow.model_validate(r) for r in rows]


@router.post("/giay/{giay_id}/versions", response_model=GiayGiaVersionRow,
             status_code=status.HTTP_201_CREATED, name="add_giay_version")
def add_giay_version(
    giay_id: int,
    payload: GiayGiaVersionIn,
    svc: Service,
    user: Annotated[User, Depends(require_permission(MODULE, "update"))],
) -> GiayGiaVersionRow:
    try:
        v = svc.add_giay_version(giay_id, payload.model_dump(), created_by=user.id)
    except (VatLieuKhoNotFound, VatLieuKhoValidationError) as e:
        raise _err(e) from None
    return GiayGiaVersionRow.model_validate(v)
