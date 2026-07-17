"""Tests cho tái thiết kế danh mục #7 — Định mức & Bù hao (waste_group + chuỗi mới)."""
from __future__ import annotations

import math
from datetime import date

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base
from app.models.material import Material, MaterialCost
from app.models.machine import Machine, MachineRate
from app.models.norm import Norm
from app.models.product_type_catalog import ProductTypeCatalog
from app.repositories.norm_repo import NormRepository
from app.repositories.audit_repo import AuditLogRepository
from app.services.norm_service import NormService, NormLookupContext
from app.services.pricing_engine import (
    PricingEngine,
    _compute_setup_sheets,
    _compute_running_sheets,
    _compute_paper_extra,
)


class MockActor:
    id = 1


# --- Helper: đơn vị công thức nhóm ------------------------------------------

def test_setup_combined_and_clamp():
    n = Norm(norm_key="makeready_per_color_side", waste_group="SETUP_WASTE",
             calculation_method="COMBINED", value=0,
             setup_waste_qty=100, setup_waste_per_color=30, setup_waste_per_side=50,
             min_waste_qty=100, max_waste_qty=1000, context_key="{}",
             effective_from=date(2026, 1, 1))
    # 100 + 30×4 + 50×2 = 320
    assert _compute_setup_sheets(n, colors=4, sides=2) == 320
    # clamp max
    n.max_waste_qty = 200
    assert _compute_setup_sheets(n, colors=4, sides=2) == 200


def test_setup_legacy_per_color_side():
    n = Norm(norm_key="makeready_per_color_side", waste_group="SETUP_WASTE",
             calculation_method="PER_COLOR_SIDE", value=15, context_key="{}",
             effective_from=date(2026, 1, 1))
    assert _compute_setup_sheets(n, colors=4, sides=2) == 120


def test_running_additive_with_min_clamp():
    n = Norm(norm_key="running_waste_pct", waste_group="RUNNING_WASTE",
             calculation_method="PERCENT", value=0.03, min_waste_qty=20,
             context_key="{}", effective_from=date(2026, 1, 1))
    # ceil(258 × 3%) = 8 → nhưng min 20 → 20
    assert _compute_running_sheets(n, 258) == 20
    # base lớn: ceil(2000 × 3%) = 60
    assert _compute_running_sheets(n, 2000) == 60


def test_paper_extra_methods():
    pct = Norm(norm_key="paper_extra_waste", waste_group="PAPER_EXTRA_WASTE",
               calculation_method="PERCENT", value=0.01, context_key="{}",
               effective_from=date(2026, 1, 1))
    assert _compute_paper_extra(pct, 486) == math.ceil(486 * 0.01)  # 5
    fixed = Norm(norm_key="paper_extra_waste", waste_group="PAPER_EXTRA_WASTE",
                 calculation_method="FIXED", value=10, context_key="{}",
                 effective_from=date(2026, 1, 1))
    assert _compute_paper_extra(fixed, 486) == 10
    ream = Norm(norm_key="paper_extra_waste", waste_group="PAPER_EXTRA_WASTE",
                calculation_method="PER_REAM", value=5, context_key="{}",
                effective_from=date(2026, 1, 1))
    assert _compute_paper_extra(ream, 1000) == 5 * (1000 / 500)  # 10


# --- Chuỗi engine đầy đủ khớp ví dụ spec §4.2 (486 tờ SX, 491 tờ mua) -------

def _mem_db():
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(eng)
    return sessionmaker(bind=eng)()


def test_full_chain_matches_spec_example():
    db = _mem_db()
    paper = Material(code="P", name="Giay", material_type="paper", unit="to",
                     width_cm=79, height_cm=109, gsm=150)
    db.add(paper)
    db.flush()
    db.add(MaterialCost(material_id=paper.id, price_unit="to", unit_price=1000, effective_from=date(2025, 1, 1)))
    mc = Machine(code="M", name="May", machine_type="offset", process_type="in", speed=8000,
                 speed_unit="to/gio", setup_time_mins=0, changeover_time_mins=0, setup_waste_sheets=0, num_ink_units=8)
    db.add(mc)
    db.flush()
    db.add(MachineRate(machine_id=mc.id, hourly_rate=0, effective_from=date(2025, 1, 1)))
    # Định mức khâu in: đạt 97%, makeready 100 + 30/màu, running 3%; hao giấy 1%.
    db.add(Norm(norm_key="yield_rate", waste_group="YIELD_RATE", calculation_method="PERCENT",
                value=0.97, context_key="{}", effective_from=date(2025, 1, 1), code="YIELD_IN"))
    db.add(Norm(norm_key="makeready_per_color_side", waste_group="SETUP_WASTE", calculation_method="COMBINED",
                value=0, setup_waste_qty=100, setup_waste_per_color=30, setup_waste_per_side=0,
                context_key="{}", effective_from=date(2025, 1, 1), code="MR_IN"))
    db.add(Norm(norm_key="running_waste_pct", waste_group="RUNNING_WASTE", calculation_method="PERCENT",
                value=0.03, context_key="{}", effective_from=date(2025, 1, 1), code="RW_IN"))
    db.add(Norm(norm_key="paper_extra_waste", waste_group="PAPER_EXTRA_WASTE", calculation_method="PERCENT",
                value=0.01, context_key="{}", effective_from=date(2025, 1, 1), code="PAPER"))
    db.commit()

    # Mô hình mới: engine BỎ QUA norm. Bù hao lấy từ waste_pct của Loại sản phẩm.
    db.add(ProductTypeCatalog(product_type="tor_roi", name="Tờ rơi",
                              calculation_strategy="sheet_based", is_active=True, waste_pct=5))
    db.commit()

    spec = dict(product_type="tor_roi", colors=4, sides=2, forms=1, material_id=paper.id, machine_id=mc.id,
                sheet_w=79, sheet_h=109, pieces_per_sheet=4, operations=[])
    lines, total, warns = PricingEngine(db).calculate_option(spec, 1000)
    assert not any(w["severity"] == "blocking_error" for w in warns), warns
    mat = next(l for l in lines if l.category == "material")
    snap = mat.calculation_snapshot_json
    # printed = ceil(1000/4) = 250. Norm (yield/makeready/running/paper) KHÔNG áp nữa.
    assert snap["sheets_after_yield"] == 250   # không còn tỷ lệ đạt norm
    assert snap["makeready_sheets"] == 0       # không còn makeready norm
    # Bù hao chỉ từ Loại SP: SX = ceil(250 × 1.05) = 263.
    assert snap["production_sheets"] == 263
    assert snap["paper_extra_sheets"] == 0
    assert snap["purchase_sheets"] == 263
    # Diễn giải mới: lý thuyết → bù hao → sản xuất (không còn dòng Makeready norm).
    labels = [n["label"] for n in snap["norms_applied"]]
    assert "Bù hao" in labels and "Số tờ sản xuất" in labels
    db.close()


# API `/api/norms` ĐÃ GỠ (2026-07-16: không màn nào gọi — NormsCatalogPage mồ côi đã xóa, module
# quyền `dm_dinh_muc` bỏ theo migration 0069) → 3 test đi qua endpoint đó (tạo theo waste_group ·
# 2-mã-cùng-phạm-vi · chặn yield>1 / min>max) đi cùng. Phần CÒN SỐNG là bảng norms + engine đọc
# thẳng qua NormService, phủ bởi các test tính toán ở trên và test_estimate_norm_usage_scan dưới.


# --- "Đang dùng trong" — quét snapshot tính giá tìm định mức đã dùng --------

def test_estimate_norm_usage_scan():
    from app.models.estimate import Estimate, EstimateOption, EstimateCostLine

    db = _mem_db()
    running = Norm(norm_key="running_waste_pct", waste_group="RUNNING_WASTE", calculation_method="PERCENT",
                   value=0.03, context_key="{}", effective_from=date(2025, 1, 1), code="RW")
    yield_op = Norm(norm_key="yield_rate", waste_group="YIELD_RATE", calculation_method="PERCENT",
                    value=0.97, context_key="{}", effective_from=date(2025, 1, 1), code="Y")
    unused = Norm(norm_key="paper_extra_waste", waste_group="PAPER_EXTRA_WASTE", calculation_method="PERCENT",
                  value=0.01, context_key="{}", effective_from=date(2025, 1, 1), code="PX")
    db.add_all([running, yield_op, unused])
    db.flush()

    est = Estimate(estimate_number="E1", product_type="tor_roi", product_name="Tờ rơi",
                   status="calculated", input_spec_json={}, quantity_list_json=[1000])
    db.add(est)
    db.flush()
    opt = EstimateOption(estimate_id=est.id, quantity=1000, total_cost=0)
    db.add(opt)
    db.flush()
    # Một dòng dùng norm ở khóa top-level (print_waste) + một norm ở chuỗi hao ngược.
    db.add(EstimateCostLine(
        estimate_option_id=opt.id, category="material", description="Giấy",
        calculation_snapshot_json={
            "print_waste_norm_id": running.id,
            "reverse_waste_chain": [{"norm_id": yield_op.id, "setup_norm_id": None}],
        },
        quantity=1, unit="to", unit_cost=0, total_cost=0,
    ))
    db.commit()

    repo = NormRepository(db)
    counts = repo.estimate_norm_counts()
    assert counts.get(running.id) == 1
    assert counts.get(yield_op.id) == 1
    assert counts.get(unused.id, 0) == 0  # định mức chưa dùng ở phiếu nào

    ests = repo.list_estimates_by_norm(running.id)
    assert [e.estimate_number for e in ests] == ["E1"]

    # Phiếu bị hủy → không tính vào "đang dùng".
    est.status = "cancelled"
    db.commit()
    assert NormRepository(db).estimate_norm_counts().get(running.id, 0) == 0
    assert NormRepository(db).list_estimates_by_norm(running.id) == []
    db.close()


# --- Cảnh báo xung đột (§9) — phạm vi giao + độ cụ thể ngang -----------------

def test_detect_conflicts_equal_specificity():
    db = _mem_db()
    svc = NormService(NormRepository(db), AuditLogRepository(db))
    # A: áp dụng tất cả (spec 0). B: theo loại SP (spec +10). C: theo máy (spec +10).
    # Dùng cột scope scalar (product_type/machine_id) vì uix_norms_current chỉ khóa theo scalar
    # — hai rule chỉ khác nhau ở multi-select không thể cùng mở.
    a = Norm(norm_key="running_waste_pct", waste_group="RUNNING_WASTE", calculation_method="PERCENT",
             value=0.02, context_key="{}", effective_from=date(2025, 1, 1), code="RW_ALL")
    b = Norm(norm_key="running_waste_pct", waste_group="RUNNING_WASTE", calculation_method="PERCENT",
             value=0.015, product_type="cat", context_key="{}",
             effective_from=date(2025, 1, 1), code="RW_CAT")
    c = Norm(norm_key="running_waste_pct", waste_group="RUNNING_WASTE", calculation_method="PERCENT",
             value=0.018, machine_id=5, context_key="{}",
             effective_from=date(2025, 1, 1), code="RW_M109")
    db.add_all([a, b, c])
    db.commit()

    out = svc.detect_conflicts()
    conflicts = out["conflicts"]
    # B ↔ C xung đột (đều +10, phạm vi giao: SP=cat trên máy=5 khớp cả hai).
    assert conflicts.get(b.id) == [c.id]
    assert conflicts.get(c.id) == [b.id]
    # A (spec 0) KHÔNG bị cảnh báo — rule cụ thể hơn đã thắng rõ ràng, engine không phân vân.
    assert a.id not in conflicts
    assert out["labels"][b.id] == "RW_CAT"
    db.close()


def test_detect_conflicts_disjoint_scopes_no_warning():
    db = _mem_db()
    svc = NormService(NormRepository(db), AuditLogRepository(db))
    # Hai rule theo hai loại SP KHÁC nhau → không thể cùng khớp → không cảnh báo.
    b = Norm(norm_key="running_waste_pct", waste_group="RUNNING_WASTE", calculation_method="PERCENT",
             value=0.015, product_type="cat", context_key="{}",
             effective_from=date(2025, 1, 1), code="RW_CAT")
    d = Norm(norm_key="running_waste_pct", waste_group="RUNNING_WASTE", calculation_method="PERCENT",
             value=0.02, product_type="hop", context_key="{}",
             effective_from=date(2025, 1, 1), code="RW_HOP")
    db.add_all([b, d])
    db.commit()
    assert svc.detect_conflicts()["conflicts"] == {}
    db.close()
