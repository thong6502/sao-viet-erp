"""Repository — Danh mục Bù hao. CRUD + lọc theo trục (số màu/số con)."""
from __future__ import annotations

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ..models.bu_hao import BuHao

_FIELDS = ("ten", "truc", "key_tu", "key_den", "bac", "ghi_chu", "active")


class BuHaoRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get(self, item_id: int):
        return self.db.get(BuHao, item_id)

    def find_by_ma(self, ma: str):
        ma = (ma or "").strip().upper()
        if not ma:
            return None
        return self.db.execute(select(BuHao).where(func.upper(BuHao.ma) == ma)).scalars().first()

    def list(self, *, q: str | None = None, truc: str | None = None, active: bool | None = None,
             page: int = 1, size: int = 50):
        conds = []
        if q:
            like = f"%{q.strip().lower()}%"
            conds.append(or_(func.lower(BuHao.ma).like(like), func.lower(BuHao.ten).like(like)))
        if truc:
            conds.append(BuHao.truc == truc)
        if active is not None:
            conds.append(BuHao.active.is_(active))
        base = select(BuHao)
        count_stmt = select(func.count()).select_from(BuHao)
        for c in conds:
            base = base.where(c)
            count_stmt = count_stmt.where(c)
        total = self.db.execute(count_stmt).scalar_one()
        page, size = max(1, page), max(1, min(size, 200))
        base = base.order_by(BuHao.truc.asc(), BuHao.key_tu.asc(), BuHao.ma.asc()).offset((page - 1) * size).limit(size)
        return list(self.db.execute(base).scalars()), total

    def create(self, data: dict):
        obj = BuHao(ma=data["ma"].strip().upper())
        for k in _FIELDS:
            if k in data:
                setattr(obj, k, data[k])
        self.db.add(obj)
        self.db.commit()
        self.db.refresh(obj)
        return obj

    def update(self, obj, data: dict):
        if data.get("ma"):
            obj.ma = data["ma"].strip().upper()
        for k in _FIELDS:
            if k in data:
                setattr(obj, k, data[k])
        self.db.commit()
        self.db.refresh(obj)
        return obj

    def delete(self, obj) -> None:
        self.db.delete(obj)
        self.db.commit()
