"""Đơn giá khoán data access — chỉ tầng này chạm DB cho bảng piece_rates."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models.piece_work import PieceRate


class PieceWorkRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    # --- piece_rates --------------------------------------------------------

    def list_rates(self, *, active_only: bool = False) -> list[PieceRate]:
        stmt = select(PieceRate)
        if active_only:
            stmt = stmt.where(PieceRate.is_active.is_(True))
        return list(self.db.execute(stmt.order_by(PieceRate.group_name, PieceRate.id)).scalars())

    def get_rate(self, rate_id: int) -> PieceRate | None:
        return self.db.get(PieceRate, rate_id)

    def create_rate(self, **f) -> PieceRate:
        r = PieceRate(**f); self.db.add(r); self.db.commit(); self.db.refresh(r); return r

    def update_rate(self, r: PieceRate, **f) -> PieceRate:
        for k, v in f.items():
            setattr(r, k, v)
        self.db.commit(); self.db.refresh(r); return r

    def delete_rate(self, r: PieceRate) -> None:
        self.db.delete(r); self.db.commit()

    def commit(self) -> None:
        self.db.commit()
