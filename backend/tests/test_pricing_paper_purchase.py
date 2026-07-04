"""Lát 8 — số tờ 3 lớp (lý thuyết → sản xuất → mua giấy) + mua giấy dùng Khổ giấy.

Khi khổ giấy mua (purchase_sheet_w/h) lớn hơn khổ tờ in, mỗi tờ mua cắt ra nhiều tờ in
→ số tờ mua = ⌈số tờ SX / số tờ in mỗi tờ mua⌉. Không khai khổ mua ⇒ mua = SX (hành vi cũ).
Self-contained; không phụ thuộc seed.
"""
import math
from datetime import date

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base
from app.models.material import Material, MaterialCost
from app.models.machine import Machine, MachineRate
from app.services.pricing_engine import PricingEngine


def _engine_and_ids():
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(eng)
    db = sessionmaker(bind=eng)()
    m = Material(code="P1", name="Giay", material_type="paper", unit="to",
                 width_cm=60, height_cm=84, gsm=150)
    db.add(m)
    db.flush()
    db.add(MaterialCost(material_id=m.id, price_unit="to", unit_price=5000, effective_from=date(2025, 1, 1)))
    mc = Machine(code="M1", name="May", machine_type="offset", process_type="in", speed=5000,
                 speed_unit="to/gio", setup_time_mins=0, changeover_time_mins=0,
                 setup_waste_sheets=0, num_ink_units=8)
    db.add(mc)
    db.flush()
    db.add(MachineRate(machine_id=mc.id, hourly_rate=0, effective_from=date(2025, 1, 1)))
    db.commit()
    return db, m.id, mc.id


def _mat(db, mid, mcid, purchase=None):
    spec = dict(product_type="test", colors=4, sides=1, forms=1, material_id=mid, machine_id=mcid,
                sheet_w=30, sheet_h=42, pieces_per_sheet=4, operations=[])
    if purchase:
        spec["purchase_sheet_w"], spec["purchase_sheet_h"] = purchase
    lines, total, warns = PricingEngine(db).calculate_option(spec, 10000)
    mat = next(l for l in lines if l.category == "material")
    snap = mat.calculation_snapshot_json
    return snap["production_sheets"], snap["purchase_sheets"], snap["press_per_purchase"], mat.total_cost


def test_purchase_sheets_default_equals_production():
    db, mid, mcid = _engine_and_ids()
    prod, purch, ppp, cost = _mat(db, mid, mcid)  # không khai khổ mua
    assert ppp == 1
    assert purch == prod  # khổ mua = khổ in ⇒ số tờ mua = số tờ SX (giữ nguyên hành vi cũ)


def test_purchase_sheets_precut_from_bigger_sheet():
    db, mid, mcid = _engine_and_ids()
    prod0, _, _, cost0 = _mat(db, mid, mcid)                    # press 30×42, mua = SX
    prod, purch, ppp, cost = _mat(db, mid, mcid, (60, 84))      # mua 60×84 cắt 4 tờ in 30×42
    assert prod == prod0
    assert ppp == 4                          # (60//30) × (84//42) = 2 × 2
    assert purch == math.ceil(prod / 4)      # số tờ mua = ⌈SX / 4⌉
    assert cost < cost0                       # ít tờ giấy mua hơn ⇒ rẻ hơn
