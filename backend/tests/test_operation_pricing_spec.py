"""Tests cho Công đoạn & Đơn giá gia công — các năng lực mới theo spec §A–§G.

Bao phủ những nhánh mà golden/engine test cũ chưa chạm: tính nội bộ theo giờ máy & kết hợp,
nhân công đa hình thức, khuôn, thuê ngoài từ bảng giá NCC, endpoint preview, và guard xóa.
Con số bám theo ví dụ trong spec (vd Bế thuê ngoài = 600.000đ).
"""
from __future__ import annotations

from datetime import date

import pytest

from app.db import SessionLocal
from app.models.estimate import Estimate, EstimateOption, EstimateCostLine
from app.models.operation import Operation, OperationRate
from app.models.product_type_catalog import ProductTypeCatalog
from app.models.user import User
from app.repositories.audit_repo import AuditLogRepository
from app.repositories.operation_repo import OperationRepository
from app.schemas.operation import OperationPreviewIn
from app.services.operation_service import (
    OperationService,
    OperationInUse,
    OperationValidationError,
)
from app.services.pricing_engine import PricingEngine


@pytest.fixture
def ctx(client):
    db = SessionLocal()
    db.query(OperationRate).delete()
    db.query(Operation).delete()
    db.commit()
    actor = db.query(User).filter(User.username == "admin").first()
    svc = OperationService(OperationRepository(db), AuditLogRepository(db))
    yield db, svc, actor
    db.close()


def _make(svc, actor, *, rate: dict, **op) -> Operation:
    op.setdefault("operation_type", "be")
    op.setdefault("unit", "to")
    operation = svc.create_operation(actor=actor, name=op.pop("name", "CD test"), **op)
    svc.add_operation_rate(operation_id=operation.id, effective_from=date(2026, 1, 1), actor=actor, **rate)
    return operation


# --- preview_cost (tab Test nhanh) — con số bám ví dụ spec -----------------

def test_preview_per_qty(ctx):
    _db, svc, actor = ctx
    op = _make(
        svc, actor, name="Bế per_qty", internal_pricing_method="per_qty", pricing_method="none",
        quantity_formula_type="print_sheet_qty",
        rate={"setup_fee": 100000, "run_rate": 300},
    )
    res = svc.preview_cost(operation_id=op.id, preview=OperationPreviewIn(sheet_qty=500))
    # setup 100.000 + 500 × 300 = 250.000
    assert res["quantity"] == 500
    assert res["total"] == 250000


def test_preview_per_hour(ctx):
    _db, svc, actor = ctx
    op = _make(
        svc, actor, name="Cán giờ máy", operation_type="can_mang", internal_pricing_method="per_hour",
        pricing_method="none", quantity_formula_type="print_sheet_qty",
        rate={"hourly_rate": 250000, "speed": 3000, "setup_time_mins": 30},
    )
    res = svc.preview_cost(operation_id=op.id, preview=OperationPreviewIn(sheet_qty=3000))
    # (0.5h setup + 3000/3000) × 250.000 = 1.5 × 250.000 = 375.000
    assert res["total"] == 375000


def test_preview_combined(ctx):
    _db, svc, actor = ctx
    op = _make(
        svc, actor, name="Kết hợp", internal_pricing_method="combined", pricing_method="none",
        rate={"setup_fee": 100000, "run_rate": 300, "hourly_rate": 250000, "speed": 3000, "setup_time_mins": 30},
    )
    res = svc.preview_cost(operation_id=op.id, preview=OperationPreviewIn(sheet_qty=3000))
    # 100.000 setup + 1.5×250.000 giờ máy + 3000×300 sản lượng = 100.000 + 375.000 + 900.000
    assert res["total"] == 1375000


def test_preview_labor_theo_gio(ctx):
    _db, svc, actor = ctx
    op = _make(
        svc, actor, name="NC theo giờ", internal_pricing_method="per_qty", pricing_method="theo_gio",
        labor_people_count=2, rate={"run_rate": 0, "labor_rate": 50000, "speed": 3000, "setup_time_mins": 30},
    )
    res = svc.preview_cost(operation_id=op.id, preview=OperationPreviewIn(sheet_qty=3000))
    # 2 người × 1.5 giờ × 50.000 = 150.000 (run_rate = 0)
    assert res["total"] == 150000


def test_preview_labor_khoan(ctx):
    _db, svc, actor = ctx
    op = _make(
        svc, actor, name="NC khoán", internal_pricing_method="per_qty", pricing_method="khoan",
        rate={"run_rate": 0, "labor_fixed": 200000},
    )
    res = svc.preview_cost(operation_id=op.id, preview=OperationPreviewIn(sheet_qty=500))
    assert res["total"] == 200000


def test_preview_tooling(ctx):
    _db, svc, actor = ctx
    op = _make(
        svc, actor, name="Bế có khuôn", internal_pricing_method="per_qty", pricing_method="none",
        has_tooling=True, tooling_type="khuon_be",
        rate={"run_rate": 500, "tooling_unit_price": 800000},
    )
    res = svc.preview_cost(operation_id=op.id, preview=OperationPreviewIn(sheet_qty=100))
    # 100 × 500 + 800.000 khuôn = 850.000
    assert res["total"] == 850000


def test_preview_outsource_matches_spec(ctx):
    """spec §5.5: max(500×250, 300.000) + 100.000 setup + 200.000 vận chuyển = 600.000."""
    _db, svc, actor = ctx
    op = _make(
        svc, actor, name="Bế thuê ngoài", process_type="both", quantity_formula_type="print_sheet_qty",
        rate={
            "run_rate": 500,
            "outsource_unit_price": 250, "outsource_min_charge": 300000,
            "outsource_setup_fee": 100000, "outsource_transport_fee": 200000,
        },
    )
    res = svc.preview_cost(operation_id=op.id, preview=OperationPreviewIn(sheet_qty=500, execution_mode="outsourced"))
    assert res["total"] == 600000


# --- engine path (kiểm nhánh engine, không chỉ preview) --------------------

def _engine_spec(op_id, mode):
    return {
        "material_id": None,
        "machine_id": None,
        "pieces_per_sheet": 1,
        "colors": 4,
        "sides": 2,
        "operations": [{"operation_id": op_id, "sequence": 10, "execution_mode": mode}],
    }


def test_engine_per_hour_line(ctx):
    db, svc, actor = ctx
    # has_yield_loss + tỷ lệ đạt 100% → hao 0 để lượng qua chuỗi = qty (kiểm số chính xác).
    op = _make(
        svc, actor, name="Cán giờ engine", operation_type="can_mang", internal_pricing_method="per_hour",
        pricing_method="none", has_yield_loss=True, default_yield_rate=100.0,
        rate={"hourly_rate": 250000, "speed": 3000, "setup_time_mins": 30},
    )
    lines, _total, _w = PricingEngine(db).calculate_option(_engine_spec(op.id, "internal"), 3000)
    op_lines = [l for l in lines if l.category in ("operation", "packing") and l.source_type == "operation_rates"]
    assert len(op_lines) == 1
    assert float(op_lines[0].total_cost) == 375000


def test_engine_outsource_from_catalog(ctx):
    db, svc, actor = ctx
    op = _make(
        svc, actor, name="Bế TN engine", process_type="both", has_yield_loss=True, default_yield_rate=100.0,
        rate={
            "run_rate": 500,
            "outsource_unit_price": 250, "outsource_min_charge": 300000,
            "outsource_setup_fee": 100000, "outsource_transport_fee": 200000,
        },
    )
    lines, _total, _w = PricingEngine(db).calculate_option(_engine_spec(op.id, "outsourced"), 500)
    out_lines = [l for l in lines if l.category == "outsource"]
    assert len(out_lines) == 1
    # max(500×250, 300.000) + 100.000 + 200.000 = 600.000
    assert float(out_lines[0].total_cost) == 600000
    assert out_lines[0].source_type == "operation_rates"


# --- validation + guard xóa (spec §7) --------------------------------------

def test_tooling_requires_type(ctx):
    _db, svc, actor = ctx
    with pytest.raises(OperationValidationError):
        svc.create_operation(actor=actor, name="Thiếu loại khuôn", operation_type="be", unit="to", has_tooling=True, tooling_type=None)


def test_delete_blocked_when_used_in_snapshot(ctx):
    db, svc, actor = ctx
    op = _make(svc, actor, name="Đã dùng", rate={"run_rate": 300})
    rate_id = op.rates[0].id

    pt = ProductTypeCatalog(product_type="pt_test", name="PT test", calculation_strategy="sheet_based", is_active=True)
    db.add(pt)
    db.flush()
    est = Estimate(estimate_number="EST-TEST-1", product_type="pt_test", product_name="X", input_spec_json={}, quantity_list_json=[100])
    db.add(est)
    db.flush()
    opt = EstimateOption(estimate_id=est.id, quantity=100)
    db.add(opt)
    db.flush()
    db.add(EstimateCostLine(
        estimate_option_id=opt.id, category="operation", description="Gia công",
        source_type="operation_rates", source_id=rate_id,
        quantity=1, unit="to", unit_cost=0, total_cost=0,
    ))
    db.commit()

    with pytest.raises(OperationInUse):
        svc.delete_operation(operation_id=op.id, actor=actor)
