"""Downstream port for checking material stock usage (SEAM-22).

Owned by dm_giay_vat_tu (downstream), implemented later by Kho (upstream).
"""
from __future__ import annotations

from typing import Protocol, runtime_checkable

@runtime_checkable
class PaperStockUsageLookupPort(Protocol):
    """Port interface to check if a paper master is referenced by StockLot in Kho."""

    def is_referenced(self, paper_master_id: int) -> bool:  # pragma: no cover
        ...

def is_paper_referenced_in_stock(paper_master_id: int) -> bool:
    # SEAM-22 back-fill (Kho P0): vật tư có lô/sổ tồn nào trong Kho không.
    from ..db import SessionLocal
    from ..repositories.warehouse_stock_repo import StockRepo

    db = SessionLocal()
    try:
        return StockRepo(db).material_has_stock(paper_master_id)
    finally:
        db.close()
