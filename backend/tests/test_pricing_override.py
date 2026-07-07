"""§12 — Sửa tay (override) tổng tiền từng dòng, kèm lý do bắt buộc.

Khẳng định: input_spec["overrides"]=[{target:"line:<cat>",value,reason}] thay tổng tiền dòng đó,
lưu giá gốc + lý do vào snapshot; thiếu lý do ⇒ blocking_error. Self-contained in-memory DB.
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
from app.services.pricing_engine import PricingEngine


def _db():
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(eng)
    db = sessionmaker(bind=eng)()
    m = Material(code="P1", name="Giay", material_type="paper", unit="to", width_cm=79, height_cm=109, gsm=150)
    db.add(m); db.flush()
    db.add(MaterialCost(material_id=m.id, price_unit="to", unit_price=5000, effective_from=date(2025, 1, 1)))
    db.add(PlateDieRate(code="PLATE_T", name="Kẽm test", plate_type="ban_kem_offset", technology="offset",
                        unit="ban", unit_price=100000, effective_from=date(2025, 1, 1)))
    mc = Machine(code="M1", name="May", machine_type="offset", process_type="in", speed=6000,
                 speed_unit="to/gio", num_ink_units=8)
    db.add(mc); db.flush()
    db.add(MachineRate(machine_id=mc.id, hourly_rate=1_000_000, effective_from=date(2025, 1, 1)))
    db.commit()
    return db, m.id, mc.id


def _spec(mid, mcid, overrides=None):
    return dict(product_type="test", colors=4, sides=1, forms=1, material_id=mid, machine_id=mcid,
                sheet_w=79, sheet_h=109, pieces_per_sheet=4, operations=[],
                overrides=overrides or [])


def test_override_replaces_line_total_with_reason():
    db, mid, mcid = _db()
    base_lines, base_total, _ = PricingEngine(db).calculate_option(_spec(mid, mcid), 10000)
    machine_before = next(l for l in base_lines if l.category == "machine")

    ov = [{"target": "line:machine", "value": 123456, "reason": "chốt theo ca máy thực tế"}]
    lines, total, warns = PricingEngine(db).calculate_option(_spec(mid, mcid, ov), 10000)
    machine = next(l for l in lines if l.category == "machine")
    assert float(machine.total_cost) == 123456
    assert machine.calculation_snapshot_json["override_reason"] == "chốt theo ca máy thực tế"
    assert float(machine.calculation_snapshot_json["override_original"]) == float(machine_before.total_cost)
    assert "[SỬA TAY]" in (machine.note or "")
    # tổng phản ánh số sửa tay
    assert abs(total - (base_total - float(machine_before.total_cost) + 123456)) < 1.0


def test_override_missing_reason_is_blocking():
    db, mid, mcid = _db()
    ov = [{"target": "line:machine", "value": 100000, "reason": ""}]
    lines, total, warns = PricingEngine(db).calculate_option(_spec(mid, mcid, ov), 10000)
    assert any(w["code"] == "OVERRIDE_NO_REASON" and w["severity"] == "blocking_error" for w in warns)
    # không áp khi thiếu lý do
    machine = next(l for l in lines if l.category == "machine")
    assert float(machine.total_cost) != 100000


def test_override_production_sheets_cascades():
    """§12 nâng cao — override số tờ SX phải cascade sang giấy + công in (giảm tờ ⇒ giảm tiền)."""
    db, mid, mcid = _db()
    base_lines, _, _ = PricingEngine(db).calculate_option(_spec(mid, mcid), 10000)
    base_paper = float(next(l for l in base_lines if l.category == "material").total_cost)

    spec = _spec(mid, mcid)
    spec["override_production_sheets"] = {"value": 100, "reason": "chốt theo lệnh sản xuất"}
    lines, _, warns = PricingEngine(db).calculate_option(spec, 10000)
    paper = float(next(l for l in lines if l.category == "material").total_cost)
    assert any(w["code"] == "OVERRIDE_PRODUCTION_SHEETS" for w in warns)
    assert paper < base_paper  # ít tờ hơn ⇒ giấy rẻ hơn (cascade)


def test_override_material_unit_price():
    """§12 nâng cao — override đơn giá vật tư thay đơn giá/tờ."""
    db, mid, mcid = _db()
    spec = _spec(mid, mcid)
    spec["override_material_unit_price"] = {"value": 99, "reason": "giá giấy NCC mới"}
    lines, _, warns = PricingEngine(db).calculate_option(spec, 10000)
    mat = next(l for l in lines if l.category == "material")
    assert any(w["code"] == "OVERRIDE_MATERIAL_PRICE" for w in warns)
    assert abs(float(mat.unit_cost) - 99) < 1e-6
