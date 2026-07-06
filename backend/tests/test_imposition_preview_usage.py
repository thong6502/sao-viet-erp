"""Kiểu bình bài — Kiểm thử (preview) dùng chung công thức engine + đếm 'Đang dùng trong' (tính giá).

`imposition_math` là nguồn công thức duy nhất: pricing_engine gọi 3 hàm lõi (số con TP/tờ,
số bản kẽm, số lượt-màu) → preview endpoint dùng CHÍNH các hàm đó nên không lệch. Ở đây test
trực tiếp helper + service.preview, và test đếm/liệt kê estimates theo mã bình bài.
Self-contained (own in-memory DB); không phụ thuộc seed.
"""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base
import app.models  # noqa: F401 — register every table on Base.metadata
from app.models.estimate import Estimate
from app.models.user import User
from app.repositories.audit_repo import AuditLogRepository
from app.repositories.imposition_type_repo import ImpositionTypeRepository
from app.services import imposition_math
from app.services.imposition_type_service import (
    ImpositionTypeService,
    ImpositionTypeValidationError,
)


def _setup():
    eng = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(eng)
    db = sessionmaker(bind=eng)()
    actor = User(username="tester", name="Tester", password_hash="x")
    db.add(actor)
    db.commit()
    repo = ImpositionTypeRepository(db)
    svc = ImpositionTypeService(repo, AuditLogRepository(db))
    return db, repo, svc, actor


def _est(db, number, spec, *, status="calculated"):
    db.add(Estimate(
        estimate_number=number,
        product_type="name_card",
        product_name="Test " + number,
        status=status,
        input_spec_json=spec,
        quantity_list_json=[1000],
    ))
    db.commit()


# ---- helper lõi ------------------------------------------------------------
def test_finished_pieces_factor_half_floors():
    # tự trở: 8 con hình học × 0.5 = 4 con thành phẩm
    assert imposition_math.finished_pieces_per_sheet(8, 0.5) == 4
    # hệ số 1.0 giữ nguyên số con hình học
    assert imposition_math.finished_pieces_per_sheet(8, 1.0) == 8
    # luôn ≥ 1 con/tờ
    assert imposition_math.finished_pieces_per_sheet(1, 0.5) == 1


def test_plates_and_ink_helpers():
    assert imposition_math.plates_count(4, 1.0, 1) == 4
    assert imposition_math.plates_count(4, 2.0, 1) == 8   # trở nhíp 2 kẽm
    assert imposition_math.ink_impressions(300, 4, 1.0) == 1200
    assert imposition_math.ink_impressions(300, 4, 2.0) == 2400  # 2 mặt


# ---- preview (khớp ví dụ UI: geo=8, qty=1000, tờ SX=300, 4 màu, 1 form, 6000 tờ/h) ----
def test_preview_one_side_example():
    out = imposition_math.preview(
        finished_factor=1.0, pass_count=1.0, plate_set_factor=1.0, ink_pass_factor=1.0,
        geometric_pieces=8, quantity=1000, production_sheets=300, colors=4,
        forms=1, machine_speed=6000,
    )
    assert out["finished_pieces_per_sheet"] == 8
    assert out["theoretical_sheets"] == 125          # ceil(1000/8)
    assert out["machine_sheets"] == 300
    assert out["run_hours"] == pytest.approx(0.05)   # 300/6000
    assert out["plates"] == 4
    assert out["ink_impressions"] == 1200


def test_preview_tu_tro_halves_pieces_doubles_pass():
    out = imposition_math.preview(
        finished_factor=0.5, pass_count=2.0, plate_set_factor=1.0, ink_pass_factor=2.0,
        geometric_pieces=8, quantity=1000, production_sheets=300, colors=4,
        forms=1, machine_speed=6000,
    )
    assert out["finished_pieces_per_sheet"] == 4
    assert out["theoretical_sheets"] == 250          # ceil(1000/4)
    assert out["machine_sheets"] == 600              # 300 × 2 lượt
    assert out["plates"] == 4                         # 4 × 1 × 1 (dùng chung kẽm)
    assert out["ink_impressions"] == 2400            # 300 × 4 × 2


def test_service_preview_validates_factors():
    _db, _repo, svc, _actor = _setup()
    with pytest.raises(ImpositionTypeValidationError):
        svc.preview({"finished_factor": 0, "pass_count": 1})
    with pytest.raises(ImpositionTypeValidationError):
        svc.preview({"finished_factor": 1, "pass_count": 0})


# ---- "Đang dùng trong" = số tính giá (estimates) --------------------------
def test_estimate_counts_by_resolved_code():
    db, repo, _svc, _actor = _setup()
    _est(db, "E1", {"imposition": "TU_TRO", "sides": 2})
    _est(db, "E2", {"imposition": "tu_tro", "sides": 2})        # khác hoa/thường → cùng mã
    _est(db, "E3", {"imposition_name": "ONE_SIDE", "sides": 1})  # legacy field
    _est(db, "E4", {"sides": 1})                                 # không chỉ định → ONE_SIDE
    _est(db, "E5", {"sides": 2})                                 # không chỉ định → TRO_NHIP_2_KEM
    _est(db, "E6", {"imposition": "TU_TRO"}, status="cancelled") # cancelled bị loại

    counts = repo.estimate_code_counts()
    assert counts.get("TU_TRO") == 2
    assert counts.get("ONE_SIDE") == 2         # E3 (name) + E4 (default sides=1)
    assert counts.get("TRO_NHIP_2_KEM") == 1   # E5 default sides=2


def test_list_estimates_by_code_newest_first():
    db, repo, _svc, _actor = _setup()
    _est(db, "E1", {"imposition": "TU_TRO", "sides": 2})
    _est(db, "E2", {"imposition": "TU_TRO", "sides": 2})
    _est(db, "E3", {"imposition": "ONE_SIDE", "sides": 1})

    rows = repo.list_estimates_by_code("TU_TRO")
    assert [r.estimate_number for r in rows] == ["E2", "E1"]  # created_at desc
    assert repo.list_estimates_by_code("ONE_SIDE")[0].estimate_number == "E3"
