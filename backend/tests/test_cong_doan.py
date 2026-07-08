"""Công đoạn — danh mục CRUD/validate + routing_engine (cascade/basis/step-cost/kẽm §4–5)."""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base
import app.models  # noqa: F401
from app.models.cong_doan import CongDoan  # noqa: F401 — đăng ký metadata
from app.repositories.cong_doan_repo import CongDoanRepository
from app.services.cong_doan_service import (
    CongDoanDuplicate,
    CongDoanService,
    CongDoanValidationError,
)
from app.services import routing_engine as re


def _svc():
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(eng)
    db = sessionmaker(bind=eng)()
    return db, CongDoanService(CongDoanRepository(db))


# ---- danh mục ----
def test_crud_and_duplicate():
    db, svc = _svc()
    cd = svc.create(dict(ma="IN", ten="In offset", nhom="print",
                         che_do_tinh="theo_san_luong", pricing_basis="per_1000_luot",
                         first_unit_floor=350000))
    assert cd.id and cd.nhom == "print"
    with pytest.raises(CongDoanDuplicate):
        svc.create(dict(ma="IN", ten="khác", nhom="print", pricing_basis="per_sheet"))


def test_validate_basis_and_hour():
    db, svc = _svc()
    with pytest.raises(CongDoanValidationError):          # E-CD-BASIS
        svc.create(dict(ma="X1", ten="x", nhom="finishing", che_do_tinh="theo_san_luong"))
    with pytest.raises(CongDoanValidationError):          # E-CD-HOUR-MAY (thiếu may_id)
        svc.create(dict(ma="X2", ten="x", nhom="prepress", che_do_tinh="theo_gio"))


def test_print_spoilage_forced_zero():
    db, svc = _svc()
    cd = svc.create(dict(ma="IN2", ten="In", nhom="print", pricing_basis="per_sheet", spoilage_pct=5))
    assert float(cd.spoilage_pct) == 0        # W-CD-PRINT-SPOIL → ép 0


# ---- routing_engine ----
def test_basis_qty_table():
    ctx = dict(so_to_in_gross=1000, so_luot=666, dt_to_in_m2=0.28, so_mat=1, so_cuon=500, so_con=44000)
    assert re.basis_qty("per_sheet", ctx) == 1000
    assert re.basis_qty("per_ram", ctx) == 2.0
    assert abs(re.basis_qty("per_1000_luot", ctx) - 0.666) < 1e-9
    assert re.basis_qty("per_pass", ctx) == 666
    assert re.basis_qty("per_book", ctx) == 500
    assert re.basis_qty("per_number", ctx) == 44000


def test_step_cost_floor_and_pass():
    # §7A IN: 666 lượt < 1.000 → sàn 350.000
    cd_in = dict(che_do_tinh="theo_san_luong", pricing_basis="per_1000_luot",
                 run_rate=200000, first_unit_floor=350000)
    r = re.compute_step_cost(cd_in, dict(so_luot=666))
    assert r["total"] == 350000
    # §7A BẾ per_pass: 333 lượt × 180 + khuôn 200k
    cd_be = dict(che_do_tinh="theo_san_luong", pricing_basis="per_pass", run_rate=180)
    r2 = re.compute_step_cost(cd_be, dict(so_luot=333), tooling_one_time=200000)
    assert r2["run_cost"] == round(333 * 180, 2)
    assert r2["tooling_cost"] == 200000
    # tái bản → bỏ tiền khuôn
    r3 = re.compute_step_cost(cd_be, dict(so_luot=333), reuse_tooling=True, tooling_one_time=200000)
    assert r3["tooling_cost"] == 0


def test_cascade_waste_backward():
    steps = [dict(nhom="print", spoilage_pct=5), dict(nhom="finishing", spoilage_pct=2),
             dict(nhom="finishing", spoilage_pct=3)]
    out = re.cascade_waste_backward(steps, 1000)
    assert out[-1]["output_qty"] == 1000
    # bước cuối 3%: input = 1000/0.97 ≈ 1030.93
    assert abs(out[-1]["input_qty"] - 1030.928) < 0.01
    # bước in: spoilage ép 0 → input == output
    assert out[0]["input_qty"] == out[0]["output_qty"]


def test_kem_line():
    # sheetwise 4/4, 1 form → 8 kẽm
    assert re.compute_kem_line(so_forms=1, so_kem_truoc=4, so_kem_sau=4, tu_tro=False,
                               don_gia_kem=100000)["so_kem"] == 8
    # tự trở → max(4,4)=4 kẽm
    assert re.compute_kem_line(so_forms=1, so_kem_truoc=4, so_kem_sau=4, tu_tro=True,
                               don_gia_kem=100000)["so_kem"] == 4
    # digital → 0 kẽm
    assert re.compute_kem_line(so_forms=2, so_kem_truoc=4, so_kem_sau=4, tu_tro=False,
                               don_gia_kem=100000, is_digital=True)["so_kem"] == 0
    # tiền kẽm = 8 × 100k
    assert re.compute_kem_line(so_forms=1, so_kem_truoc=4, so_kem_sau=4, tu_tro=False,
                               don_gia_kem=100000)["tien_kem"] == 800000


def test_so_to_in_gross():
    # net 228 + canh máy 100/màu × ... (ở đây 1 lần) + 2% → ceil
    g = re.so_to_in_gross(228, so_mau=1, bu_hao_canh_may_per_mau=100, bu_hao_chay_pct=2)
    assert g == pytest.approx(335, abs=1)   # (228+100)*1.02 = 334.56 → 335
