"""Danh mục Tiêu chí KCS — service CRUD (validate cong_doan_ids có thật).

Thân CRUD dùng chung ở `services/catalog_base.CatalogService`; ở đây chỉ còn luật riêng.
"""
from __future__ import annotations

from ..repositories.san_xuat_kcs_tieu_chi_repo import SanXuatKcsTieuChiRepository
from .catalog_base import (
    CatalogDuplicate, CatalogError, CatalogNotFound, CatalogService, CatalogValidationError,
)


class SanXuatKcsTieuChiError(CatalogError):
    pass


class SanXuatKcsTieuChiValidationError(SanXuatKcsTieuChiError, CatalogValidationError):
    pass


class SanXuatKcsTieuChiDuplicate(SanXuatKcsTieuChiError, CatalogDuplicate):
    pass


class SanXuatKcsTieuChiNotFound(SanXuatKcsTieuChiError, CatalogNotFound):
    pass


class SanXuatKcsTieuChiService(CatalogService):
    LOAI = "san_xuat_kcs_tieu_chi"
    MA_TU_SINH = True       # mã `KM####` do server cấp, UI không có ô nhập mã
    E_NOT_FOUND, E_DUPLICATE, E_VALIDATION = (
        SanXuatKcsTieuChiNotFound, SanXuatKcsTieuChiDuplicate, SanXuatKcsTieuChiValidationError,
    )
    MSG_NOT_FOUND = "Không tìm thấy hạng mục kiểm."
    MSG_DUPLICATE = "Mã đã tồn tại."

    def __init__(self, repo: SanXuatKcsTieuChiRepository, audit=None) -> None:
        super().__init__(repo, audit)

    def _validate(self, data: dict, obj=None) -> None:
        ten = (data.get("ten") or (obj.ten if obj is not None else "") or "").strip()
        if not ten:
            raise SanXuatKcsTieuChiValidationError("Tên hạng mục kiểm không được trống.")
        # PATCH .../active chỉ gửi một khoá `active` — lấy công đoạn hiện có làm nền, đừng đọc
        # thành "chuyển hạng mục sang công đoạn rỗng" (cùng bẫy đã vá ở `_sau_gan` bản M2M cũ).
        cd = data.get("cong_doan_id", obj.cong_doan_id if obj is not None else None)
        if not cd:
            raise SanXuatKcsTieuChiValidationError("Phải chọn công đoạn cho hạng mục kiểm.")
        cd = int(cd)
        if not self.repo.cong_doan_ids_ton_tai({cd}):
            raise SanXuatKcsTieuChiValidationError(f"Công đoạn không tồn tại: {cd}.")
        if self.repo.trung_ten(cd, ten, tru_id=(obj.id if obj is not None else None)):
            raise SanXuatKcsTieuChiValidationError(
                f"Công đoạn này đã có hạng mục “{ten}”."
            )
