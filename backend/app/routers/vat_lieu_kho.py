"""Danh mục Giấy & Vật tư khác — DANH MỤC GỐC của mặt hàng (Kho + NCC đều trỏ về đây).

BA danh mục trên một router, cả ba sinh từ `routers/catalog_base.make_catalog_router`
(`/chung-loai-giay`, `/giay`, `/vat-tu-in-an`). Ngoài ra router phơi ba cửa dùng chung:
  · `GET /mat-hang`                      — tìm gộp Giấy + Vật tư khác (picker mặt hàng)
  · `GET /mat-hang/{loai}/{id}/don-vi`   — đơn vị gốc + mọi đơn vị đổi được (dropdown ĐVT)
  · `GET|POST /giay/{id}/versions`       — lịch sử giá giấy

Dependency INLINE để không đụng deps.py.
"""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
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
    MotDanhMucVatLieu, VatLieuKhoNotFound, VatLieuKhoService, VatLieuKhoValidationError,
)
from .catalog_base import loi_http, make_catalog_router

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


def _mot(kind: str):
    """Provider cho MỘT trong ba danh mục — ghim sẵn `kind` (xem `MotDanhMucVatLieu`)."""
    def provider(db: Annotated[Session, Depends(get_db)]) -> MotDanhMucVatLieu:
        return MotDanhMucVatLieu(get_service(db), kind)
    return Annotated[MotDanhMucVatLieu, Depends(provider)]


def _rows_kem_don_vi(svc: MotDanhMucVatLieu, objs: list, RowModel) -> list:
    """Dòng + TÊN đơn vị tính (mã → tên đọc được, 1 truy vấn cho cả trang)."""
    rows = [RowModel.model_validate(o) for o in objs]
    svc.gan_ten_don_vi(rows)
    return rows


def _khai(kind: str, InModel, RowModel, path: str, *, kem_don_vi: bool):
    mod = MODULE_BY_KIND[kind]
    make_catalog_router(
        router, goc=f"/{path}", ten=kind, ServiceDep=_mot(kind), module=mod,
        doc=require_any_permission((mod, "read"), *_DOC_CHUNG),
        InModel=InModel, RowModel=RowModel,
        # Phong bì phân trang GẮN ĐÚNG kiểu dòng của danh mục này → OpenAPI ra `GiayRow[]` chứ
        # không phải `any[]` (xem `schemas/vat_lieu_kho.ListOut`).
        ListModel=ListOut[RowModel],
        dung_rows=((lambda svc, objs: _rows_kem_don_vi(svc, objs, RowModel))
                   if kem_don_vi else None),
        # Không mở `/ma-goi-y`: mã ở ba danh mục này là chữ có nghĩa (`COUCHE`, `MUC-CMYK`,
        # `COUCHE-300-65x86`), không phải một dãy số ⇒ không có "mã kế tiếp" nào đúng.
    )


_khai("chung_loai_giay", ChungLoaiGiayIn, ChungLoaiGiayRow, "chung-loai-giay", kem_don_vi=False)
_khai("giay", GiayIn, GiayRow, "giay", kem_don_vi=True)
_khai("vat_tu", VatTuIn, VatTuRow, "vat-tu-in-an", kem_don_vi=True)


# -- MẶT HÀNG GỐC: hai cửa Kho + NCC dùng để chọn hàng và chọn đơn vị --
#
# Quyền rộng hơn CRUD (thêm `thu_mua`): người lập đề nghị kho và người khai bảng giá NCC đều phải
# CHỌN được mặt hàng, nhưng không được sửa danh mục. Chỉ trả mã · tên · đơn vị — không có giá.
_doc_mat_hang = require_any_permission(
    ("dm_giay", "read"), ("dm_vat_tu", "read"), ("kho", "read"), ("thu_mua", "read"),
    ("tinh_gia_thanh", "read"), ("san_xuat", "read"))


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
        raise loi_http(e) from None


# -- Phiên bản giá giấy (lịch sử) — route custom, KHÔNG theo khuôn danh mục --
@router.get("/giay/{giay_id}/versions", response_model=list[GiayGiaVersionRow],
            name="list_giay_versions")
def list_giay_versions(
    giay_id: int,
    svc: Service,
    _: Annotated[User, Depends(require_permission(MODULE, "read"))],
) -> list[GiayGiaVersionRow]:
    try:
        rows = svc.list_giay_versions(giay_id)
    except VatLieuKhoNotFound as e:
        raise loi_http(e) from None
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
        raise loi_http(e) from None
    return GiayGiaVersionRow.model_validate(v)
