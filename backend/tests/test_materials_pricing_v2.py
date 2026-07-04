"""Tests tái thiết kế danh mục #2 — Vật tư & Đơn giá (mực-từ-material, bậc giá, quy đổi, API).

Cố ý KHÔNG dựng PlateDieRate (đang được session khác tái thiết kế) — dùng DB in-memory riêng.
"""
from __future__ import annotations

import math
from datetime import date

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base
from app.models.material import Material, MaterialCost
from app.models.machine import Machine, MachineRate
from app.services.pricing_engine import PricingEngine


def _mem_db():
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(eng)
    return sessionmaker(bind=eng)()


def _base_setup(db):
    paper = Material(code="P1", name="Giay", material_type="paper", material_group="paper",
                     unit="to", width_cm=79, height_cm=109, gsm=150)
    db.add(paper)
    db.flush()
    db.add(MaterialCost(material_id=paper.id, price_unit="to", unit_price=1000, effective_from=date(2025, 1, 1)))
    mc = Machine(code="M1", name="May", machine_type="offset", process_type="in", speed=8000,
                 speed_unit="to/gio", setup_time_mins=0, changeover_time_mins=0, setup_waste_sheets=0, num_ink_units=8)
    db.add(mc)
    db.flush()
    db.add(MachineRate(machine_id=mc.id, hourly_rate=0, effective_from=date(2025, 1, 1)))
    db.commit()
    return paper, mc


def test_ink_cost_from_material():
    """Mực đọc từ material nhóm 'ink' giá nghin_luot (không còn norm)."""
    db = _mem_db()
    paper, mc = _base_setup(db)
    ink = Material(code="INK1", name="Mực offset CMYK", material_type="chemical",
                   material_group="ink", unit="kg", ink_type="offset", ink_color_system="CMYK")
    db.add(ink)
    db.flush()
    db.add(MaterialCost(material_id=ink.id, price_unit="nghin_luot", unit_price=500, effective_from=date(2025, 1, 1)))
    db.commit()

    spec = dict(product_type="tor_roi", colors=4, sides=1, forms=1, material_id=paper.id, machine_id=mc.id,
                sheet_w=79, sheet_h=109, pieces_per_sheet=4, operations=[], imposition="In 1 mặt")
    lines, total, warns = PricingEngine(db).calculate_option(spec, 1000)
    ink_lines = [l for l in lines if l.category == "ink"]
    assert len(ink_lines) == 1, "phải có 1 dòng mực đọc từ material"
    il = ink_lines[0]
    # impressions = total_sheets × colors × ink_pass(1 mặt=1); tiền = ceil(impr/1000) × 500
    impr = il.calculation_snapshot_json["impressions"]
    assert float(il.total_cost) == math.ceil(impr / 1000) * 500
    assert il.source_type == "material_costs"
    assert il.source_snapshot_json["name"] == "Mực offset CMYK"
    assert not any(w["code"] == "MISSING_INK_RATE" for w in warns)
    db.close()


def test_ink_missing_when_no_ink_material():
    """Không có material mực → cảnh báo, không có dòng mực (như trước khi cấu hình)."""
    db = _mem_db()
    paper, mc = _base_setup(db)
    spec = dict(product_type="tor_roi", colors=4, sides=1, forms=1, material_id=paper.id, machine_id=mc.id,
                sheet_w=79, sheet_h=109, pieces_per_sheet=4, operations=[], imposition="In 1 mặt")
    lines, total, warns = PricingEngine(db).calculate_option(spec, 1000)
    assert not any(l.category == "ink" for l in lines)
    assert any(w["code"] == "MISSING_INK_RATE" for w in warns)
    db.close()


def test_price_band_selection():
    """Engine chọn đơn giá theo bậc số tờ mua."""
    db = _mem_db()
    paper, mc = _base_setup(db)
    # Thêm 2 bậc cho giấy (to): ≤200 tờ = 1200, >200 = 900. Dòng no-band 1000 vẫn còn nhưng bậc
    # được ưu tiên hơn (band_ok + sort ưu tiên bậc cụ thể).
    db.add(MaterialCost(material_id=paper.id, price_unit="to", unit_price=1200,
                        quantity_from=0, quantity_to=200, effective_from=date(2025, 1, 1)))
    db.add(MaterialCost(material_id=paper.id, price_unit="to", unit_price=900,
                        quantity_from=200, quantity_to=None, effective_from=date(2025, 1, 1)))
    db.commit()

    # SL nhỏ → số tờ mua nhỏ (≤200) → giá 1200; SL lớn → >200 → giá 900.
    spec = dict(product_type="tor_roi", colors=4, sides=1, forms=1, material_id=paper.id, machine_id=mc.id,
                sheet_w=79, sheet_h=109, pieces_per_sheet=100, operations=[], imposition="In 1 mặt")
    lines_small, _, _ = PricingEngine(db).calculate_option(spec, 1000)   # ~10 tờ
    lines_large, _, _ = PricingEngine(db).calculate_option(spec, 100000)  # ~1000 tờ
    mat_small = next(l for l in lines_small if l.category == "material")
    mat_large = next(l for l in lines_large if l.category == "material")
    assert float(mat_small.unit_cost) == 1200
    assert float(mat_large.unit_cost) == 900
    db.close()


# --- API tests (client fixture; plate_die không seed ở test nên không bị ảnh hưởng) ---

def test_api_material_new_fields_and_price_variants(client, seed_credentials):
    tok = client.post("/api/auth/login", json=seed_credentials).json()["access_token"]
    h = {"Authorization": f"Bearer {tok}"}

    # Tạo giấy với field mới.
    r = client.post("/api/materials", json={
        "name": "Ivory 250 test #2", "material_type": "paper", "unit": "to",
        "gsm": 250, "width_cm": 79, "height_cm": 109, "paper_family": "Ivory",
        "material_group": "paper", "default_supplier": "NCC Giấy A",
        "base_uom": "kg", "purchase_uom": "kg", "consumption_uom": "to",
        "conversion_method": "gsm_area",
    }, headers=h)
    assert r.status_code == 201, r.text
    mat = r.json()
    assert mat["material_group"] == "paper"
    assert mat["default_supplier"] == "NCC Giấy A"
    mid = mat["id"]

    # Thêm 2 bậc giá kg (khác bậc) + NCC — không chồng lấn.
    for qf, qt, price in [(0, 100, 32000), (100, None, 30000)]:
        r = client.post(f"/api/materials/{mid}/costs", json={
            "price_unit": "kg", "unit_price": price, "effective_from": str(date.today()),
            "supplier": "NCC Giấy A", "quantity_from": qf, "quantity_to": qt,
            "price_type": "purchase", "transport_fee": 300000, "moq": 100, "lead_time_days": 2,
        }, headers=h)
        assert r.status_code == 201, r.text
    row = client.get(f"/api/materials/{mid}", headers=h).json()
    assert len([c for c in row["costs"] if c["price_unit"] == "kg"]) == 2

    # Cost history.
    r = client.get(f"/api/materials/{mid}/costs/history", headers=h)
    assert r.status_code == 200 and len(r.json()) >= 2


def test_api_kg_requires_gsm(client, seed_credentials):
    tok = client.post("/api/auth/login", json=seed_credentials).json()["access_token"]
    h = {"Authorization": f"Bearer {tok}"}
    # Giấy KHÔNG có gsm nhưng thêm giá kg → 422 (§12).
    r = client.post("/api/materials", json={
        "name": "Giấy no-gsm test", "material_type": "paper", "unit": "to",
        "width_cm": 79, "height_cm": 109, "paper_family": "Ford",
    }, headers=h)
    mid = r.json()["id"]
    r = client.post(f"/api/materials/{mid}/costs", json={
        "price_unit": "kg", "unit_price": 30000, "effective_from": str(date.today()),
    }, headers=h)
    assert r.status_code == 422
    assert "gsm" in r.json()["detail"].lower()


def test_api_convert_and_price_test(client, seed_credentials):
    tok = client.post("/api/auth/login", json=seed_credentials).json()["access_token"]
    h = {"Authorization": f"Bearer {tok}"}
    # Quy đổi khổ 79×109, gsm 150 → kg/tờ ≈ 0.1292.
    r = client.post("/api/materials/convert", json={"gsm": 150, "width_cm": 79, "height_cm": 109}, headers=h)
    assert r.status_code == 200
    assert abs(r.json()["kg_per_sheet"] - 0.1292) < 0.001

    # Test tiền mực: 2400 lượt, 80.000/1.000 → 3 block × 80.000 = 240.000.
    r = client.post("/api/materials/price-test", json={
        "price_unit": "nghin_luot", "unit_price": 80000, "impressions": 2400,
    }, headers=h)
    assert r.status_code == 200
    assert r.json()["total"] == 240000

    # Test tiền giấy theo kg: 500 tờ × 0.1292 × 28.000 ≈ 1.808.800.
    r = client.post("/api/materials/price-test", json={
        "price_unit": "kg", "unit_price": 28000, "sheets": 500, "gsm": 150, "width_cm": 79, "height_cm": 109,
    }, headers=h)
    assert r.status_code == 200
    assert abs(r.json()["total"] - 1808800) < 2000
