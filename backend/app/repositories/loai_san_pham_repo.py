"""Repository — Loại sản phẩm (template). CRUD + list/filter + find_by_ma."""
from __future__ import annotations

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ..models.loai_san_pham import LoaiSanPham

ASSIGNABLE = (
    "ten", "structural_type", "box_sub_type", "imposition_rule_id", "default_so_mat",
    "has_cover", "cover_type", "default_binding", "default_stock_class", "routing_template",
    "vat_rate", "ghi_chu", "active",
)


class LoaiSanPhamRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get(self, sp_id: int) -> LoaiSanPham | None:
        return self.db.get(LoaiSanPham, sp_id)

    def find_by_ma(self, ma: str) -> LoaiSanPham | None:
        ma = (ma or "").strip().upper()
        if not ma:
            return None
        return self.db.execute(select(LoaiSanPham).where(func.upper(LoaiSanPham.ma) == ma)).scalars().first()

    def list(self, *, q: str | None = None, structural_type: str | None = None,
             active: bool | None = None, page: int = 1, size: int = 50):
        conds = []
        if q:
            like = f"%{q.strip().lower()}%"
            conds.append(or_(func.lower(LoaiSanPham.ma).like(like), func.lower(LoaiSanPham.ten).like(like)))
        if structural_type:
            conds.append(LoaiSanPham.structural_type == structural_type)
        if active is not None:
            conds.append(LoaiSanPham.active.is_(active))
        base = select(LoaiSanPham)
        count_stmt = select(func.count()).select_from(LoaiSanPham)
        for c in conds:
            base = base.where(c)
            count_stmt = count_stmt.where(c)
        total = self.db.execute(count_stmt).scalar_one()
        page, size = max(1, page), max(1, min(size, 200))
        base = base.order_by(LoaiSanPham.ma.asc()).offset((page - 1) * size).limit(size)
        return list(self.db.execute(base).scalars()), total

    def _apply(self, sp: LoaiSanPham, data: dict) -> None:
        for k in ASSIGNABLE:
            if k in data:
                setattr(sp, k, data[k])

    def create(self, data: dict) -> LoaiSanPham:
        sp = LoaiSanPham(ma=data["ma"].strip().upper())
        self._apply(sp, data)
        self.db.add(sp)
        self.db.commit()
        self.db.refresh(sp)
        return sp

    def update(self, sp: LoaiSanPham, data: dict) -> LoaiSanPham:
        if data.get("ma"):
            sp.ma = data["ma"].strip().upper()
        self._apply(sp, data)
        self.db.commit()
        self.db.refresh(sp)
        return sp

    def delete(self, sp: LoaiSanPham) -> None:
        self.db.delete(sp)
        self.db.commit()
