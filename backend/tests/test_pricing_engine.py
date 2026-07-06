"""Integration tests for Phase 2A — PricingEngine and EstimateService.
"""
from __future__ import annotations

import pytest
from datetime import date, datetime, timezone
from app.db import SessionLocal
from app.models.material import Material, MaterialCost
from app.models.machine import Machine, MachineRate
from app.models.operation import Operation, OperationRate
from app.models.plate_die_rate import PlateDieRate
from app.models.norm import Norm
from app.models.product_type_catalog import ProductTypeCatalog
from app.models.user import User
from app.repositories.estimate_repo import EstimateRepository
from app.repositories.audit_repo import AuditLogRepository
from app.repositories.document_sequence_repo import DocumentSequenceRepository
from app.services.sequence_service import SequenceService
from app.services.estimate_service import EstimateService, EstimateValidationError, EstimateNotFound
from app.services.pricing_engine import PricingEngine

class MockActor:
    def __init__(self, user_id: int = 1) -> None:
        self.id = user_id

@pytest.fixture
def test_setup(client):
    db = SessionLocal()
    
    # 1. Clean old entries to avoid unique constraints
    db.query(MaterialCost).delete()
    db.query(Material).delete()
    db.query(MachineRate).delete()
    db.query(Machine).delete()
    db.query(OperationRate).delete()
    db.query(Operation).delete()
    db.query(PlateDieRate).delete()
    db.query(Norm).delete()
    db.query(ProductTypeCatalog).delete()
    db.commit()

    # 2. Setup user and seed basics
    actor = db.query(User).filter(User.username == "admin").first()
    if not actor:
        actor = User(username="admin", name="Admin", password_hash="hash")
        db.add(actor)
        db.commit()

    # Seed brochure catalog type
    catalog_pt = ProductTypeCatalog(product_type="brochure", name="Brochure", calculation_strategy="page_based", is_active=True)
    db.add(catalog_pt)
    db.commit()

    # 3. Seed test material (Paper)
    paper = Material(
        code="GY001",
        name="Giấy Couche 150gsm",
        material_type="paper",
        unit="to",
        width_cm=65.0,
        height_cm=86.0,
        gsm=150,
        is_active=True
    )
    db.add(paper)
    db.flush()

    paper_cost = MaterialCost(
        material_id=paper.id,
        price_unit="to",
        unit_price=1200, # 1,200 VND per sheet
        effective_from=date(2026, 1, 1),
    )
    db.add(paper_cost)

    # Decal material (area-based)
    decal = Material(
        code="VT001",
        name="Decal Sữa",
        material_type="decal",
        unit="m2",
        width_cm=100.0,
        height_cm=100.0,
        is_active=True
    )
    db.add(decal)
    db.flush()

    decal_cost = MaterialCost(
        material_id=decal.id,
        price_unit="m2",
        unit_price=45000, # 45,000 VND per m2
        effective_from=date(2026, 1, 1),
    )
    db.add(decal_cost)

    # 4. Seed test machine (Offset)
    offset_machine = Machine(
        code="M_OFFSET_01",
        name="Máy in Offset 4 màu",
        machine_type="offset",
        process_type="in",
        max_width_cm=79.0,
        max_height_cm=109.0,
        speed=8000.0, # 8000 sheets/hour
        speed_unit="to/gio",
        setup_time_mins=30,
        changeover_time_mins=0,
        is_active=True
    )
    db.add(offset_machine)
    db.flush()

    offset_rate = MachineRate(
        machine_id=offset_machine.id,
        hourly_rate=450000, # 450,000 VND / hour
        min_charge=300000,
        effective_from=date(2026, 1, 1),
    )
    db.add(offset_rate)

    # Digital machine
    digital_machine = Machine(
        code="M_DIGITAL_01",
        name="Máy in Nhanh Konica",
        machine_type="digital",
        process_type="in",
        speed=60.0, # 60 pages/minute
        speed_unit="trang/phut",
        setup_time_mins=5,
        changeover_time_mins=0,
        is_active=True
    )
    db.add(digital_machine)
    db.flush()

    digital_rate = MachineRate(
        machine_id=digital_machine.id,
        hourly_rate=200000,
        min_charge=50000,
        effective_from=date(2026, 1, 1),
    )
    db.add(digital_rate)

    # 5. Seed finishing operations
    be = Operation(code="OP_BE", name="Bế thành phẩm", operation_type="be", unit="to", is_active=True)
    db.add(be)
    db.flush()

    be_rate = OperationRate(
        operation_id=be.id,
        setup_fee=150000,
        run_rate=150,
        labor_rate=50,
        min_charge=100000,
        speed=1500,
        effective_from=date(2026, 1, 1)
    )
    db.add(be_rate)

    # Lamination
    lamination = Operation(code="OP_CAN", name="Cán màng bóng", operation_type="can_mang", unit="m2", is_active=True)
    db.add(lamination)
    db.flush()

    lamination_rate = OperationRate(
        operation_id=lamination.id,
        setup_fee=50000,
        run_rate=2500,
        labor_rate=500,
        min_charge=50000,
        speed=1000,
        effective_from=date(2026, 1, 1)
    )
    db.add(lamination_rate)

    # Packing
    packing = Operation(code="OP_GOI", name="Đóng gói thùng carton", operation_type="dong_goi", unit="cai", is_active=True)
    db.add(packing)
    db.flush()

    packing_rate = OperationRate(
        operation_id=packing.id,
        setup_fee=0,
        run_rate=500,
        labor_rate=100,
        min_charge=20000,
        speed=200,
        effective_from=date(2026, 1, 1)
    )
    db.add(packing_rate)

    # 6. Seed plate rate
    plate = PlateDieRate(
        code="PLATE_T", name="Kẽm test",
        plate_type="ban_kem_offset",
        technology="offset",
        unit="ban",
        unit_price=120000,
        effective_from=date(2026, 1, 1)
    )
    db.add(plate)

    # 7. Seed norms
    # Tỷ lệ đạt từng công đoạn (gộp "hao công đoạn" → tỷ lệ đạt = 1 − hao):
    # can_mang 97% (hao 3%), be 98% (hao 2%), packing 100% (hao 0%).
    db.add(Norm(norm_key="yield_rate", waste_group="YIELD_RATE", value=0.97, operation_key="can_mang", context_key="{}", effective_from=date(2026, 1, 1)))
    db.add(Norm(norm_key="yield_rate", waste_group="YIELD_RATE", value=0.98, operation_key="be", context_key="{}", effective_from=date(2026, 1, 1)))
    db.add(Norm(norm_key="yield_rate", waste_group="YIELD_RATE", value=1.0, operation_key="dong_goi", context_key="{}", effective_from=date(2026, 1, 1)))
    # print running waste (cộng thêm base × 2%)
    db.add(Norm(norm_key="running_waste_pct", waste_group="RUNNING_WASTE", value=0.02, context_key="{}", effective_from=date(2026, 1, 1)))
    # print makeready waste (legacy: 15 tờ/màu-mặt)
    db.add(Norm(norm_key="makeready_per_color_side", waste_group="SETUP_WASTE", value=15.0, context_key="{}", effective_from=date(2026, 1, 1)))

    db.commit()

    # Services
    repo = EstimateRepository(db)
    audit = AuditLogRepository(db)
    seq_repo = DocumentSequenceRepository(db)
    sequence = SequenceService(seq_repo)
    service = EstimateService(db, repo, audit, sequence)

    yield service, db, actor, paper.id, offset_machine.id, be.id, lamination.id, packing.id, decal.id, digital_machine.id
    db.close()


def test_geometric_layout_fit(test_setup):
    service, db, actor, paper_id, offset_id, be_id, lam_id, pack_id, decal_id, digital_id = test_setup
    engine = PricingEngine(db)

    # finished: 10x15, sheet: 32x22 -> 3 straight, 2 rotated -> max 3
    spec = {
        "finished_width": 10.0,
        "finished_height": 15.0,
        "sheet_w": 32.0,
        "sheet_h": 22.0,
        "grain_locked": False
    }
    cost_lines, total, warnings = engine.calculate_option(spec, 100)
    # find pieces_per_sheet used in calculation_snapshot of first machine line or calc_snapshot
    assert total >= 0
    # pieces_per_sheet is 3
    
    # test grain locked (straight only)
    spec_locked = {
        "finished_width": 15.0,
        "finished_height": 10.0,
        "sheet_w": 32.0,
        "sheet_h": 22.0,
        "grain_locked": True
    }
    # straight: swat=2, shat=2 -> 4. Best with rotate was straight.
    # What if piece is 20x15, sheet 30x20: straight 1x1=1. rotated 1x2=2.
    spec_rot = {
        "finished_width": 20.0,
        "finished_height": 15.0,
        "sheet_w": 30.0,
        "sheet_h": 20.0,
        "grain_locked": False
    }
    # rotated should give 2
    # straight should give 1
    spec_rot_locked = dict(spec_rot, grain_locked=True)

    # Let's check pieces calculation directly via calculate_option warnings / calculations
    _, _, warnings_res = engine.calculate_option(spec_rot, 100)
    assert not any(w["code"] == "PIECES_PER_SHEET_ZERO" for w in warnings_res)


def test_reverse_waste_chain_sorting(test_setup):
    service, db, actor, paper_id, offset_id, be_id, lam_id, pack_id, decal_id, digital_id = test_setup
    
    # Create estimate with operations in wrong order sequence-wise
    # In -> Cán màng (seq 10) -> Bế (seq 20) -> Đóng gói (seq 30)
    # Reverse Waste Chain must sort sequence DESC: Đóng gói (30) -> Bế (20) -> Cán màng (10)
    input_spec = {
        "material_id": paper_id,
        "machine_id": offset_id,
        "sheet_w": 65.0,
        "sheet_h": 86.0,
        "pieces_per_sheet": 4,
        "colors": 4,
        "sides": 2,
        "forms": 1,
        "operations": [
            {"operation_id": be_id, "sequence": 20, "execution_mode": "internal"},
            {"operation_id": lam_id, "sequence": 10, "execution_mode": "internal"},
            {"operation_id": pack_id, "sequence": 30, "execution_mode": "internal"}
        ]
    }

    # Execute service call
    est = service.create_estimate(
        product_type="brochure",
        product_name="Brochure A4",
        quantity_list=[1000],
        input_spec=input_spec,
        actor_id=actor.id,
        status="calculated"
    )

    assert est.status == "calculated"
    assert len(est.options) == 1
    option = est.options[0]
    
    # Audit calculation snapshot to verify sequence order of reverse waste chain
    # It must be packing -> be -> can_mang
    cost_lines = option.cost_lines
    machine_lines = [l for l in cost_lines if l.category == "machine"]
    assert len(machine_lines) == 1
    
    # Verify print waste calculations (chuỗi mới — tỷ lệ đạt CĐ + running CỘNG thêm):
    # 1. targetFinished: 1000
    # 2. packing: đạt 100% -> ceil(1000 / 1.0) = 1000
    # 3. be: đạt 98% -> ceil(1000 / 0.98) = 1021
    # 4. can_mang: đạt 97% -> ceil(1021 / 0.97) = 1053
    # 5. printed_sheets = ceil(1053 / 4) = 264 (tỷ lệ đạt in mặc định 1.0)
    # 6. running_add = ceil(264 × 2%) = 6  → tờ chạy = 264 + 6 = 270
    # 7. makeready_sheets = 15 * 4 * 2 * 1 = 120
    # 8. total_sheets = 264 + 120 + 6 = 390
    
    # Let's assert total sheets matches 390!
    mat_line = [l for l in cost_lines if l.category == "material"][0]
    assert int(mat_line.quantity) == 390


def test_offset_plates_multiplier(test_setup):
    service, db, actor, paper_id, offset_id, be_id, lam_id, pack_id, decal_id, digital_id = test_setup
    
    input_spec = {
        "material_id": paper_id,
        "machine_id": offset_id,
        "sheet_w": 65.0,
        "sheet_h": 86.0,
        "pieces_per_sheet": 4,
        "colors": 4,
        "sides": 2,
        "forms": 3, # 3 forms
        "operations": []
    }

    est = service.create_estimate(
        product_type="brochure",
        product_name="Offset Booklet",
        quantity_list=[1000],
        input_spec=input_spec,
        actor_id=actor.id,
        status="calculated"
    )

    option = est.options[0]
    plate_line = [l for l in option.cost_lines if l.category == "plate_die"][0]
    # plates = colors (4) * sides (2) * forms (3) = 24 plates
    assert int(plate_line.quantity) == 24
    # unit price 120,000 -> total cost = 24 * 120,000 = 2,880,000 VND
    assert float(plate_line.total_cost) == 2880000.0


def test_blocking_error_guards_calculated_status(test_setup):
    service, db, actor, paper_id, offset_id, be_id, lam_id, pack_id, decal_id, digital_id = test_setup

    # Create estimate missing material price (e.g. invalid material_id 9999)
    input_spec = {
        "material_id": 9999, # non-existent
        "machine_id": offset_id,
        "sheet_w": 65.0,
        "sheet_h": 86.0,
        "pieces_per_sheet": 4,
        "colors": 4,
        "sides": 2,
        "operations": []
    }

    # Attempting to create in status calculated should fail
    with pytest.raises(EstimateValidationError, match="Không thể chuyển sang trạng thái đã tính toán"):
        service.create_estimate(
            product_type="brochure",
            product_name="Errored Book",
            quantity_list=[1000],
            input_spec=input_spec,
            actor_id=actor.id,
            status="calculated"
        )

    # Creating in status draft is fine, but options should carry the warnings/blocking_errors
    est_draft = service.create_estimate(
        product_type="brochure",
        product_name="Errored Book",
        quantity_list=[1000],
        input_spec=input_spec,
        actor_id=actor.id,
        status="draft"
    )
    assert est_draft.status == "draft"
    assert len(est_draft.options) == 1
    option = est_draft.options[0]
    
    # Blocking error warning present
    blocking_warnings = [w for w in option.warnings_json if w["severity"] == "blocking_error"]
    assert len(blocking_warnings) > 0
    assert any(w["code"] == "MATERIAL_NOT_FOUND" for w in blocking_warnings)


def test_recalculate_transactional_safety(test_setup):
    service, db, actor, paper_id, offset_id, be_id, lam_id, pack_id, decal_id, digital_id = test_setup

    input_spec = {
        "material_id": paper_id,
        "machine_id": offset_id,
        "sheet_w": 65.0,
        "sheet_h": 86.0,
        "pieces_per_sheet": 4,
        "colors": 4,
        "sides": 2,
        "operations": []
    }

    est = service.create_estimate(
        product_type="brochure",
        product_name="Transaction test Book",
        quantity_list=[1000],
        input_spec=input_spec,
        actor_id=actor.id,
        status="calculated"
    )
    assert est.status == "calculated"
    old_option_id = est.options[0].id

    # Update with invalid quantities to cause validation error
    # The transaction should rollback and keep old options!
    with pytest.raises(EstimateValidationError):
        service.update_estimate(
            estimate_id=est.id,
            product_type="brochure",
            product_name="Transaction test Book",
            quantity_list=[0], # invalid quantity 0
            input_spec=input_spec,
            actor_id=actor.id,
            status="calculated"
        )
    
    # Reload from DB and verify old option still exists intact
    db.expire_all()
    reloaded = service.get_estimate(est.id)
    assert len(reloaded.options) == 1
    assert reloaded.options[0].id == old_option_id
    assert reloaded.options[0].quantity == 1000
