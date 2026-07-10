"""Danh mục Bù hao — service CRUD (validate trục + bậc động)."""
from __future__ import annotations

from ..models.bu_hao import DON_VI_BAC, TRUC_BU_HAO
from ..repositories.bu_hao_repo import BuHaoRepository


class BuHaoError(Exception):
    pass


class BuHaoValidationError(BuHaoError):
    pass


class BuHaoDuplicate(BuHaoError):
    pass


class BuHaoNotFound(BuHaoError):
    pass


class BuHaoService:
    def __init__(self, repo: BuHaoRepository) -> None:
        self.repo = repo

    def _validate(self, data: dict) -> None:
        if not (data.get("ma") or "").strip():
            raise BuHaoValidationError("Mã không được trống.")
        if not (data.get("ten") or "").strip():
            raise BuHaoValidationError("Tên không được trống.")
        if data.get("truc") and data["truc"] not in TRUC_BU_HAO:
            raise BuHaoValidationError("Trục tra không hợp lệ (so_mau/so_con).")
        if data.get("key_tu") is not None and data.get("key_den") is not None:
            if int(data["key_tu"]) > int(data["key_den"]):
                raise BuHaoValidationError("Dải trục: từ phải ≤ đến.")
        for b in (data.get("bac") or []):
            if b.get("don_vi") and b["don_vi"] not in DON_VI_BAC:
                raise BuHaoValidationError("Đơn vị bậc không hợp lệ (tờ/%).")
            tu, den = b.get("sl_tu"), b.get("sl_den")
            if den is not None and tu is not None and int(tu) >= int(den):
                raise BuHaoValidationError(f"Bậc SL: từ ({tu}) phải < đến ({den}).")

    def get(self, item_id: int):
        obj = self.repo.get(item_id)
        if obj is None:
            raise BuHaoNotFound("Không tìm thấy dòng bù hao.")
        return obj

    def list(self, **kw):
        return self.repo.list(**kw)

    def create(self, data: dict):
        self._validate(data)
        if self.repo.find_by_ma(data["ma"]) is not None:
            raise BuHaoDuplicate("Mã đã tồn tại.")
        return self.repo.create(data)

    def update(self, item_id: int, data: dict):
        obj = self.get(item_id)
        self._validate(data)
        dup = self.repo.find_by_ma(data["ma"])
        if dup is not None and dup.id != obj.id:
            raise BuHaoDuplicate("Mã đã tồn tại.")
        return self.repo.update(obj, data)

    def delete(self, item_id: int) -> None:
        self.repo.delete(self.get(item_id))
