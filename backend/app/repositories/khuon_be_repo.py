"""Repository — Danh mục Khuôn bế. CRUD + tìm theo mã/tên + sinh mã tự động KB-####."""
from __future__ import annotations

import re

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ..models.khuon_be import KhuonBe

_FIELDS = ("ten", "khach_hang", "so_ke", "ngay_lam_khuon", "tinh_trang", "ghi_chu", "active")
_MA_PREFIX = "KB-"


class KhuonBeRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get(self, item_id: int):
        return self.db.get(KhuonBe, item_id)

    def next_ma(self) -> str:
        """Mã kế tiếp KB-#### tính trên MỌI hàng (kể cả đã xóa mềm) → không đụng mã cũ
        đã kẹt trong DB (ma unique). Chỉ tăng, chấp nhận có khoảng trống."""
        rx = re.compile(rf"^{_MA_PREFIX}(\d+)$")
        mx = 0
        for ma in self.db.execute(select(KhuonBe.ma)).scalars():
            m = rx.match((ma or "").strip().upper())
            if m:
                mx = max(mx, int(m.group(1)))
        return f"{_MA_PREFIX}{mx + 1:04d}"

    def find_by_ma(self, ma: str):
        ma = (ma or "").strip().upper()
        if not ma:
            return None
        return self.db.execute(select(KhuonBe).where(func.upper(KhuonBe.ma) == ma)).scalars().first()

    def list(self, *, q: str | None = None, active: bool | None = None,
             page: int = 1, size: int = 50):
        conds = []
        if q:
            like = f"%{q.strip().lower()}%"
            conds.append(or_(
                func.lower(KhuonBe.ma).like(like),
                func.lower(KhuonBe.ten).like(like),
                func.lower(KhuonBe.khach_hang).like(like),
                func.lower(KhuonBe.so_ke).like(like),
            ))
        if active is not None:
            conds.append(KhuonBe.active.is_(active))
        base = select(KhuonBe)
        count_stmt = select(func.count()).select_from(KhuonBe)
        for c in conds:
            base = base.where(c)
            count_stmt = count_stmt.where(c)
        total = self.db.execute(count_stmt).scalar_one()
        page, size = max(1, page), max(1, min(size, 200))
        base = base.order_by(KhuonBe.ma.asc()).offset((page - 1) * size).limit(size)
        return list(self.db.execute(base).scalars()), total

    def create(self, data: dict):
        obj = KhuonBe(ma=data["ma"].strip().upper())
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
