"""Repository — Danh mục Đơn vị đo & quy đổi. CRUD + tra theo mã + liệt kê họ đã dùng."""
from __future__ import annotations

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ..models.don_vi_do import DonViDo

_FIELDS = ("ten", "ho", "he_so_goc", "hieu_luc_tu", "ghi_chu", "active")


class DonViDoRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get(self, item_id: int):
        return self.db.get(DonViDo, item_id)

    def find_by_ma(self, ma: str):
        ma = (ma or "").strip().lower()
        if not ma:
            return None
        return self.db.execute(
            select(DonViDo).where(func.lower(DonViDo.ma) == ma)
        ).scalars().first()

    def all_active(self) -> list[DonViDo]:
        """Toàn bộ đơn vị đang dùng — nguồn cho `quy_doi_service` (bảng nhỏ, nạp cả bảng là đủ)."""
        return list(
            self.db.execute(
                select(DonViDo).where(DonViDo.active.is_(True)).order_by(DonViDo.ho, DonViDo.ma)
            ).scalars()
        )

    def distinct_ho(self) -> list[str]:
        """Họ đã có trong dữ liệu — gợi ý cho ô "Họ" (form MỞ, không phải whitelist)."""
        rows = self.db.execute(
            select(DonViDo.ho).where(DonViDo.ho.is_not(None)).distinct()
        ).scalars()
        return sorted({(h or "").strip() for h in rows if (h or "").strip()})

    def list(self, *, q: str | None = None, ho: str | None = None, active: bool | None = None,
             page: int = 1, size: int = 50):
        conds = []
        if q:
            like = f"%{q.strip().lower()}%"
            conds.append(or_(func.lower(DonViDo.ma).like(like), func.lower(DonViDo.ten).like(like)))
        if ho:
            conds.append(func.lower(DonViDo.ho) == ho.strip().lower())
        if active is not None:
            conds.append(DonViDo.active.is_(active))
        base = select(DonViDo)
        count_stmt = select(func.count()).select_from(DonViDo)
        for c in conds:
            base = base.where(c)
            count_stmt = count_stmt.where(c)
        total = self.db.execute(count_stmt).scalar_one()
        page, size = max(1, page), max(1, min(size, 200))
        base = base.order_by(DonViDo.ho.asc(), DonViDo.he_so_goc.asc(), DonViDo.ma.asc())
        base = base.offset((page - 1) * size).limit(size)
        return list(self.db.execute(base).scalars()), total

    def create(self, data: dict):
        obj = DonViDo(ma=data["ma"].strip().lower())
        for k in _FIELDS:
            if k in data:
                setattr(obj, k, data[k])
        self.db.add(obj)
        self.db.commit()
        self.db.refresh(obj)
        return obj

    def update(self, obj, data: dict):
        if data.get("ma"):
            obj.ma = data["ma"].strip().lower()
        for k in _FIELDS:
            if k in data:
                setattr(obj, k, data[k])
        self.db.commit()
        self.db.refresh(obj)
        return obj

    def delete(self, obj) -> None:
        self.db.delete(obj)
        self.db.commit()
