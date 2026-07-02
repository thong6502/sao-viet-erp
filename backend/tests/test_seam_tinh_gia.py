"""Enabling-point tests for the Tính giá (Costing) cross-module seams — spec-08.

SOURCE OF TRUTH for each seam (together with the ``# SEAM-NN`` markers in
``app/services/costing_ports.py``). ``docs/CROSS_MODULE_LINKS.md`` is only an index.
Back-filling an upstream module flips its ``test_seam_NN`` green (and its stub must then be
replaced by the real adapter).

Two tests per seam:
  - ``test_seam_NN_*`` (skip, carrying the exact reason from CROSS_MODULE_LINKS) is the
    enabling point the upstream builder unskips;
  - ``test_seam_NN_stub_raises`` proves the port fails LOUDLY (NotImplementedError with the
    seam id) while pending — never a silent fake value.
"""
from __future__ import annotations

import pytest

from app.services import costing_ports


# --- SEAM-07 — giá giấy (PaperCost) ----------------------------------------
@pytest.mark.skip(reason="SEAM-07 chờ giá giấy (PaperCost)")
def test_seam_07_paper_cost_lookup():
    price = costing_ports.get_paper_price(paper_master_id=1)
    assert "per_ram" in price or "per_kg" in price
    assert "lot_type" in price
    assert "ownership" in price


def test_seam_07_stub_raises():
    with pytest.raises(NotImplementedError, match="SEAM-07"):
        costing_ports.get_paper_price(paper_master_id=1)


# --- SEAM-08 — đơn giá khoán (PieceRate) -----------------------------------
@pytest.mark.skip(reason="SEAM-08 chờ đơn giá khoán (PieceRate)")
def test_seam_08_piece_rate_lookup():
    rate = costing_ports.get_piece_rate(operation_key="can_mang")
    assert "unit" in rate
    assert "unit_price" in rate


def test_seam_08_stub_raises():
    with pytest.raises(NotImplementedError, match="SEAM-08"):
        costing_ports.get_piece_rate(operation_key="can_mang")


# --- SEAM-09 — định mức/bù hao (Norm) --------------------------------------
def test_seam_09_norm_lookup():
    from app.db import SessionLocal
    from app.models.norm import Norm
    from datetime import date
    
    db = SessionLocal()
    try:
        norm = Norm(
            norm_key="yield_rate",
            value=0.98,
            qty_min=None,
            qty_max=None,
            context_key="{}",
            effective_from=date(2026, 1, 1),
            effective_to=None,
        )
        db.add(norm)
        db.commit()
        
        yield_rate = costing_ports.get_norm(norm_key="yield_rate", context={})
        assert yield_rate == 0.98
        
        db.delete(norm)
        db.commit()
    finally:
        db.close()


def test_seam_09_lookup_not_found():
    from app.services.norm_service import NormNotFoundError
    with pytest.raises(NormNotFoundError):
        costing_ports.get_norm(norm_key="yield_rate", context={"quantity": 99999})



# --- SEAM-10 — specs máy (MachineSpec) -------------------------------------
def test_seam_10_machine_spec_lookup(client):
    from app.db import SessionLocal
    from app.models.machine import Machine
    from sqlalchemy import select
    
    db = SessionLocal()
    try:
        machine = db.execute(select(Machine)).scalars().first()
        assert machine is not None
        
        spec = costing_ports.get_machine_spec(machine_id=machine.id)
        assert "units_per_pass" in spec
        assert spec["max_sheet_w"] == float(machine.max_width_cm or 0)
        assert spec["max_sheet_h"] == float(machine.max_height_cm or 0)
    finally:
        db.close()


# --- SEAM-11 — đọc Sản phẩm (ProductRead) ----------------------------------
@pytest.mark.skip(reason="SEAM-11 chờ đọc Sản phẩm (ProductRead)")
def test_seam_11_product_read():
    product = costing_ports.get_product_for_costing(product_id=1)
    assert "components" in product


def test_seam_11_stub_raises():
    with pytest.raises(NotImplementedError, match="SEAM-11"):
        costing_ports.get_product_for_costing(product_id=1)


# --- SEAM-12 — đơn giá NCC gia công (OutsourcePrice) -----------------------
@pytest.mark.skip(reason="SEAM-12 chờ đơn giá NCC gia công (OutsourcePrice)")
def test_seam_12_outsource_price_lookup():
    price = costing_ports.get_outsource_price(operation_key="be", supplier_id=1)
    assert isinstance(price, (int, float))


def test_seam_12_stub_raises():
    with pytest.raises(NotImplementedError, match="SEAM-12"):
        costing_ports.get_outsource_price(operation_key="be", supplier_id=1)
