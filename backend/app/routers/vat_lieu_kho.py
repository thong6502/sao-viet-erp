"""Danh mục Giấy & Vật tư khác — DANH MỤC GỐC của mặt hàng (Kho + NCC đều trỏ về đây).

Ngoài CRUD ba danh mục, router này phơi hai cửa dùng chung:
  · `GET /mat-hang`                      — tìm gộp Giấy + Vật tư khác (picker mặt hàng)
  · `GET /mat-hang/{loai}/{id}/don-vi`   — đơn vị gốc + mọi đơn vị đổi được (dropdown ĐVT)

Dependency INLINE để không đụng deps.py. MODULE quyền = "kho" (thuộc Kho hàng).
"""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import require_any_permission, require_permission
from ..models.user import User
from ..repositories.audit_repo import AuditLogRepository
from ..repositories.don_vi_do_repo import DonViDoRepository
from ..repositories.vat_lieu_kho_repo import VatLieuKhoRepository
from ..schemas.vat_lieu_kho import (
    ChungLoaiGiayIn, ChungLoaiGiayRow, DonViCuaMatHangOut, GiayGiaVersionIn, GiayGiaVersionRow,
    GiayIn, GiayRow, ListOut, MatHangRow, VatTuIn, VatTuRow,
)
from ..services.vat_lieu_kho_service import (
    VatLieuKhoDuplicate, VatLieuKhoNotFound, VatLieuKhoService, VatLieuKhoValidationError,
)

router = APIRouter(prefix="/api/vat-lieu-kho", tags=["vat-lieu-kho"])

# MỘT MÀN = MỘT QUYỀN. Ba danh mục ở router này là ba màn riêng trong menu nên ba module riêng —
# KHÔNG dùng chung `kho` như trước (kho hàng là chứng từ nhập/xuất + tồn; đây là danh mục khai
# hàng, kèm đơn giá giấy → hai việc khác nhau, thường hai người khác nhau).
MODULE_BY_KIND = {
    "chung_loai_giay": "dm_chung_loai_giay",
    "giay": "dm_giay",
    "vat_tu": "dm_vat_tu",
}
MODULE = MODULE_BY_KIND["giay"]   # dùng cho các route giá giấy bên dưới

# Ai ĐỌC được danh mục: người khai (3 module trên) + kho (lập phiếu) + tính giá (dropdown giấy) +
# sản xuất (đổi giấy cùng chủng loại ở lệnh). Rộng vì chỉ là tra cứu; GHI thì đúng module của màn.
_DOC_CHUNG = (
    ("kho", "read"), ("tinh_gia_thanh", "read"), ("san_xuat", "read"),
)


def get_service(db: Annotated[Session, Depends(get_db)]) -> VatLieuKhoService:
    return VatLieuKhoService(
        VatLieuKhoRepository(db), DonViDoRepository(db), AuditLogRepository(db),
    )


Service = Annotated[VatLieuKhoService, Depends(get_service)]


def _err(e: Exception):
    if isinstance(e, VatLieuKhoNotFound):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    if isinstance(e, VatLieuKhoDuplicate):
        return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))


def _make_crud(kind: str, InModel, RowModel, path: str):
    mod = MODULE_BY_KIND[kind]
    doc = require_any_permission((mod, "read"), *_DOC_CHUNG)
    req_create = require_permission(mod, "create")
    req_update = require_permission(mod, "update")
    req_delete = require_permission(mod, "delete")

    def _list(
        svc: Service,
        _=Depends(doc),
        q: str | None = Query(default=None),
        active: bool | None = Query(default=None),
        page: int = Query(default=1, ge=1),
        size: int = Query(default=50, ge=1, le=200),
    ) -> ListOut:
        rows, total = svc.list(kind, q=q, active=active, page=page, size=size)
        items = [RowModel.model_validate(r) for r in rows]
        if kind in ("giay", "vat_tu"):
            svc.gan_ten_don_vi(items)      # mã → tên đọc được, 1 truy vấn cho cả trang
        return ListOut(items=items, total=total, page=page, size=size)
    _list.__annotations__["_"] = User

    def _create(payload, svc: Service, user=Depends(req_create)):
        try:
            return RowModel.model_validate(
                svc.create(kind, payload.model_dump(exclude_unset=True), actor_id=user.id))
        except (VatLieuKhoDuplicate, VatLieuKhoValidationError) as e:
            raise _err(e) from None
    _create.__annotations__["payload"] = InModel
    _create.__annotations__["user"] = User

    def _update(item_id: int, payload, svc: Service, user=Depends(req_update)):
        try:
            return RowModel.model_validate(
                svc.update(kind, item_id, payload.model_dump(exclude_unset=True),
                           actor_id=user.id))
        except (VatLieuKhoNotFound, VatLieuKhoDuplicate, VatLieuKhoValidationError) as e:
            raise _err(e) from None
    _update.__annotations__["payload"] = InModel
    _update.__annotations__["user"] = User

    def _delete(item_id: int, svc: Service, user=Depends(req_delete)):
        try:
            svc.delete(kind, item_id, actor_id=user.id)
        except VatLieuKhoNotFound as e:
            raise _err(e) from None
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    _delete.__annotations__["user"] = User

    router.get(f"/{path}", response_model=ListOut, name=f"list_{kind}")(_list)
    router.post(f"/{path}", response_model=RowModel, status_code=status.HTTP_201_CREATED,
                name=f"create_{kind}")(_create)
    router.put(f"/{path}/{{item_id}}", response_model=RowModel, name=f"update_{kind}")(_update)
    router.delete(f"/{path}/{{item_id}}", status_code=status.HTTP_204_NO_CONTENT,
                  response_class=Response, name=f"delete_{kind}")(_delete)


_make_crud("chung_loai_giay", ChungLoaiGiayIn, ChungLoaiGiayRow, "chung-loai-giay")
_make_crud("giay", GiayIn, GiayRow, "giay")
_make_crud("vat_tu", VatTuIn, VatTuRow, "vat-tu-in-an")


# -- MẶT HÀNG GỐC: hai cửa Kho + NCC dùng để chọn hàng và chọn đơn vị --
#
# Quyền rộng hơn CRUD: người lập đề nghị kho/YCMH và người khai bảng giá NCC đều phải CHỌN được
# mặt hàng, nhưng không được sửa danh mục. Chỉ trả mã · tên · đơn vị — không có giá.
_doc_mat_hang = require_any_permission(
    ("dm_giay", "read"), ("dm_vat_tu", "read"), ("kho", "read"), ("thu_mua", "read"),
    ("yeu_cau_mua_hang", "read"), ("tinh_gia_thanh", "read"), ("san_xuat", "read"))


@router.get("/mat-hang", response_model=list[MatHangRow], name="tim_mat_hang")
def tim_mat_hang(
    svc: Service,
    _: Annotated[User, Depends(_doc_mat_hang)],
    q: str | None = Query(default=None),
    size: int = Query(default=20, ge=1, le=50),
) -> list[MatHangRow]:
    """Tìm gộp Giấy + Vật tư khác. Thay `GET /api/kho/de-nghi/vat-tu` (đọc bảng `materials` cũ)."""
    return [MatHangRow(**r) for r in svc.tim_mat_hang(q=q, size=size)]


@router.get("/mat-hang/{hang_loai}/{hang_id}/don-vi", response_model=DonViCuaMatHangOut,
            name="don_vi_cua_mat_hang")
def don_vi_cua_mat_hang(
    hang_loai: str,
    hang_id: int,
    svc: Service,
    _: Annotated[User, Depends(_doc_mat_hang)],
) -> DonViCuaMatHangOut:
    """Đơn vị gốc + mọi đơn vị đổi được với nó, TÍNH THEO CHÍNH MẶT HÀNG.

    Giấy có khổ + định lượng nên thấy cả tờ/ram/m²; hoá chất chỉ khai kg thì chỉ thấy kg/g/tấn.
    Chưa khai đơn vị gốc → `ds` rỗng kèm `ly_do` để UI khoá ô và chỉ đường về danh mục.
    """
    try:
        return DonViCuaMatHangOut(**svc.don_vi_cua_mat_hang(hang_loai, hang_id))
    except (VatLieuKhoNotFound, VatLieuKhoValidationError) as e:
        raise _err(e) from None


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
