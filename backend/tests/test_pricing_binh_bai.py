"""P6 — pricing_engine dùng Quy tắc bình bài khi spec khai `imposition_rule_id`.

Gate: có rule (step_repeat/nesting) → số con/kẽm theo engine bình bài; không rule → giữ
hành vi hình học cũ (các test pricing khác không đổi = golden safety)."""
from __future__ import annotations

from datetime import date

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401  (đăng ký toàn bộ bảng cho create_all)
from app.db import Base
from app.models.material import Material, MaterialCost
from app.models.machine import Machine, MachineRate
from app.models.plate_die_rate import PlateDieRate
from app.models.quy_tac_binh_bai import QuyTacBinhBai, QuyTacBinhBaiVersion
from app.services.pricing_engine import PricingEngine


def _db():
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(eng)
    db = sessionmaker(bind=eng)()
    m = Material(code="P1", name="Giay", material_type="paper", unit="to",
                 width_cm=43, height_cm=65, gsm=150)
    db.add(m); db.flush()
    db.add(MaterialCost(material_id=m.id, price_unit="to", unit_price=5000, effective_from=date(2025, 1, 1)))
    mc = Machine(code="M1", name="May", machine_type="offset", process_type="in", speed=6000,
                 speed_unit="to/gio", num_ink_units=8, gripper_cm=1.2, max_width_cm=74, max_height_cm=105)
    db.add(mc); db.flush()
    db.add(MachineRate(machine_id=mc.id, hourly_rate=1_000_000, effective_from=date(2025, 1, 1)))
    db.add(PlateDieRate(code="PLATE_T", name="Kẽm test", plate_type="ban_kem_offset", technology="offset",
                        unit="ban", unit_price=100000, effective_from=date(2025, 1, 1)))
    # Rule step_repeat: side 5 / tail 8 / gutter 4 (mm) → golden §5.1 = 40 con.
    h = QuyTacBinhBai(ma="TEST-NUP", ten="Ấn phẩm phẳng test", trang_thai="active")
    db.add(h); db.flush()
    db.add(QuyTacBinhBaiVersion(rule_id=h.id, version_no=1, is_current=True, layout_mode="step_repeat",
                                side_margin_mm=5, tail_colorbar_mm=8, gutter_mm=4, bleed_default_mm=3,
                                allow_rotate=True))
    db.commit()
    return db, m.id, mc.id, h.id


def _spec(mid, mcid, rule_id=None):
    s = dict(colors=4, sides=2, forms=1, material_id=mid, machine_id=mcid,
             sheet_w=43, sheet_h=65, finished_width=9.0, finished_height=5.3,
             bleed_cm=0.2, operations=[])
    if rule_id is not None:
        s["imposition_rule_id"] = rule_id
    return s


def test_rule_drives_pieces_per_sheet():
    """Name card 90×53 (+2 bleed), tờ in 43×65, nhíp 12 → engine bình bài ra 40 con/tờ."""
    db, mid, mcid, rid = _db()
    lines, total, warns = PricingEngine(db).calculate_option(_spec(mid, mcid, rule_id=rid), 10000)
    blocking = [w for w in warns if w.get("severity") == "blocking_error"]
    assert not blocking, blocking
    assert any(w["code"] == "IMPOSITION_RULE" and "40 con" in w["message"] for w in warns), warns


def test_no_rule_keeps_geometric_no_warning():
    """Không khai imposition_rule_id → KHÔNG áp bình bài (giữ hành vi cũ)."""
    db, mid, mcid, _ = _db()
    lines, total, warns = PricingEngine(db).calculate_option(_spec(mid, mcid), 10000)
    assert not any(w["code"] == "IMPOSITION_RULE" for w in warns)


def test_rule_changes_sheet_count_vs_geometric():
    """Số con rule (40) khác hình học thô → số tờ giấy khác (chứng tỏ rule thực sự đổi giá)."""
    db, mid, mcid, rid = _db()

    def _mat_sheets(spec):
        lines, _t, _w = PricingEngine(db).calculate_option(spec, 10000)
        ml = next(l for l in lines if l.category == "material")
        return float(ml.quantity)

    with_rule = _mat_sheets(_spec(mid, mcid, rule_id=rid))
    without = _mat_sheets(_spec(mid, mcid))
    assert with_rule != without  # rule đổi số con → đổi số tờ giấy
