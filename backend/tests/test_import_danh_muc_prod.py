"""Guard cho script nạp danh mục PROD `app.import_danh_muc_prod`.

Hai điều cần chắc TRƯỚC KHI chạy trên prod:
  1. IDEMPOTENT — chạy `run(db)` hai lần: lần 2 thêm 0 dòng, tổng số dòng mỗi bảng KHÔNG đổi.
  2. ENGINE NUỐT ĐƯỢC — mọi `cong_thuc_*` insert vào DB đều `safe_eval` trót lọt với ngữ cảnh
     phủ ĐỦ 20 biến hợp lệ (bắt lỗi gõ nhầm tên biến, thứ mà insert ORM KHÔNG kiểm).

Chạy nhắm đích (KHÔNG chạy cả init.ps1):
    cd backend; python -m pytest tests/test_import_danh_muc_prod.py -q
"""
from __future__ import annotations

import pytest
from sqlalchemy import func, select

from app.db import Base, SessionLocal, engine
from app.db_migrations import run_migrations
from app.import_danh_muc_prod import run
from app.seed import seed_all
from app.models.bu_hao import BuHao
from app.models.cong_doan import CongDoan
from app.models.khuon_be import KhuonBe
from app.models.may_thiet_bi import MayThietBi
from app.models.piece_work import PieceRate
from app.models.san_xuat_ly_do import SanXuatLyDo
from app.models.vat_lieu_kho import ChungLoaiGiay, GiayNguyen, VatTuInAn
from app.services.bien_cong_thuc import BIEN
from app.services.thanh_phan_engine import safe_eval

# Ngữ cảnh phủ ĐỦ MỌI biến hợp lệ (16 chung + dinh_luong + sl_vao/sl_ra + 2 đơn giá).
# Kích thước ở MÉT (engine đã ÷1000). Giá trị > 0 để công thức có max()/chia vẫn ra số thật.
_CTX_DAY_DU = {b["ma"]: 1.0 for b in BIEN}
_CTX_DAY_DU.update(
    dai_tp=0.21, rong_tp=0.29, dai_nguyen=0.79, rong_nguyen=1.09,
    dai_in=0.52, rong_in=0.72, so_luong=5000, so_tp=8,
    to_dau_vao=5200, to_sau_in=5100, to_nguyen=1050,
    so_mau=4, so_mau_pha=1, so_mat=2, so_kem=8,
    dinh_luong=0.15, sl_vao=5200, sl_ra=5000,
    don_gia_giay=27000, don_gia_vat_tu=250000,
)

# Các bảng danh mục + cột công thức cần soi.
_BANG_CONG_THUC = [
    (CongDoan, ["cong_thuc_gia", "cong_thuc_san_luong"]),
    (GiayNguyen, ["cong_thuc_luong"]),
    (VatTuInAn, ["cong_thuc_gia", "cong_thuc_luong"]),
    (MayThietBi, ["cong_thuc_luong"]),
    (PieceRate, ["cong_thuc_luong"]),
]

# Bảng cần đối chiếu số dòng giữa hai lần chạy (idempotent).
_BANG_DEM = [ChungLoaiGiay, GiayNguyen, VatTuInAn, MayThietBi, BuHao,
             CongDoan, KhuonBe, SanXuatLyDo, PieceRate]


@pytest.fixture
def db():
    """DB test như prod SAU khởi động bình thường: migrations + seed_all (SEED_DEMO=false),
    rồi script `run()` layer danh mục lên trên."""
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    s = SessionLocal()
    run_migrations(s)
    seed_all(s)
    yield s
    s.close()


def _dem(db, model) -> int:
    return db.execute(select(func.count()).select_from(model)).scalar_one()


def test_run_idempotent_va_cong_thuc_engine_nuot_duoc(db):
    # --- Lần 1 ---
    kq1 = run(db)
    sau_lan1 = {m.__name__: _dem(db, m) for m in _BANG_DEM}

    # Có thêm dòng thật ở mọi danh mục đa dạng (không phải no-op).
    for khoa in ("chung_loai_giay", "giay", "vat_tu", "may", "bu_hao",
                 "cong_doan", "khuon", "ly_do_san_xuat", "cong_viec_khoan"):
        assert kq1[khoa] > 0, f"{khoa} không thêm dòng nào ở lần chạy đầu"

    # --- Lần 2: phải idempotent ---
    kq2 = run(db)
    for khoa, so in kq2.items():
        assert so == 0, f"{khoa} lần 2 thêm {so} dòng — KHÔNG idempotent"

    sau_lan2 = {m.__name__: _dem(db, m) for m in _BANG_DEM}
    assert sau_lan2 == sau_lan1, "Tổng số dòng đổi sau lần chạy 2 — có insert trùng"

    # --- Engine nuốt được mọi công thức đã insert ---
    loi = []
    for model, cols in _BANG_CONG_THUC:
        for row in db.execute(select(model)).scalars():
            for col in cols:
                ct = getattr(row, col, None)
                if not ct or not str(ct).strip():
                    continue
                try:
                    val = safe_eval(str(ct), _CTX_DAY_DU)
                except Exception as e:  # noqa: BLE001 — gom hết để báo 1 lần
                    loi.append(f"{model.__name__}[{row.ma}].{col} = {ct!r} → {e}")
                    continue
                if val < 0:
                    loi.append(f"{model.__name__}[{row.ma}].{col} ra ÂM ({val}): {ct!r}")
    assert not loi, "Công thức engine không nuốt được:\n" + "\n".join(loi)


def test_khong_dong_toi_bac_tay_nghe(db):
    """Bộ đóng 5 bậc — script KHÔNG được đẻ/xoá dòng bậc tay nghề (số dòng bất biến)."""
    from app.models.employee import JobGrade

    truoc = _dem(db, JobGrade)
    run(db)
    sau = _dem(db, JobGrade)
    assert sau == truoc, f"Bậc tay nghề đổi {truoc}→{sau} — script không được đụng job_grades"
