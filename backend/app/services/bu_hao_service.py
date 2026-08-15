"""Danh mục Bù hao — service CRUD (validate bậc động).

Thân CRUD dùng chung ở `services/catalog_base.CatalogService`; ở đây chỉ còn luật riêng.
"""
from __future__ import annotations

from ..models.bu_hao import DON_VI_BAC
from ..repositories.bu_hao_repo import BuHaoRepository
from .catalog_base import (
    CatalogDuplicate, CatalogError, CatalogNotFound, CatalogService, CatalogValidationError,
)


class BuHaoError(CatalogError):
    pass


class BuHaoValidationError(BuHaoError, CatalogValidationError):
    pass


class BuHaoDuplicate(BuHaoError, CatalogDuplicate):
    pass


class BuHaoNotFound(BuHaoError, CatalogNotFound):
    pass


class BuHaoService(CatalogService):
    LOAI = "bu_hao"
    E_NOT_FOUND, E_DUPLICATE, E_VALIDATION = BuHaoNotFound, BuHaoDuplicate, BuHaoValidationError
    MSG_NOT_FOUND = "Không tìm thấy dòng bù hao."
    MSG_DUPLICATE = "Mã đã tồn tại."

    def __init__(self, repo: BuHaoRepository, audit=None) -> None:
        super().__init__(repo, audit)

    def _validate(self, data: dict, obj=None) -> None:
        if not (data.get("ma") or "").strip():
            raise BuHaoValidationError("Mã không được trống.")
        if not (data.get("ten") or "").strip():
            raise BuHaoValidationError("Tên không được trống.")
        for b in (data.get("bac") or []):
            if b.get("don_vi") and b["don_vi"] not in DON_VI_BAC:
                raise BuHaoValidationError("Đơn vị bậc không hợp lệ (tờ/%).")
            tu, den = b.get("sl_tu"), b.get("sl_den")
            if den is not None and tu is not None and int(tu) >= int(den):
                raise BuHaoValidationError(f"Bậc SL: từ ({tu}) phải < đến ({den}).")
