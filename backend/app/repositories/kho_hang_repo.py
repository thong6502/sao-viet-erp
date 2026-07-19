"""Repository — Danh mục Kho hàng. CRUD + tìm theo mã/tên + sinh mã tự động."""
from __future__ import annotations

import re

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ..models.kho_hang import KhoHang

_FIELDS = ("ten", "vi_tri", "ghi_chu", "active")
_MA_PREFIX = "KHO-"


class KhoHangRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get(self, item_id: int):
        return self.db.get(KhoHang, item_id)

    def next_ma(self) -> str:
        """Mã kế tiếp KHO-#### tính trên MỌI hàng (kể cả đã xóa mềm) → không đụng
        mã cũ đã kẹt trong DB (ma unique). Chỉ tăng, chấp nhận có khoảng trống."""
        rx = re.compile(rf"^{_MA_PREFIX}(\d+)$")
        mx = 0
        for ma in self.db.execute(select(KhoHang.ma)).scalars():
            m = rx.match((ma or "").strip().upper())
            if m:
                mx = max(mx, int(m.group(1)))
        return f"{_MA_PREFIX}{mx + 1:04d}"

    def find_by_ma(self, ma: str):
        ma = (ma or "").strip().upper()
        if not ma:
            return None
        return self.db.execute(select(KhoHang).where(func.upper(KhoHang.ma) == ma)).scalars().first()

    def list(self, *, q: str | None = None, active: bool | None = None,
             page: int = 1, size: int = 50):
        conds = []
        if q:
            like = f"%{q.strip().lower()}%"
            conds.append(or_(func.lower(KhoHang.ma).like(like), func.lower(KhoHang.ten).like(like)))
        if active is not None:
            conds.append(KhoHang.active.is_(active))
        base = select(KhoHang)
        count_stmt = select(func.count()).select_from(KhoHang)
        for c in conds:
            base = base.where(c)
            count_stmt = count_stmt.where(c)
        total = self.db.execute(count_stmt).scalar_one()
        page, size = max(1, page), max(1, min(size, 200))
        base = base.order_by(KhoHang.ma.asc()).offset((page - 1) * size).limit(size)
        return list(self.db.execute(base).scalars()), total

    def create(self, data: dict):
        obj = KhoHang(ma=data["ma"].strip().upper())
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
