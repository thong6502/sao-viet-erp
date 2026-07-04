"""Engine khuôn (#5): Operation.tooling_rate_id → giá khuôn theo pricing_method của bảng giá.

fixed → unit_price (sàn min_charge); area → area_cm2 × đơn giá/cm² (sàn min); dùng lại →
maintenance_fee. Fallback tooling_unit_price cũ khi chưa link. Self-contained in-memory DB.
"""
from datetime import date

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base
import app.models  # noqa: F401
from app.models.material import Material, MaterialCost
from app.models.machine import Machine, MachineRate
from app.models.operation import Operation, OperationRate
from app.models.plate_die_rate import PlateDieRate
from app.services.pricing_engine import PricingEngine


def _setup():
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(eng)
    db = sessionmaker(bind=eng)()
    m = Material(code="P1", name="Giay", material_type="paper", unit="to",
                 width_cm=60, height_cm=84, gsm=150)
    db.add(m); db.flush()
    db.add(MaterialCost(material_id=m.id, price_unit="to", unit_price=5000, effective_from=date(2025, 1, 1)))
    mc = Machine(code="M1", name="May", machine_type="offset", process_type="in", speed=5000,
                 speed_unit="to/gio", setup_time_mins=0, changeover_time_mins=0, setup_waste_sheets=0)
    db.add(mc); db.flush()
    db.add(MachineRate(machine_id=mc.id, hourly_rate=0, effective_from=date(2025, 1, 1)))
    # kẽm để dòng plate resolve
    db.add(PlateDieRate(code="PL", name="Kẽm", plate_type="ban_kem_offset", technology="offset",
                        unit="ban", unit_price=100000, effective_from=date(2025, 1, 1)))
    # khuôn: fixed, area, reuse
    die_fixed = PlateDieRate(code="DIE_FIX", name="Bế cố định", plate_type="khuon_be",
                             technology="be", unit="bo", unit_price=800000, min_charge=500000,
                             pricing_method="fixed", effective_from=date(2025, 1, 1))
    die_area = PlateDieRate(code="DIE_AREA", name="Ép kim area", plate_type="khuon_ep_kim",
                            technology="ep_kim", unit="cm2", unit_price=0, unit_price_area=2000,
                            min_charge=300000, pricing_method="area", effective_from=date(2025, 1, 1))
    die_reuse = PlateDieRate(code="DIE_REUSE", name="Bế dùng lại", plate_type="khuon_be",
                             technology="be", unit="bo", unit_price=800000,
                             pricing_method="fixed", reusable=True,
                             reuse_price_method="maintenance_fee", maintenance_fee=100000,
                             effective_from=date(2025, 1, 1))
    db.add_all([die_fixed, die_area, die_reuse]); db.flush()

    def _op(code, name, otype, rate_id):
        op = Operation(code=code, name=name, operation_type=otype, unit="to",
                       has_tooling=True, tooling_rate_id=rate_id)
        db.add(op); db.flush()
        db.add(OperationRate(operation_id=op.id, run_rate=0, effective_from=date(2025, 1, 1)))
        return op.id
    ids = {
        "fixed": _op("OP_FIX", "Bế", "be", die_fixed.id),
        "area": _op("OP_AREA", "Ép kim", "ep_kim", die_area.id),
        "reuse": _op("OP_REUSE", "Bế lại", "be", die_reuse.id),
    }
    # op chưa link (fallback tooling_unit_price cũ)
    op_fb = Operation(code="OP_FB", name="Bế fallback", operation_type="be", unit="to",
                      has_tooling=True, tooling_rate_id=None)
    db.add(op_fb); db.flush()
    db.add(OperationRate(operation_id=op_fb.id, run_rate=0, tooling_unit_price=444000,
                         effective_from=date(2025, 1, 1)))
    ids["fallback"] = op_fb.id
    db.commit()
    return db, m.id, mc.id, ids


def _op_cost(db, mid, mcid, op_spec):
    spec = dict(product_type="test", colors=4, sides=1, forms=1, material_id=mid, machine_id=mcid,
                sheet_w=30, sheet_h=42, pieces_per_sheet=4, operations=[op_spec])
    lines, total, warns = PricingEngine(db).calculate_option(spec, 10000)
    op_line = next(l for l in lines if l.category in ("operation", "packing"))
    return op_line.total_cost, op_line.calculation_snapshot_json.get("tooling_cost")


def test_die_fixed_applies_min_charge():
    db, mid, mcid, ids = _setup()
    total, tooling = _op_cost(db, mid, mcid, {"operation_id": ids["fixed"], "sequence": 10, "execution_mode": "internal"})
    assert tooling == 800000.0 and total == 800000.0  # fixed 800k > min 500k


def test_die_area_times_price_floored():
    db, mid, mcid, ids = _setup()
    total, tooling = _op_cost(db, mid, mcid,
                              {"operation_id": ids["area"], "sequence": 10, "execution_mode": "internal",
                               "tooling_area_cm2": 120})
    assert tooling == 300000.0  # 120×2000=240k < min 300k → 300k


def test_die_reuse_maintenance_fee():
    db, mid, mcid, ids = _setup()
    total, tooling = _op_cost(db, mid, mcid,
                              {"operation_id": ids["reuse"], "sequence": 10, "execution_mode": "internal",
                               "tooling_reuse": True})
    assert tooling == 100000.0  # dùng lại → phí bảo trì


def test_tooling_fallback_when_no_link():
    db, mid, mcid, ids = _setup()
    total, tooling = _op_cost(db, mid, mcid, {"operation_id": ids["fallback"], "sequence": 10, "execution_mode": "internal"})
    assert tooling == 444000.0  # chưa link → tooling_unit_price cũ trên OperationRate
