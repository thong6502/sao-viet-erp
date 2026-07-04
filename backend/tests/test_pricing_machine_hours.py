"""Máy móc — engine áp công thức giờ máy hạt (setup base/màu + vệ sinh + đổi kẽm) + fallback.

Khẳng định: khi máy khai setup_time_*_hour → engine dùng công thức hạt; khi = 0 → fallback về
(setup_time_mins + changeover)/60 (đúng hành vi cũ). Self-contained (own in-memory DB).
"""
from datetime import date

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base
import app.models  # noqa: F401
from app.models.material import Material, MaterialCost
from app.models.machine import Machine, MachineRate
from app.models.plate_die_rate import PlateDieRate
from app.models.imposition_type import ImpositionType
from app.services.pricing_engine import PricingEngine


def _db():
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(eng)
    db = sessionmaker(bind=eng)()
    m = Material(code="P1", name="Giay", material_type="paper", unit="to", width_cm=79, height_cm=109, gsm=150)
    db.add(m); db.flush()
    db.add(MaterialCost(material_id=m.id, price_unit="to", unit_price=5000, effective_from=date(2025, 1, 1)))
    db.add(PlateDieRate(code="PLATE_T", name="Kẽm test", plate_type="ban_kem_offset", technology="offset", unit="ban", unit_price=100000, effective_from=date(2025, 1, 1)))
    db.add(ImpositionType(code="ONE_SIDE", name="In 1 mặt", sides=1, finished_factor=1.0, pass_count=1, plate_set_factor=1.0, ink_pass_factor=1.0))
    db.commit()
    return db, m.id


def _machine(db, **over):
    base = dict(code="M1", name="May", machine_type="offset", process_type="in",
                speed=6000, speed_unit="to/gio", num_ink_units=8, supports_perfecting=False)
    base.update(over)
    mc = Machine(**base)
    db.add(mc); db.flush()
    db.add(MachineRate(machine_id=mc.id, hourly_rate=1_000_000, effective_from=date(2025, 1, 1)))
    db.commit()
    return mc


def _run(db, mid, mcid, qty=6000):
    spec = dict(product_type="test", colors=4, sides=1, forms=1, material_id=mid, machine_id=mcid,
                sheet_w=79, sheet_h=109, pieces_per_sheet=1, imposition="ONE_SIDE", operations=[])
    lines, total, warns = PricingEngine(db).calculate_option(spec, qty)
    machine = next(l for l in lines if l.category == "machine")
    return float(machine.calculation_snapshot_json["machine_hours"]), float(machine.calculation_snapshot_json["setup_hours"])


def test_granular_setup_formula():
    db, mid = _db()
    # setup = base 0.5 + per_color 0.1×4 + cleaning 0.25 + plate_change 0.05×(4×1×1) = 1.35h
    mc = _machine(db, setup_time_base_hour=0.5, setup_time_per_color_hour=0.1,
                  cleaning_time_hour=0.25, plate_change_time_per_plate_hour=0.05,
                  rounding_hour_policy="0.01")
    hours, setup = _run(db, mid, mc.id)
    assert abs(setup - 1.35) < 1e-6, setup
    # run ~ tổng tờ / 6000 (tổng tờ ≥ 6000 do bù hao) → machine_hours = setup + run > 1.35
    assert hours > 1.35


def test_fallback_to_minutes_when_no_granular():
    db, mid = _db()
    mc = _machine(db, setup_time_mins=30, changeover_time_mins=0)  # không khai giờ hạt
    _, setup = _run(db, mid, mc.id)
    assert abs(setup - 0.5) < 1e-6, setup  # 30 phút = 0.5 giờ (đúng hành vi cũ)
