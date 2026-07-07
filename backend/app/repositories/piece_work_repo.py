"""Lương khoán data access — chỉ tầng này chạm DB cho piece_* tables."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models.piece_work import PieceBatch, PieceBatchEntry, PieceBatchShare, PieceRate


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

    # --- piece_batches ------------------------------------------------------

    def get_batch(self, batch_id: int) -> PieceBatch | None:
        return self.db.get(PieceBatch, batch_id)

    def get_batch_by_ymg(self, year: int, month: int, group_name: str) -> PieceBatch | None:
        return self.db.execute(
            select(PieceBatch).where(
                PieceBatch.year == year, PieceBatch.month == month, PieceBatch.group_name == group_name
            )
        ).scalars().first()

    def list_batches(self, year: int, month: int) -> list[PieceBatch]:
        return list(self.db.execute(
            select(PieceBatch).where(PieceBatch.year == year, PieceBatch.month == month)
            .order_by(PieceBatch.group_name)
        ).scalars())

    def create_batch(self, **f) -> PieceBatch:
        b = PieceBatch(**f); self.db.add(b); self.db.commit(); self.db.refresh(b); return b

    def update_batch(self, b: PieceBatch, **f) -> PieceBatch:
        for k, v in f.items():
            setattr(b, k, v)
        self.db.commit(); self.db.refresh(b); return b

    def delete_batch(self, b: PieceBatch) -> None:
        self.db.delete(b); self.db.commit()

    # --- entries ------------------------------------------------------------

    def list_entries(self, batch_id: int) -> list[PieceBatchEntry]:
        return list(self.db.execute(
            select(PieceBatchEntry).where(PieceBatchEntry.batch_id == batch_id).order_by(PieceBatchEntry.id)
        ).scalars())

    def get_entry(self, entry_id: int) -> PieceBatchEntry | None:
        return self.db.get(PieceBatchEntry, entry_id)

    def create_entry(self, **f) -> PieceBatchEntry:
        e = PieceBatchEntry(**f); self.db.add(e); self.db.commit(); self.db.refresh(e); return e

    def update_entry(self, e: PieceBatchEntry, **f) -> PieceBatchEntry:
        for k, v in f.items():
            setattr(e, k, v)
        self.db.commit(); self.db.refresh(e); return e

    def delete_entry(self, e: PieceBatchEntry) -> None:
        self.db.delete(e); self.db.commit()

    # --- shares -------------------------------------------------------------

    def list_shares(self, batch_id: int) -> list[PieceBatchShare]:
        return list(self.db.execute(
            select(PieceBatchShare).where(PieceBatchShare.batch_id == batch_id).order_by(PieceBatchShare.id)
        ).scalars())

    def get_share(self, share_id: int) -> PieceBatchShare | None:
        return self.db.get(PieceBatchShare, share_id)

    def get_share_by_be(self, batch_id: int, employee_id: int) -> PieceBatchShare | None:
        return self.db.execute(
            select(PieceBatchShare).where(
                PieceBatchShare.batch_id == batch_id, PieceBatchShare.employee_id == employee_id
            )
        ).scalars().first()

    def create_share(self, **f) -> PieceBatchShare:
        s = PieceBatchShare(**f); self.db.add(s); self.db.commit(); self.db.refresh(s); return s

    def update_share(self, s: PieceBatchShare, **f) -> PieceBatchShare:
        for k, v in f.items():
            setattr(s, k, v)
        self.db.commit(); self.db.refresh(s); return s

    def delete_share(self, s: PieceBatchShare) -> None:
        self.db.delete(s); self.db.commit()

    def commit(self) -> None:
        self.db.commit()
