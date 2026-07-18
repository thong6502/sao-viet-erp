"""Repository — Công đoạn (danh mục). CRUD + list/filter + find_by_ma."""
from __future__ import annotations

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ..models.cong_doan import CongDoan

ASSIGNABLE = (
    "ten", "ten_hien_thi", "kieu_bu_hao", "bu_hao_id", "so_to_bu_hao", "nhom", "may_id", "department_id", "khoan_ghi_theo",
    "allowed_defect_pct", "allowed_defect_abs",
    "che_do_tinh", "pricing_basis", "setup_cost", "setup_time",
    "run_rate", "rate_tiers", "size_tiers", "first_unit_floor", "min_charge", "requires_tooling",
    "tooling_type", "spoilage_pct", "inline_flag", "ghi_chu", "active", "cong_thuc_gia",
)


class CongDoanRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get(self, cd_id: int) -> CongDoan | None:
        return self.db.get(CongDoan, cd_id)

    def find_by_ma(self, ma: str) -> CongDoan | None:
        ma = (ma or "").strip().upper()
        if not ma:
            return None
        return self.db.execute(select(CongDoan).where(func.upper(CongDoan.ma) == ma)).scalars().first()

    def list(self, *, q: str | None = None, nhom: str | None = None,
             active: bool | None = None, page: int = 1, size: int = 50):
        conds = []
        if q:
            like = f"%{q.strip().lower()}%"
            conds.append(or_(func.lower(CongDoan.ma).like(like), func.lower(CongDoan.ten).like(like)))
        if nhom:
            conds.append(CongDoan.nhom == nhom)
        if active is not None:
            conds.append(CongDoan.active.is_(active))
        base = select(CongDoan)
        count_stmt = select(func.count()).select_from(CongDoan)
        for c in conds:
            base = base.where(c)
            count_stmt = count_stmt.where(c)
        total = self.db.execute(count_stmt).scalar_one()
        page, size = max(1, page), max(1, min(size, 200))
        base = base.order_by(CongDoan.ma.asc()).offset((page - 1) * size).limit(size)
        return list(self.db.execute(base).scalars()), total

    def _apply(self, cd: CongDoan, data: dict) -> None:
        for k in ASSIGNABLE:
            if k in data:
                setattr(cd, k, data[k])

    def create(self, data: dict) -> CongDoan:
        cd = CongDoan(ma=data["ma"].strip().upper())
        self._apply(cd, data)
        self.db.add(cd)
        self.db.commit()
        self.db.refresh(cd)
        return cd

    def update(self, cd: CongDoan, data: dict) -> CongDoan:
        if data.get("ma"):
            cd.ma = data["ma"].strip().upper()
        self._apply(cd, data)
        self.db.commit()
        self.db.refresh(cd)
        return cd

    def delete(self, cd: CongDoan) -> None:
        self.db.delete(cd)
        self.db.commit()
