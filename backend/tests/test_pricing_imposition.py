"""Lát 7 — engine reads DM Kiểu bình bài (imposition) coefficients.

Locks in that PricingEngine applies finished_factor / plate_set_factor /
pass_count / ink_pass_factor from the ImpositionType catalog:
  - Số bộ kẽm = plate_set_factor  →  kẽm(Tự trở) = ½ kẽm(Trở nhíp).
  - Hệ số thành phẩm (con÷2 cho Tự trở) → cần nhiều tờ hơn Trở nhíp.
Self-contained (own in-memory DB); does not depend on the seed.

NOTE: "Tự trở" hệ số (con÷2, kẽm÷2, lượt×2) là công thức TẠM theo DATA_CONTRACTS —
chờ phiếu NextPrint thật để nghiệm thu lại. Test này chỉ khẳng định engine ÁP hệ số
từ danh mục đúng, không khẳng định con số khớp phiếu thực tế.
"""
from datetime import date

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base
from app.models.material import Material, MaterialCost
from app.models.machine import Machine, MachineRate
from app.models.plate_die_rate import PlateDieRate
from app.models.imposition_type import ImpositionType
from app.services.pricing_engine import PricingEngine


def _build_db():
    eng = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(eng)
    db = sessionmaker(bind=eng)()

    m = Material(code="P1", name="Giay test", material_type="paper", unit="to",
                 width_cm=79, height_cm=109, gsm=150)
    db.add(m)
    db.flush()
    db.add(MaterialCost(material_id=m.id, price_unit="to", unit_price=5000,
                        effective_from=date(2025, 1, 1)))
    mc = Machine(code="M1", name="May offset", machine_type="offset", process_type="in",
                 speed=5000, speed_unit="to/gio", setup_time_mins=0, changeover_time_mins=0,
                 setup_waste_sheets=0, num_ink_units=8, supports_perfecting=False)
    db.add(mc)
    db.flush()
    db.add(MachineRate(machine_id=mc.id, hourly_rate=1_000_000, effective_from=date(2025, 1, 1)))
    db.add(PlateDieRate(code="PLATE_T", name="Kẽm test", plate_type="ban_kem_offset",
                        technology="offset", unit="ban",
                        unit_price=100_000, effective_from=date(2025, 1, 1)))
    rows = [
        ("KB001", "In 1 mặt", 1, 1.0, 1, 1.0, 1.0),
        ("KB002", "Tự trở", 2, 0.5, 2, 1.0, 2.0),
        ("KB003", "Trở nhíp", 2, 1.0, 2, 2.0, 2.0),
    ]
    for code, name, sides, fin, passc, plate, ink in rows:
        db.add(ImpositionType(code=code, name=name, sides=sides, finished_factor=fin,
                              pass_count=passc, plate_set_factor=plate, ink_pass_factor=ink,
                              allow_rotate=True))
    db.commit()
    return db, m.id, mc.id


def _run(db, material_id, machine_id, impo, sides):
    spec = dict(product_type="test", colors=4, sides=sides, forms=1,
                material_id=material_id, machine_id=machine_id, sheet_w=79, sheet_h=109,
                pieces_per_sheet=4, imposition=impo, operations=[])
    lines, total, warns = PricingEngine(db).calculate_option(spec, 10000)
    plate = next((l for l in lines if l.category == "plate_die"), None)
    material = next((l for l in lines if l.category == "material"), None)
    machine = next((l for l in lines if l.category == "machine"), None)
    assert plate is not None and material is not None and machine is not None
    blocking = [w for w in warns if w.get("severity") == "blocking_error"]
    assert not blocking, blocking
    return (int(plate.quantity),
            int(material.calculation_snapshot_json["total_sheets"]),
            int(machine.total_cost))


def test_imposition_plate_sets_and_finished_factor():
    db, mid, mcid = _build_db()

    one_kem, one_sheets, _ = _run(db, mid, mcid, "In 1 mặt", 1)
    turn_kem, turn_sheets, _ = _run(db, mid, mcid, "Tự trở", 2)
    tumble_kem, tumble_sheets, _ = _run(db, mid, mcid, "Trở nhíp", 2)

    # Số bộ kẽm = màu × plate_set_factor × forms
    assert one_kem == 4          # 4 × 1 × 1
    assert turn_kem == 4         # 4 × 1 × 1  (tự trở 1 bộ kẽm)
    assert tumble_kem == 8       # 4 × 2 × 1  (trở nhíp 2 bộ kẽm)
    # Headline: kẽm Tự trở = ½ kẽm Trở nhíp
    assert turn_kem * 2 == tumble_kem

    # Hệ số thành phẩm: Tự trở con÷2 ⇒ số con/tờ giảm một nửa ⇒ số tờ in ~gấp đôi.
    # (Trở nhíp giữ finished_factor=1 nên số con không đổi; chênh makeready theo số mặt là
    #  hành vi cũ, không thuộc phạm vi bình bài.)
    assert turn_sheets > tumble_sheets * 1.8


def test_perfecting_press_no_side_pass():
    """Máy in trở tự động (perfecting): job 2 mặt chạy 1 lượt qua máy → giờ máy KHÔNG nhân 2."""
    from app.models.machine import Machine, MachineRate

    db, mid, mcid = _build_db()
    mp = Machine(code="M2", name="May tro tu dong", machine_type="offset", process_type="in",
                 speed=5000, speed_unit="to/gio", setup_time_mins=0, changeover_time_mins=0,
                 setup_waste_sheets=0, num_ink_units=8, supports_perfecting=True)
    db.add(mp)
    db.flush()
    db.add(MachineRate(machine_id=mp.id, hourly_rate=1_000_000, effective_from=date(2025, 1, 1)))
    db.commit()

    _, _, cost_normal = _run(db, mid, mcid, "Trở nhíp", 2)   # máy thường: giờ máy ×2 lượt
    _, _, cost_perf = _run(db, mid, mp.id, "Trở nhíp", 2)    # máy perfecting: ×1 lượt
    assert cost_perf < cost_normal
