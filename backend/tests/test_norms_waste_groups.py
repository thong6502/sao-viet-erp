"""Tests cho tái thiết kế danh mục #7 — Định mức & Bù hao (waste_group + chuỗi mới)."""
from __future__ import annotations

import math
from datetime import date

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base
from app.models.material import Material, MaterialCost
from app.models.machine import Machine, MachineRate
from app.models.norm import Norm
from app.repositories.norm_repo import NormRepository
from app.repositories.audit_repo import AuditLogRepository
from app.services.norm_service import NormService, NormLookupContext
from app.services.pricing_engine import (
    PricingEngine,
    _compute_setup_sheets,
    _compute_running_sheets,
    _compute_paper_extra,
)


class MockActor:
    id = 1


# --- Helper: đơn vị công thức nhóm ------------------------------------------

def test_setup_combined_and_clamp():
    n = Norm(norm_key="makeready_per_color_side", waste_group="SETUP_WASTE",
             calculation_method="COMBINED", value=0,
             setup_waste_qty=100, setup_waste_per_color=30, setup_waste_per_side=50,
             min_waste_qty=100, max_waste_qty=1000, context_key="{}",
             effective_from=date(2026, 1, 1))
    # 100 + 30×4 + 50×2 = 320
    assert _compute_setup_sheets(n, colors=4, sides=2) == 320
    # clamp max
    n.max_waste_qty = 200
    assert _compute_setup_sheets(n, colors=4, sides=2) == 200


def test_setup_legacy_per_color_side():
    n = Norm(norm_key="makeready_per_color_side", waste_group="SETUP_WASTE",
             calculation_method="PER_COLOR_SIDE", value=15, context_key="{}",
             effective_from=date(2026, 1, 1))
    assert _compute_setup_sheets(n, colors=4, sides=2) == 120


def test_running_additive_with_min_clamp():
    n = Norm(norm_key="running_waste_pct", waste_group="RUNNING_WASTE",
             calculation_method="PERCENT", value=0.03, min_waste_qty=20,
             context_key="{}", effective_from=date(2026, 1, 1))
    # ceil(258 × 3%) = 8 → nhưng min 20 → 20
    assert _compute_running_sheets(n, 258) == 20
    # base lớn: ceil(2000 × 3%) = 60
    assert _compute_running_sheets(n, 2000) == 60


def test_paper_extra_methods():
    pct = Norm(norm_key="paper_extra_waste", waste_group="PAPER_EXTRA_WASTE",
               calculation_method="PERCENT", value=0.01, context_key="{}",
               effective_from=date(2026, 1, 1))
    assert _compute_paper_extra(pct, 486) == math.ceil(486 * 0.01)  # 5
    fixed = Norm(norm_key="paper_extra_waste", waste_group="PAPER_EXTRA_WASTE",
                 calculation_method="FIXED", value=10, context_key="{}",
                 effective_from=date(2026, 1, 1))
    assert _compute_paper_extra(fixed, 486) == 10
    ream = Norm(norm_key="paper_extra_waste", waste_group="PAPER_EXTRA_WASTE",
                calculation_method="PER_REAM", value=5, context_key="{}",
                effective_from=date(2026, 1, 1))
    assert _compute_paper_extra(ream, 1000) == 5 * (1000 / 500)  # 10


# --- Chuỗi engine đầy đủ khớp ví dụ spec §4.2 (486 tờ SX, 491 tờ mua) -------

def _mem_db():
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(eng)
    return sessionmaker(bind=eng)()


def test_full_chain_matches_spec_example():
    db = _mem_db()
    paper = Material(code="P", name="Giay", material_type="paper", unit="to",
                     width_cm=79, height_cm=109, gsm=150)
    db.add(paper)
    db.flush()
    db.add(MaterialCost(material_id=paper.id, price_unit="to", unit_price=1000, effective_from=date(2025, 1, 1)))
    mc = Machine(code="M", name="May", machine_type="offset", process_type="in", speed=8000,
                 speed_unit="to/gio", setup_time_mins=0, changeover_time_mins=0, setup_waste_sheets=0, num_ink_units=8)
    db.add(mc)
    db.flush()
    db.add(MachineRate(machine_id=mc.id, hourly_rate=0, effective_from=date(2025, 1, 1)))
    # Định mức khâu in: đạt 97%, makeready 100 + 30/màu, running 3%; hao giấy 1%.
    db.add(Norm(norm_key="yield_rate", waste_group="YIELD_RATE", calculation_method="PERCENT",
                value=0.97, context_key="{}", effective_from=date(2025, 1, 1), code="YIELD_IN"))
    db.add(Norm(norm_key="makeready_per_color_side", waste_group="SETUP_WASTE", calculation_method="COMBINED",
                value=0, setup_waste_qty=100, setup_waste_per_color=30, setup_waste_per_side=0,
                context_key="{}", effective_from=date(2025, 1, 1), code="MR_IN"))
    db.add(Norm(norm_key="running_waste_pct", waste_group="RUNNING_WASTE", calculation_method="PERCENT",
                value=0.03, context_key="{}", effective_from=date(2025, 1, 1), code="RW_IN"))
    db.add(Norm(norm_key="paper_extra_waste", waste_group="PAPER_EXTRA_WASTE", calculation_method="PERCENT",
                value=0.01, context_key="{}", effective_from=date(2025, 1, 1), code="PAPER"))
    db.commit()

    spec = dict(product_type="tor_roi", colors=4, sides=2, forms=1, material_id=paper.id, machine_id=mc.id,
                sheet_w=79, sheet_h=109, pieces_per_sheet=4, operations=[])
    lines, total, warns = PricingEngine(db).calculate_option(spec, 1000)
    assert not any(w["severity"] == "blocking_error" for w in warns), warns
    mat = next(l for l in lines if l.category == "material")
    snap = mat.calculation_snapshot_json
    # printed = ceil(1000/4) = 250; sau đạt = ceil(250/0.97) = 258
    assert snap["sheets_after_yield"] == 258
    # makeready = 100 + 30×4 = 220
    assert snap["makeready_sheets"] == 220
    # running = ceil(258 × 3%) = 8
    assert snap["running_waste_sheets"] == 8
    # SX = 258 + 220 + 8 = 486
    assert snap["production_sheets"] == 486
    # hao giấy = ceil(486 × 1%) = 5 → mua = 491
    assert snap["paper_extra_sheets"] == 5
    assert snap["purchase_sheets"] == 491
    # có diễn giải nêu rule
    labels = [n["label"] for n in snap["norms_applied"]]
    assert "Makeready" in labels and "Số tờ mua giấy" not in labels  # mua giấy nằm ngoài (block riêng)
    db.close()


# --- API: tạo bằng waste_group + Test + duplicate + history -----------------

def test_api_create_with_waste_group(client, seed_credentials):
    tok = client.post("/api/auth/login", json=seed_credentials).json()["access_token"]
    h = {"Authorization": f"Bearer {tok}"}
    payload = {
        "waste_group": "SETUP_WASTE", "calculation_method": "COMBINED",
        "code": "MR_TEST", "name": "Makeready test",
        "setup_waste_qty": 100, "setup_waste_per_color": 30, "setup_waste_per_side": 50,
        "min_waste_qty": 100, "max_waste_qty": 500,
        "effective_from": str(date.today()),
    }
    r = client.post("/api/norms", json=payload, headers=h)
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["waste_group"] == "SETUP_WASTE"
    assert body["norm_key"] == "makeready_per_color_side"
    assert body["setup_waste_per_color"] == 30
    norm_id = body["id"]

    # History
    r = client.get(f"/api/norms/{norm_id}/history", headers=h)
    assert r.status_code == 200 and r.json()["total"] >= 1

    # Test endpoint
    r = client.post("/api/norms/test", json={
        "quantity": 1000, "pieces_per_sheet": 4, "colors": 4, "sides": 2, "forms": 1,
        "operation_keys": [],
    }, headers=h)
    assert r.status_code == 200, r.text
    out = r.json()
    # makeready = clamp(100 + 30×4 + 50×2, 100, 500) = clamp(320) = 320
    assert out["makeready_sheets"] == 320
    assert out["production_sheets"] == out["sheets_after_yield"] + 320 + out["running_sheets"] - out["sheets_after_yield"]

    # Duplicate → version mới
    r = client.post(f"/api/norms/{norm_id}/duplicate", json={
        "effective_from": str(date.today().replace(day=28)), "code": "MR_TEST_V2",
    }, headers=h)
    assert r.status_code == 201, r.text
    assert r.json()["version"] == 2


def test_api_yield_bounds_and_min_max(client, seed_credentials):
    tok = client.post("/api/auth/login", json=seed_credentials).json()["access_token"]
    h = {"Authorization": f"Bearer {tok}"}
    # yield > 1 → 422
    r = client.post("/api/norms", json={"waste_group": "YIELD_RATE", "value": 1.5, "effective_from": str(date.today())}, headers=h)
    assert r.status_code == 422
    # min > max → 422
    r = client.post("/api/norms", json={
        "waste_group": "RUNNING_WASTE", "value": 0.03, "min_waste_qty": 500, "max_waste_qty": 20,
        "effective_from": str(date.today()),
    }, headers=h)
    assert r.status_code == 422
