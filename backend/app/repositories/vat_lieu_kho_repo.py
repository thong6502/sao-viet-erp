"""Repository — Vật liệu Kho (giấy/mực/bản). CRUD 3 loại + lookup giá kẽm theo khoa_class."""
from __future__ import annotations

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ..models.vat_lieu_kho import BanKem, GiayNguyen, Muc

_GIAY = ("ten", "kho_dai", "kho_rong", "gsm", "caliper_micron", "tho", "don_vi_gia", "don_gia", "ton", "active")
_MUC = ("ten", "loai_muc", "ma_pantone", "don_gia", "coverage_tiers", "active")
_BAN = ("ten", "khoa_class", "don_gia_kem", "ton", "active")

_MODELS = {"giay": (GiayNguyen, _GIAY), "muc": (Muc, _MUC), "ban": (BanKem, _BAN)}


class VatLieuKhoRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def _cfg(self, kind: str):
        if kind not in _MODELS:
            raise ValueError(f"loại vật liệu không hợp lệ: {kind}")
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

    # -- lookup cho engine --
    def ban_kem_by_khoa_class(self, khoa_class: str) -> BanKem | None:
        return self.db.execute(
            select(BanKem).where(BanKem.khoa_class == khoa_class, BanKem.active.is_(True))
            .order_by(BanKem.id.asc())
        ).scalars().first()
