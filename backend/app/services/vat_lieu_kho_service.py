"""Danh mục Giấy & Vật tư — service CRUD (chủng loại giấy / giấy / vật tư in ấn)."""
from __future__ import annotations

from decimal import Decimal

from ..models.vat_lieu_kho import BE_MAT_GIAY, DON_VI_GIA_GIAY, DON_VI_GIA_VAT_TU, THO
from ..repositories.vat_lieu_kho_repo import VERSION_SNAPSHOT, VatLieuKhoRepository


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
        if kind == "chung_loai_giay":
            if data.get("be_mat") not in (None, "") and data["be_mat"] not in BE_MAT_GIAY:
                raise VatLieuKhoValidationError("Bề mặt giấy không hợp lệ.")
            if data.get("tho_mac_dinh") not in (None, "") and data["tho_mac_dinh"] not in THO:
                raise VatLieuKhoValidationError("Thớ mặc định không hợp lệ.")
        elif kind == "giay":
            if not data.get("chung_loai_giay_id"):
                raise VatLieuKhoValidationError("Phải chọn Chủng loại giấy.")
            # Khổ 0 = cuộn/khổ mở (bảng xưởng ghi "0x0") — cho phép; chỉ chặn số âm.
            if _f(data.get("kho_dai")) < 0 or _f(data.get("kho_rong")) < 0:
                raise VatLieuKhoValidationError("Khổ giấy không được âm.")
            if _f(data.get("gsm")) <= 0:
                raise VatLieuKhoValidationError("GSM phải > 0.")
            if data.get("don_vi_gia") and data["don_vi_gia"] not in DON_VI_GIA_GIAY:
                raise VatLieuKhoValidationError("Đơn vị giá giấy không hợp lệ.")
            if data.get("tho") not in (None, "") and data["tho"] not in THO:
                raise VatLieuKhoValidationError("Thớ không hợp lệ.")
        elif kind == "vat_tu":
            if data.get("don_vi_gia") and data["don_vi_gia"] not in DON_VI_GIA_VAT_TU:
                raise VatLieuKhoValidationError("Đơn vị giá vật tư không hợp lệ.")
        elif kind == "kho_giay_chuan":
            if not data.get("chung_loai_giay_id"):
                raise VatLieuKhoValidationError("Phải chọn Chủng loại giấy.")
            if _f(data.get("rong")) <= 0:
                raise VatLieuKhoValidationError("Khổ rộng phải > 0.")
            if data.get("dai") not in (None, "") and _f(data.get("dai")) <= 0:
                raise VatLieuKhoValidationError("Khổ dài nếu nhập phải > 0 (bỏ trống = cuộn/khổ mở).")

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

    # -- Phiên bản giá giấy (lịch sử) --
    def _ensure_v1(self, giay) -> None:
        """Backfill v1 từ bản ghi Giấy hiện tại nếu chưa có phiên bản nào (giấy tạo trước tính năng)."""
        if not self.repo.has_versions(giay.id):
            snap = {k: getattr(giay, k, None) for k in VERSION_SNAPSHOT}
            self.repo.create_version(giay.id, snap, ghi_chu="Phiên bản đầu")

    def list_giay_versions(self, giay_id: int):
        giay = self.get("giay", giay_id)
        self._ensure_v1(giay)
        return self.repo.list_versions(giay_id)

    def add_giay_version(self, giay_id: int, data: dict, created_by: int | None = None):
        giay = self.get("giay", giay_id)
        if _f(data.get("gsm")) <= 0:
            raise VatLieuKhoValidationError("GSM phải > 0.")
        if data.get("don_vi_gia") and data["don_vi_gia"] not in DON_VI_GIA_GIAY:
            raise VatLieuKhoValidationError("Đơn vị giá giấy không hợp lệ.")
        self._ensure_v1(giay)
        v = self.repo.create_version(
            giay_id, data, ngay_hieu_luc=data.get("ngay_hieu_luc"),
            ghi_chu=data.get("ghi_chu"), created_by=created_by,
        )
        # Mirror bản ghi Giấy (hiện hành) = version mới nhất + số phiên bản.
        for k in VERSION_SNAPSHOT:
            if k in data and data[k] is not None:
                setattr(giay, k, data[k])
        giay.version_no = v.version_no
        self.repo.db.commit()
        return v
