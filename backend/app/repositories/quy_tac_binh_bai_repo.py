"""Repository — Quy tắc bình bài. Version-chain trên 2 bảng (header + version).

Sửa cấu hình = đẻ version mới (version_no = max+1, is_current flip). Header giữ danh tính.
"""
from __future__ import annotations

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ..models.quy_tac_binh_bai import QuyTacBinhBai, QuyTacBinhBaiVersion

# Field cấu hình copy từ dict config → cột version.
VERSION_FIELDS = (
    "layout_mode", "side_margin_mm", "tail_colorbar_mm", "gutter_mm", "allow_rotate",
    "grain_constraint", "bleed_default_mm", "allow_gang", "min_gutter_mm", "pages_per_sig",
    "work_style", "nest_method", "matrix_allowance_mm", "lanes", "gap_around_mm",
    "min_pages", "max_pages", "min_spine_mm", "warn_on_grain_violation",
)


class QuyTacBinhBaiRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    # -- header reads --
    def get_header(self, rule_id: int) -> QuyTacBinhBai | None:
        return self.db.get(QuyTacBinhBai, rule_id)

    def find_by_ma(self, ma: str) -> QuyTacBinhBai | None:
        ma = (ma or "").strip().upper()
        if not ma:
            return None
        return self.db.execute(
            select(QuyTacBinhBai).where(func.upper(QuyTacBinhBai.ma) == ma)
        ).scalars().first()

    def list_headers(self, *, q: str | None = None, trang_thai: str | None = None,
                     page: int = 1, size: int = 50) -> tuple[list[QuyTacBinhBai], int]:
        conds = []
        if q:
            like = f"%{q.strip().lower()}%"
            conds.append(or_(func.lower(QuyTacBinhBai.ma).like(like),
                             func.lower(QuyTacBinhBai.ten).like(like)))
        if trang_thai:
            conds.append(QuyTacBinhBai.trang_thai == trang_thai)
        base = select(QuyTacBinhBai)
        count_stmt = select(func.count()).select_from(QuyTacBinhBai)
        for c in conds:
            base = base.where(c)
            count_stmt = count_stmt.where(c)
        total = self.db.execute(count_stmt).scalar_one()
        page = max(1, page)
        size = max(1, min(size, 200))
        base = base.order_by(QuyTacBinhBai.ma.asc()).offset((page - 1) * size).limit(size)
        return list(self.db.execute(base).scalars()), total

    # -- version reads --
    def get_version(self, version_id: int) -> QuyTacBinhBaiVersion | None:
        return self.db.get(QuyTacBinhBaiVersion, version_id)

    def versions_of(self, rule_id: int) -> list[QuyTacBinhBaiVersion]:
        return list(self.db.execute(
            select(QuyTacBinhBaiVersion)
            .where(QuyTacBinhBaiVersion.rule_id == rule_id)
            .order_by(QuyTacBinhBaiVersion.version_no.desc())
        ).scalars())

    def current_version(self, rule_id: int) -> QuyTacBinhBaiVersion | None:
        return self.db.execute(
            select(QuyTacBinhBaiVersion)
            .where(QuyTacBinhBaiVersion.rule_id == rule_id,
                   QuyTacBinhBaiVersion.is_current.is_(True))
        ).scalars().first()

    def version_count(self, rule_id: int) -> int:
        return int(self.db.execute(
            select(func.count()).select_from(QuyTacBinhBaiVersion)
            .where(QuyTacBinhBaiVersion.rule_id == rule_id)
        ).scalar_one())

    def _max_version_no(self, rule_id: int) -> int:
        return int(self.db.execute(
            select(func.max(QuyTacBinhBaiVersion.version_no))
            .where(QuyTacBinhBaiVersion.rule_id == rule_id)
        ).scalar() or 0)

    # -- writes --
    @staticmethod
    def _version_kwargs(config: dict) -> dict:
        return {k: config[k] for k in VERSION_FIELDS if k in config}

    def create_rule(self, *, ma: str, ten: str, mo_ta: str | None, config: dict,
                    actor_id: int | None) -> QuyTacBinhBai:
        header = QuyTacBinhBai(ma=ma.strip().upper(), ten=ten.strip(),
                               mo_ta=(mo_ta or None), trang_thai="active", created_by=actor_id)
        self.db.add(header)
        self.db.flush()
        v1 = QuyTacBinhBaiVersion(rule_id=header.id, version_no=1, is_current=True,
                                  created_by=actor_id, **self._version_kwargs(config))
        self.db.add(v1)
        self.db.commit()
        self.db.refresh(header)
        return header

    def new_version(self, *, rule_id: int, config: dict, ghi_chu: str | None,
                    actor_id: int | None) -> QuyTacBinhBaiVersion:
        # Khoá version hiện hành, đẻ version mới is_current=true.
        for v in self.versions_of(rule_id):
            if v.is_current:
                v.is_current = False
        new_no = self._max_version_no(rule_id) + 1
        nv = QuyTacBinhBaiVersion(rule_id=rule_id, version_no=new_no, is_current=True,
                                  ghi_chu_version=(ghi_chu or None), created_by=actor_id,
                                  **self._version_kwargs(config))
        self.db.add(nv)
        self.db.commit()
        self.db.refresh(nv)
        return nv

    def update_header(self, header: QuyTacBinhBai, *, ten: str | None = None,
                      mo_ta: str | None = None, trang_thai: str | None = None) -> QuyTacBinhBai:
        if ten is not None:
            header.ten = ten.strip()
        if mo_ta is not None:
            header.mo_ta = mo_ta.strip() or None
        if trang_thai is not None:
            header.trang_thai = trang_thai
        self.db.commit()
        self.db.refresh(header)
        return header

    def delete_rule(self, header: QuyTacBinhBai) -> None:
        self.db.delete(header)  # cascade versions
        self.db.commit()
