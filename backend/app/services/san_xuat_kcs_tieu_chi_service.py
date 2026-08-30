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
    E_NOT_FOUND, E_DUPLICATE, E_VALIDATION = (
        SanXuatKcsTieuChiNotFound, SanXuatKcsTieuChiDuplicate, SanXuatKcsTieuChiValidationError,
    )
    MSG_NOT_FOUND = "Không tìm thấy tiêu chí KCS."
    MSG_DUPLICATE = "Mã đã tồn tại."

    def __init__(self, repo: SanXuatKcsTieuChiRepository, audit=None) -> None:
        super().__init__(repo, audit)

    def _validate(self, data: dict, obj=None) -> None:
        if not (data.get("ma") or "").strip():
            raise SanXuatKcsTieuChiValidationError("Mã không được trống.")
        if not (data.get("ten") or "").strip():
            raise SanXuatKcsTieuChiValidationError("Tên không được trống.")
        ids = [int(i) for i in (data.get("cong_doan_ids") or [])]
        if ids:
            co_that = self.repo.cong_doan_ids_ton_tai(set(ids))
            sai = sorted(set(ids) - co_that)
            if sai:
                raise SanXuatKcsTieuChiValidationError(
                    f"Công đoạn không tồn tại: {', '.join(str(i) for i in sai)}."
                )
