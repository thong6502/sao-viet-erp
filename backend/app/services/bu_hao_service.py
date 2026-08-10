"""Danh mục Bù hao — service CRUD (validate bậc động)."""
from __future__ import annotations

from ..models.bu_hao import DON_VI_BAC
from ..repositories.bu_hao_repo import BuHaoRepository
from . import nhat_ky_danh_muc as nk


class BuHaoError(Exception):
    pass


class BuHaoValidationError(BuHaoError):
    pass


class BuHaoDuplicate(BuHaoError):
    pass


class BuHaoNotFound(BuHaoError):
    pass


class BuHaoService:
    def __init__(self, repo: BuHaoRepository, audit=None) -> None:
        self.repo = repo
        self.audit = audit

    def _validate(self, data: dict) -> None:
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

    def get(self, item_id: int):
        obj = self.repo.get(item_id)
        if obj is None:
            raise BuHaoNotFound("Không tìm thấy dòng bù hao.")
        return obj

    def list(self, **kw):
        return self.repo.list(**kw)

    def create(self, data: dict, created_by: int | None = None):
        self._validate(data)
        if self.repo.find_by_ma(data["ma"]) is not None:
            raise BuHaoDuplicate("Mã đã tồn tại.")
        obj = self.repo.create(data)
        nk.ghi_tao(self.audit, actor_id=created_by, loai="bu_hao", obj=obj)
        return obj

    def update(self, item_id: int, data: dict, actor_id: int | None = None):
        obj = self.get(item_id)
        self._validate(data)
        dup = self.repo.find_by_ma(data["ma"])
        if dup is not None and dup.id != obj.id:
            raise BuHaoDuplicate("Mã đã tồn tại.")
        truoc = nk.anh_chup(obj)
        obj = self.repo.update(obj, data)
        nk.ghi_sua(self.audit, actor_id=actor_id, loai="bu_hao", obj=obj, truoc=truoc)
        return obj

    def delete(self, item_id: int, actor_id: int | None = None) -> None:
        obj = self.get(item_id)
        nk.ghi_xoa(self.audit, actor_id=actor_id, loai="bu_hao", obj=obj)
        self.repo.delete(obj)
