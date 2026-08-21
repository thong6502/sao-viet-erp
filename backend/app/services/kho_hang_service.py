"""Danh mục Kho hàng — service CRUD (chỉ khai báo, validate nhẹ).

Thân CRUD dùng chung ở `services/catalog_base.CatalogService`; ở đây chỉ còn luật riêng.
"""
from __future__ import annotations

from ..repositories.kho_hang_repo import KhoHangRepository
from .catalog_base import (
    CatalogDuplicate, CatalogError, CatalogInUse, CatalogNotFound, CatalogService,
    CatalogValidationError,
)


class KhoHangError(CatalogError):
    pass


class KhoHangValidationError(KhoHangError, CatalogValidationError):
    pass


class KhoHangDuplicate(KhoHangError, CatalogDuplicate):
    pass


class KhoHangNotFound(KhoHangError, CatalogNotFound):
    pass


class KhoHangInUse(KhoHangError, CatalogInUse):
    """Kho còn tồn / phiếu chờ ghi sổ / đề nghị đang xử lý → chặn xóa."""
    pass


# Khoá đếm của `repo.dem_rang_buoc()` → câu tiếng Việt hiện trong hộp thoại xoá.
_LY_DO = (
    ("lo_con_ton", "lô còn tồn"),
    ("phieu_cho_ghi_so", "phiếu chờ ghi sổ"),
    ("de_nghi_dang_xu_ly", "đề nghị đang xử lý"),
)


class KhoHangService(CatalogService):
    LOAI = "kho_hang"
    E_NOT_FOUND = KhoHangNotFound
    E_DUPLICATE = KhoHangDuplicate
    E_VALIDATION = KhoHangValidationError
    E_IN_USE = KhoHangInUse
    MSG_NOT_FOUND = "Không tìm thấy kho."
    MSG_DUPLICATE = "Mã kho đã tồn tại."
    MSG_IN_USE = "Không xóa được — kho đang dùng: {ly_do}."
    MA_TU_SINH = True      # UI không cho gõ mã tay → server cấp KHO-####
    XOA_MEM = True         # giữ FK cho lịch sử phiếu đã ghi sổ

    def __init__(self, repo: KhoHangRepository, audit=None) -> None:
        super().__init__(repo, audit)

    def _validate(self, data: dict, obj=None) -> None:
        if not (data.get("ten") or "").strip():
            raise KhoHangValidationError("Tên kho không được trống.")

    def _blockers(self, obj) -> list[str]:
        dem = self.repo.dem_rang_buoc(obj.id)
        return [f"{dem[k]} {nhan}" for k, nhan in _LY_DO if dem[k]]
