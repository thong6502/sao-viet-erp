"""Golden-case test — phiếu ĐAI QUẤN THE FISSHER (NextPrint QUO-049/07).

Đóng băng công thức tính giá theo phiếu thật đã nghiệm thu tay
(xem docs/NGHIEM_THU_KHAY_CARTON.md). Assert theo GIÁ TRỊ CHUẨN SVN:
quyết định #1 (số tờ luôn ceil) ⇒ 6.667 tờ. Bù hao theo mô hình mới
(waste_pct ở Loại SP; ca này = 0) nên không cộng makeready.

Ca này: 6 màu / 1 mặt, giấy Duplex D400 khổ 68×101,50, gia công theo tờ.
Vì in 1 mặt nên số kẽm = màu×1×1 = 6 (trùng công thức cũ); công in đơn giá 0.
"""
from __future__ import annotations

from datetime import date
from app.db import SessionLocal
from app.models.material import Material, MaterialCost
from app.models.machine import Machine, MachineRate
from app.models.operation import Operation, OperationRate
from app.models.plate_die_rate import PlateDieRate
from app.models.norm import Norm
from app.services.pricing_engine import PricingEngine

import pytest


@pytest.fixture
def golden_setup(client):
    db = SessionLocal()

    # Giấy Duplex D400, khổ 68×101,50 — dùng giá /tờ để assert xác định
    # (đơn giá 5.384đ/tờ ≈ 19.500đ/kg × 0,276 kg/tờ; quy đổi kg test riêng).
    paper = Material(
        code="GY_D400", name="Duplex D400", material_type="paper",
        unit="to", width_cm=68.0, height_cm=101.5, gsm=400, is_active=True,
    )
    db.add(paper)
    db.flush()
    db.add(MaterialCost(
        material_id=paper.id, price_unit="to", unit_price=5384,
        effective_from=date(2026, 1, 1),
    ))

    # Máy HEIDELBERG 72×102 - 7 màu. Công in đơn giá 0 ở phiếu này (dồn vào giá khoán).
    # setup_waste_sheets=250 ⇒ makeready = 250 tờ (quyết định #3: SVN cấu hình).
    machine = Machine(
        code="M_HEIDEL_7", name="HEIDELBERG 72x102-7 MÀU",
        machine_type="offset", process_type="in",
        max_width_cm=72.0, max_height_cm=102.0,
        speed=8000.0, speed_unit="to/gio",
        setup_time_mins=0, changeover_time_mins=0,
        setup_waste_sheets=250.0, num_ink_units=7, is_active=True,
    )
    db.add(machine)
    db.flush()
    db.add(MachineRate(
        machine_id=machine.id, hourly_rate=0, min_charge=0,
        effective_from=date(2026, 1, 1),
    ))

    # Kẽm CTP — 100.000đ/bản (khổ 79×103; định giá theo khổ kẽm, quyết định #4).
    # machine_ids=NULL ⇒ áp mọi máy (engine chọn giá kẽm theo máy, NULL = generic).
    db.add(PlateDieRate(
        code="PLATE_GOLDEN", name="Kẽm CTP golden",
        plate_type="ban_kem_offset", technology="offset", unit="ban",
        unit_price=100000, effective_from=date(2026, 1, 1),
    ))

    # Gia công theo TỜ (quyết định #2: trên số tờ tốt): UV 1.000, Bế 250, Kiểm 0, Cột 0.
    ops = [
        ("OP_UV", "CM-Waterbase UV", "can_uv", 1000),
        ("OP_BE", "TB-Bế cấn hộp", "be_can", 250),
        ("OP_KP", "TP-Kiểm phẩm", "kiem_pham", 0),
        ("OP_CT", "TD-Cột thành phẩm", "cot_tp", 0),
    ]
    op_ids = {}
    for code, name, otype, rate in ops:
        op = Operation(code=code, name=name, operation_type=otype, unit="to", is_active=True)
        db.add(op)
        db.flush()
        op_ids[otype] = op.id
        db.add(OperationRate(
            operation_id=op.id, setup_fee=0, run_rate=rate, labor_rate=0,
            min_charge=0, speed=1000, effective_from=date(2026, 1, 1),
        ))
        # Không hao gia công (running 0%, tỷ lệ đạt 1) ⇒ số tờ tốt = ceil(20.000/3).
        db.add(Norm(norm_key="waste_pct_of_operation", value=0.0,
                    operation_key=otype, context_key="{}", effective_from=date(2026, 1, 1)))

    # Bù hao in: running 0%, makeready lấy từ setup_waste_sheets (=250).
    db.add(Norm(norm_key="running_waste_pct", value=0.0, context_key="{}", effective_from=date(2026, 1, 1)))
    db.add(Norm(norm_key="makeready_per_color_side", value=0.0, context_key="{}", effective_from=date(2026, 1, 1)))

    db.commit()

    yield db, paper.id, machine.id, op_ids
    db.close()


def test_golden_khay_carton(golden_setup):
    db, paper_id, machine_id, op_ids = golden_setup
    engine = PricingEngine(db)

    spec = {
        "product_type": "hop_carton",
        "product_name": "ĐAI QUẤN THE FISSHER",
        # Thành phẩm 21,59 × 100,33 cm; tờ in 68 × 101,50 ⇒ số con = 3×1 = 3
        "finished_width": 21.59,
        "finished_height": 100.33,
        "sheet_w": 68.0,
        "sheet_h": 101.5,
        "colors": 6,
        "sides": 1,
        "forms": 1,
        "material_id": paper_id,
        "machine_id": machine_id,
        "operations": [
            {"operation_id": op_ids["can_uv"], "sequence": 10, "execution_mode": "internal"},
            {"operation_id": op_ids["be_can"], "sequence": 20, "execution_mode": "internal"},
            {"operation_id": op_ids["kiem_pham"], "sequence": 30, "execution_mode": "internal"},
            {"operation_id": op_ids["cot_tp"], "sequence": 40, "execution_mode": "internal"},
        ],
    }

    cost_lines, total, warnings = engine.calculate_option(spec, 20000)

    # Không có blocking error
    assert not any(w["severity"] == "blocking_error" for w in warnings), warnings

    by_cat = {}
    for l in cost_lines:
        by_cat.setdefault(l.category, []).append(l)

    # --- Giấy: mô hình bù hao mới (waste_pct ở Loại SP; ca này = 0) ⇒ không cộng
    #     makeready. Tổng tờ = ceil(20.000/3) = 6.667 (bằng số tờ tốt). ---
    mat = by_cat["material"][0]
    assert int(mat.quantity) == 6667, f"số tờ = {mat.quantity}"
    assert float(mat.total_cost) == 6667 * 5384  # 35.895.928

    # --- Kẽm: màu(6) × mặt(1) × form(1) = 6 bản × 100.000 = 600.000 ---
    plate = by_cat["plate_die"][0]
    assert int(plate.quantity) == 6
    assert float(plate.total_cost) == 600000.0

    # --- Công in: đơn giá 0 ⇒ 0 ---
    machine_line = by_cat["machine"][0]
    assert float(machine_line.total_cost) == 0.0

    # --- Gia công theo TỜ TỐT = ceil(20.000/3) = 6.667 ---
    ops_by_name = {l.description.split(":")[0].replace("Gia công ", ""): l for l in by_cat.get("operation", [])}
    assert float(ops_by_name["CM-Waterbase UV"].total_cost) == 6667 * 1000  # 6.667.000
    assert float(ops_by_name["TB-Bế cấn hộp"].total_cost) == 6667 * 250     # 1.666.750

    # --- Tổng giá vốn ---
    expected_total = 6667 * 5384 + 600000 + 0 + 6667 * 1000 + 6667 * 250
    assert float(total) == expected_total  # 44.829.678
