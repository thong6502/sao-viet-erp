"""Vật liệu Kho — service: CRUD 3 loại + lookup giá kẽm (thiếu → LỖI, không tính 0)."""
from __future__ import annotations

from decimal import Decimal

from ..models.vat_lieu_kho import DON_VI_GIA_GIAY, KHOA_CLASS, LOAI_MUC, THO
from ..repositories.vat_lieu_kho_repo import VatLieuKhoRepository


class VatLieuKhoError(Exception):
    pass


class VatLieuKhoValidationError(VatLieuKhoError):
    pass


class VatLieuKhoDuplicate(VatLieuKhoError):
    pass


class VatLieuKhoNotFound(VatLieuKhoError):
    pass


def _f(v) -> float:
    return float(v) if isinstance(v, Decimal) else float(v or 0)


class VatLieuKhoService:
    def __init__(self, repo: VatLieuKhoRepository) -> None:
        self.repo = repo

    def _validate(self, kind: str, data: dict) -> None:
        if not (data.get("ma") or "").strip():
            raise VatLieuKhoValidationError("Mã không được trống.")
        if not (data.get("ten") or "").strip():
            raise VatLieuKhoValidationError("Tên không được trống.")
        if kind == "giay":
            if _f(data.get("kho_dai")) <= 0 or _f(data.get("kho_rong")) <= 0:
                raise VatLieuKhoValidationError("Khổ giấy (dài×rộng) phải > 0.")
            if _f(data.get("gsm")) <= 0:
                raise VatLieuKhoValidationError("GSM phải > 0.")
            if data.get("don_vi_gia") and data["don_vi_gia"] not in DON_VI_GIA_GIAY:
                raise VatLieuKhoValidationError("Đơn vị giá giấy không hợp lệ.")
            if data.get("tho") not in (None, "") and data["tho"] not in THO:
                raise VatLieuKhoValidationError("Thớ không hợp lệ.")
        elif kind == "muc":
            if data.get("loai_muc") and data["loai_muc"] not in LOAI_MUC:
                raise VatLieuKhoValidationError("Loại mực không hợp lệ.")
        elif kind == "ban":
            if data.get("khoa_class") not in KHOA_CLASS:
                raise VatLieuKhoValidationError("khoa_class không hợp lệ.")

    def get(self, kind: str, item_id: int):
        obj = self.repo.get(kind, item_id)
        if obj is None:
            raise VatLieuKhoNotFound("Không tìm thấy mặt hàng.")
        return obj

    def list(self, kind: str, **kw):
        return self.repo.list(kind, **kw)

    def create(self, kind: str, data: dict):
        self._validate(kind, data)
        if self.repo.find_by_ma(kind, data["ma"]) is not None:
            raise VatLieuKhoDuplicate("Mã đã tồn tại.")
        return self.repo.create(kind, data)

    def update(self, kind: str, item_id: int, data: dict):
        obj = self.get(kind, item_id)
        self._validate(kind, data)
        dup = self.repo.find_by_ma(kind, data["ma"])
        if dup is not None and dup.id != obj.id:
            raise VatLieuKhoDuplicate("Mã đã tồn tại.")
        return self.repo.update(obj, kind, data)

    def delete(self, kind: str, item_id: int) -> None:
        self.repo.delete(self.get(kind, item_id))

    # -- lookup cho engine tính giá --
    def lookup_don_gia_kem(self, khoa_class: str) -> float:
        """Giá 1 bản kẽm theo khổ máy. Thiếu mặt hàng → LỖI (E-TG-KHO-MISS), KHÔNG trả 0."""
        ban = self.repo.ban_kem_by_khoa_class(khoa_class)
        if ban is None:
            raise VatLieuKhoNotFound(
                f"Thiếu bản kẽm cho khổ máy '{khoa_class}' trong Kho. [E-TG-KHO-MISS]"
            )
        return _f(ban.don_gia_kem)
