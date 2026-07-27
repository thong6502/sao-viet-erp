"""Repository Bài ghép — mọi truy vấn DB của module Bài ghép nằm ở đây.

Hàng chờ ghép = LSX `san_sang`, CÓ công đoạn in (`nhom='print'`, `loai_buoc='may'`), CHƯA thuộc bài
ghép nào. "Đã ghép chưa" suy qua `NOT EXISTS(bai_ghep_thanh_vien)` — không cột cache.
"""
from __future__ import annotations

from sqlalchemy import and_, exists, select
from sqlalchemy.orm import Session, selectinload

from ..models.bai_ghep import BaiGhep, BaiGhepThanhVien
from ..models.lsx import LB_MAY, TT_SAN_SANG as LSX_SAN_SANG, Lsx, LsxCongDoan

NHOM_PRINT = "print"


class BaiGhepRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    # --- reads ---------------------------------------------------------------

    def get(self, bai_ghep_id: int) -> BaiGhep | None:
        return self.db.execute(
            select(BaiGhep)
            .where(BaiGhep.id == bai_ghep_id)
            .options(selectinload(BaiGhep.thanh_viens))
        ).scalar_one_or_none()

    def list(self) -> list[BaiGhep]:
        return list(
            self.db.execute(
                select(BaiGhep)
                .options(selectinload(BaiGhep.thanh_viens))
                .order_by(BaiGhep.created_at.desc())
            ).scalars()
        )

    def hang_cho_ghep(self) -> list[Lsx]:
        """LSX sẵn sàng + có công đoạn in + chưa thuộc bài ghép nào (mới nhất trước)."""
        return list(
            self.db.execute(
                select(Lsx)
                .where(
                    Lsx.trang_thai == LSX_SAN_SANG,
                    Lsx.cong_doans.any(
                        and_(LsxCongDoan.nhom == NHOM_PRINT, LsxCongDoan.loai_buoc == LB_MAY)
                    ),
                    ~exists(
                        select(BaiGhepThanhVien.id).where(BaiGhepThanhVien.lsx_id == Lsx.id)
                    ),
                )
                .options(selectinload(Lsx.cong_doans))
                .order_by(Lsx.created_at.desc())
            ).scalars()
        )

    def lsx_by_ids(self, lsx_ids: list[int]) -> dict[int, Lsx]:
        """id → LSX (kèm công đoạn) cho các LSX được chọn/đang là thành viên."""
        if not lsx_ids:
            return {}
        rows = self.db.execute(
            select(Lsx).where(Lsx.id.in_(lsx_ids)).options(selectinload(Lsx.cong_doans))
        ).scalars()
        return {r.id: r for r in rows}

    def lsx_da_ghep(self, lsx_ids: list[int]) -> set[int]:
        """Tập LSX (trong `lsx_ids`) ĐÃ thuộc một bài ghép — nguồn guard '1 LSX ≤ 1 bài'."""
        if not lsx_ids:
            return set()
        rows = self.db.execute(
            select(BaiGhepThanhVien.lsx_id).where(BaiGhepThanhVien.lsx_id.in_(lsx_ids))
        ).scalars()
        return set(rows)

    # --- writes --------------------------------------------------------------

    def add(self, bg: BaiGhep) -> BaiGhep:
        self.db.add(bg)
        self.db.flush()
        return bg

    def delete(self, bg: BaiGhep) -> None:
        self.db.delete(bg)
        self.db.flush()

    def commit(self) -> None:
        self.db.commit()
