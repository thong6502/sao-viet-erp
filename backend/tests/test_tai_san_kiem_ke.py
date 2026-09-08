"""Đợt kiểm kê: bung danh sách phải có → đối chiếu tay → ra thiếu/thừa."""
from datetime import date

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base
import app.models  # noqa: F401
from app.models.department import Department
from app.models.tai_san import LOAI_TSCD
from app.repositories.tai_san_repo import TaiSanRepository
from app.services.tai_san.kiem_ke_service import KiemKeDaKet, KiemKeNotFound, KiemKeService
from app.services.tai_san.service import TaiSanService


def _moi_truong():
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(eng)
    db = sessionmaker(bind=eng)()
    return db, TaiSanService(TaiSanRepository(db)), KiemKeService(db)


def _hai_tai_san(svc, bo_phan_id=None):
    a = svc.ghi_tang(dict(ten="May A", loai=LOAI_TSCD, so_thang=120, ngay_su_dung=date(2026, 1, 1),
                          bo_phan_id=bo_phan_id,
                          chi_phi=[{"dien_giai": "NG", "so_tien": 100_000_000}]))
    b = svc.ghi_tang(dict(ten="May B", loai=LOAI_TSCD, so_thang=120, ngay_su_dung=date(2026, 1, 1),
                          bo_phan_id=bo_phan_id,
                          chi_phi=[{"dien_giai": "NG", "so_tien": 200_000_000}]))
    return a, b


def test_tao_dot_bung_du_danh_sach():
    db, svc, kk = _moi_truong()
    _hai_tai_san(svc)
    dot = kk.tao_dot(ngay=date(2026, 12, 31))
    assert len(dot.dong) == 2
    assert dot.ma.startswith("KK-")


def test_dot_theo_bo_phan_chi_bung_tai_san_cua_bo_phan_do():
    db, svc, kk = _moi_truong()
    to_in = Department(name="To In", code="PB801")
    db.add(to_in)
    db.commit()
    _hai_tai_san(svc, bo_phan_id=to_in.id)
    svc.ghi_tang(dict(ten="May ngoai to", loai=LOAI_TSCD, so_thang=120,
                      ngay_su_dung=date(2026, 1, 1),
                      chi_phi=[{"dien_giai": "NG", "so_tien": 50_000_000}]))
    dot = kk.tao_dot(ngay=date(2026, 12, 31), bo_phan_id=to_in.id)
    assert len(dot.dong) == 2


def test_tai_san_da_ghi_giam_khong_bung_vao_dot():
    db, svc, kk = _moi_truong()
    a, b = _hai_tai_san(svc)
    svc.ghi_giam(b.id, ngay=date(2026, 6, 1), ly_do="Thanh ly")
    dot = kk.tao_dot(ngay=date(2026, 12, 31))
    assert [d.tai_san_id for d in dot.dong] == [a.id]


def test_ket_thuc_ra_danh_sach_thieu_va_thua():
    db, svc, kk = _moi_truong()
    a, b = _hai_tai_san(svc)
    dot = kk.tao_dot(ngay=date(2026, 12, 31))
    d_a = next(d for d in dot.dong if d.tai_san_id == a.id)
    d_b = next(d for d in dot.dong if d.tai_san_id == b.id)
    kk.ghi_ket_qua(dot.id, d_a.id, ket_qua="co", tinh_trang="Con tot")
    kk.ghi_ket_qua(dot.id, d_b.id, ket_qua="khong_thay", ghi_chu="Khong tim thay tai xuong")
    kk.them_phat_hien(dot.id, ten_phat_hien="May dan keo chua vao so")

    ket = kk.ket_thuc(dot.id)
    assert [x["ten"] for x in ket["thieu"]] == ["May B"]
    assert [x["ten"] for x in ket["thua"]] == ["May dan keo chua vao so"]
    assert kk.lay(dot.id).trang_thai == "da_ket"


def test_dot_da_ket_thi_khong_sua_duoc_nua():
    db, svc, kk = _moi_truong()
    a, _b = _hai_tai_san(svc)
    dot = kk.tao_dot(ngay=date(2026, 12, 31))
    d_a = next(d for d in dot.dong if d.tai_san_id == a.id)
    kk.ket_thuc(dot.id)
    with pytest.raises(KiemKeDaKet):
        kk.ghi_ket_qua(dot.id, d_a.id, ket_qua="co")
    with pytest.raises(KiemKeDaKet):
        kk.them_phat_hien(dot.id, ten_phat_hien="Them sau khi ket")


def test_dot_khong_co_thi_bao_404():
    db, svc, kk = _moi_truong()
    with pytest.raises(KiemKeNotFound):
        kk.ket_thuc(999)
