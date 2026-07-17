"""Repository — Danh mục Giấy & Vật tư (chủng loại giấy / giấy / vật tư in ấn). CRUD generic."""
from __future__ import annotations

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ..models.vat_lieu_kho import ChungLoaiGiay, GiayGiaVersion, GiayNguyen, KhoGiayChuan, VatTuInAn

# Các trường "ảnh chụp" của 1 phiên bản giá giấy (khớp cột GiayGiaVersion + GiayNguyen).
VERSION_SNAPSHOT = ("kho_dai", "kho_rong", "gsm", "caliper_micron", "tho",
                    "don_vi_gia", "don_gia", "gia_thi_truong")

_CHUNG_LOAI = ("ten", "be_mat", "tho_mac_dinh", "mo_ta", "active")
_GIAY = ("ten", "chung_loai_giay_id", "kho_dai", "kho_rong", "gsm", "caliper_micron",
         "tho", "don_vi_gia", "don_gia", "gia_thi_truong", "kho_tinh_gia", "ghi_chu", "active", "cong_thuc_gia")
_VAT_TU = ("ten", "don_vi_gia", "don_gia", "ghi_chu", "active", "cong_thuc_gia")
_KHO_GIAY_CHUAN = ("ten", "chung_loai_giay_id", "rong", "dai", "la_hiem", "ghi_chu", "active")

_MODELS = {
    "chung_loai_giay": (ChungLoaiGiay, _CHUNG_LOAI),
    "giay": (GiayNguyen, _GIAY),
    "vat_tu": (VatTuInAn, _VAT_TU),
    "kho_giay_chuan": (KhoGiayChuan, _KHO_GIAY_CHUAN),
}


class VatLieuKhoRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def _cfg(self, kind: str):
        if kind not in _MODELS:
            raise ValueError(f"loại danh mục không hợp lệ: {kind}")
        return _MODELS[kind]

    def get(self, kind: str, item_id: int):
        model, _ = self._cfg(kind)
        return self.db.get(model, item_id)

    def find_by_ma(self, kind: str, ma: str):
        model, _ = self._cfg(kind)
        ma = (ma or "").strip().upper()
        if not ma:
            return None
        return self.db.execute(select(model).where(func.upper(model.ma) == ma)).scalars().first()

    def list(self, kind: str, *, q: str | None = None, active: bool | None = None,
             page: int = 1, size: int = 50):
        model, _ = self._cfg(kind)
        conds = []
        if q:
            like = f"%{q.strip().lower()}%"
            conds.append(or_(func.lower(model.ma).like(like), func.lower(model.ten).like(like)))
        if active is not None:
            conds.append(model.active.is_(active))
        base = select(model)
        count_stmt = select(func.count()).select_from(model)
        for c in conds:
            base = base.where(c)
            count_stmt = count_stmt.where(c)
        total = self.db.execute(count_stmt).scalar_one()
        page, size = max(1, page), max(1, min(size, 200))
        base = base.order_by(model.ma.asc()).offset((page - 1) * size).limit(size)
        return list(self.db.execute(base).scalars()), total

    def create(self, kind: str, data: dict):
        model, fields = self._cfg(kind)
        obj = model(ma=data["ma"].strip().upper())
        for k in fields:
            if k in data:
                setattr(obj, k, data[k])
        self.db.add(obj)
        self.db.commit()
        self.db.refresh(obj)
        return obj

    def update(self, obj, kind: str, data: dict):
        _, fields = self._cfg(kind)
        if data.get("ma"):
            obj.ma = data["ma"].strip().upper()
        for k in fields:
            if k in data:
                setattr(obj, k, data[k])
        self.db.commit()
        self.db.refresh(obj)
        return obj

    def delete(self, obj) -> None:
        self.db.delete(obj)
        self.db.commit()

    # -- Phiên bản giá giấy (lịch sử) --
    def has_versions(self, giay_id: int) -> bool:
        return self.db.execute(
            select(GiayGiaVersion.id).where(GiayGiaVersion.giay_id == giay_id).limit(1)
        ).first() is not None

    def list_versions(self, giay_id: int):
        return list(self.db.execute(
            select(GiayGiaVersion).where(GiayGiaVersion.giay_id == giay_id)
            .order_by(GiayGiaVersion.version_no.desc())
        ).scalars())

    def create_version(self, giay_id: int, fields: dict, *, ngay_hieu_luc=None,
                       ghi_chu: str | None = None, created_by: int | None = None):
        # Bỏ cờ hiện hành ở các version cũ.
        for v in self.db.execute(
            select(GiayGiaVersion).where(
                GiayGiaVersion.giay_id == giay_id, GiayGiaVersion.is_current.is_(True))
        ).scalars():
            v.is_current = False
        next_no = (self.db.execute(
            select(func.max(GiayGiaVersion.version_no)).where(GiayGiaVersion.giay_id == giay_id)
        ).scalar() or 0) + 1
        obj = GiayGiaVersion(giay_id=giay_id, version_no=next_no, is_current=True,
                             ngay_hieu_luc=ngay_hieu_luc, ghi_chu=ghi_chu, created_by=created_by)
        for k in VERSION_SNAPSHOT:
            if k in fields and fields[k] is not None:
                setattr(obj, k, fields[k])
        self.db.add(obj)
        self.db.commit()
        self.db.refresh(obj)
        return obj
