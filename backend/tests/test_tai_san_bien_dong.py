"""Ba chứng từ biến động: điều chuyển · nâng cấp · ghi giảm (kể cả CCDC một phần lô)."""
from datetime import date

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base
import app.models  # noqa: F401
from app.models.department import Department
from app.models.tai_san import LOAI_CCDC, LOAI_TSCD, TT_DA_GIAM, TT_DANG_DUNG
from app.repositories.tai_san_repo import TaiSanRepository
from app.services.tai_san.ky_service import KyService
from app.services.tai_san.service import TaiSanDaChotKy, TaiSanService, TaiSanValidationError


def _moi_truong():
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(eng)
    db = sessionmaker(bind=eng)()
    return db, TaiSanService(TaiSanRepository(db)), KyService(db)


def _komori(svc):
    return svc.ghi_tang(dict(
        ten="May in Komori 4 mau", loai=LOAI_TSCD, so_thang=120,
        ngay_su_dung=date(2026, 3, 10),
        chi_phi=[{"dien_giai": "Nguyen gia", "so_tien": 3_300_000_000}],
    ))


def test_dieu_chuyen_doi_bo_phan_khong_dung_toi_so():
    db, svc, ky = _moi_truong()
    to_be = Department(name="To Be", code="PB901")
    db.add(to_be)
    db.commit()
    t = _komori(svc)
    svc.dieu_chuyen(t.id, ngay=date(2026, 9, 15), bo_phan_moi_id=to_be.id, ly_do="Chuyen to")
    db.refresh(t)
    assert t.bo_phan_id == to_be.id
    assert t.nguyen_gia == 3_300_000_000
    assert t.co_so_trich == 3_300_000_000
    assert len(t.bien_dong) == 1


def test_nang_cap_tinh_lai_muc_trich_tu_ky_sau():
    """Komori +180tr từ 01/09/2026, lũy kế 157.016.129 ⇒ 3.322.983.871 / 114 = 29.148.981."""
    db, svc, ky = _moi_truong()
    t = _komori(svc)
    for nam, thang in [(2026, 3), (2026, 4), (2026, 5), (2026, 6), (2026, 7), (2026, 8)]:
        ky.tinh(nam, thang)
        ky.chot(nam, thang)
    db.refresh(t)
    assert t.hao_mon_luy_ke == 157_016_129

    svc.nang_cap(t.id, ngay=date(2026, 9, 1), so_tien=180_000_000, so_thang_con_lai=114)
    db.refresh(t)
    assert t.nguyen_gia == 3_480_000_000
    assert t.hao_mon_luy_ke == 157_016_129
    assert t.co_so_trich == 3_322_983_871
    assert t.so_thang_con == 114
    assert t.moc_tu_ngay == date(2026, 9, 1)
    assert ky.tinh(2026, 9)[0].muc_trich == 29_148_981


def test_nang_cap_giua_thang_thi_ap_tu_ky_sau():
    db, svc, ky = _moi_truong()
    t = _komori(svc)
    svc.nang_cap(t.id, ngay=date(2026, 4, 15), so_tien=100_000_000, so_thang_con_lai=118)
    db.refresh(t)
    assert t.moc_tu_ngay == date(2026, 5, 1)


def test_ghi_giam_ngung_trich_va_bao_chenh_lech():
    db, svc, ky = _moi_truong()
    t = svc.nap_dau_ky(dict(
        ten="May in 2 mau cu", loai=LOAI_TSCD, so_thang=120,
        ngay_su_dung=date(2016, 1, 1), moc_tu_ngay=date(2026, 1, 1),
        chi_phi=[{"dien_giai": "Nguyen gia", "so_tien": 800_000_000}],
        thang_da_trich_dau_ky=93, hao_mon_dau_ky=620_000_000,
    ))
    bd = svc.ghi_giam(t.id, ngay=date(2026, 1, 1), ly_do="Nhuong ban", gia_ban=200_000_000)
    db.refresh(t)
    assert t.trang_thai == TT_DA_GIAM
    assert t.ngay_giam == date(2026, 1, 1)
    assert bd.so_tien == 200_000_000
    # giá trị còn lại 180.000.000 → chênh +20.000.000
    assert svc.chenh_lech_thanh_ly(t.id) == 20_000_000
    assert ky.tinh(2026, 2) == []


def test_ccdc_ghi_giam_mot_phan_lo():
    """12 tấm cao su, đã phân bổ 5 kỳ (6.000.000), bỏ 1 tấm từ 01/12/2026."""
    db, svc, ky = _moi_truong()
    t = svc.ghi_tang(dict(
        ten="Tam cao su offset", loai=LOAI_CCDC, so_luong=12, don_gia=2_400_000,
        so_thang=24, ngay_su_dung=date(2026, 7, 1),
    ))
    for thang in (7, 8, 9, 10, 11):
        ky.tinh(2026, thang)
        ky.chot(2026, thang)
    db.refresh(t)
    assert t.hao_mon_luy_ke == 6_000_000

    svc.ghi_giam(t.id, ngay=date(2026, 12, 1), ly_do="Rach 1 tam", so_luong_giam=1)
    db.refresh(t)
    assert t.so_luong == 11
    assert t.trang_thai == TT_DANG_DUNG      # lô còn sống
    assert t.co_so_trich == 20_900_000
    assert t.so_thang_con == 19
    assert ky.tinh(2026, 12)[0].muc_trich == 1_100_000


def test_ccdc_bo_het_lo_thi_tai_san_da_giam():
    db, svc, ky = _moi_truong()
    t = svc.ghi_tang(dict(
        ten="Tam cao su offset", loai=LOAI_CCDC, so_luong=12, don_gia=2_400_000,
        so_thang=24, ngay_su_dung=date(2026, 7, 1),
    ))
    svc.ghi_giam(t.id, ngay=date(2026, 8, 1), ly_do="Bo het", so_luong_giam=12)
    db.refresh(t)
    assert t.so_luong == 0
    assert t.trang_thai == TT_DA_GIAM


def test_chan_chung_tu_roi_vao_ky_da_chot():
    db, svc, ky = _moi_truong()
    t = _komori(svc)
    ky.tinh(2026, 3)
    ky.chot(2026, 3)
    with pytest.raises(TaiSanDaChotKy):
        svc.nang_cap(t.id, ngay=date(2026, 3, 20), so_tien=10_000_000, so_thang_con_lai=100)


def test_nang_cap_so_thang_con_lai_phai_duong():
    db, svc, ky = _moi_truong()
    t = _komori(svc)
    with pytest.raises(TaiSanValidationError):
        svc.nang_cap(t.id, ngay=date(2026, 4, 1), so_tien=10_000_000, so_thang_con_lai=0)


def test_ghi_giam_so_luong_khong_vuot_ton():
    db, svc, ky = _moi_truong()
    t = svc.ghi_tang(dict(
        ten="Tam cao su offset", loai=LOAI_CCDC, so_luong=12, don_gia=2_400_000,
        so_thang=24, ngay_su_dung=date(2026, 7, 1),
    ))
    with pytest.raises(TaiSanValidationError):
        svc.ghi_giam(t.id, ngay=date(2026, 8, 1), ly_do="Mat", so_luong_giam=20)


def test_ghi_giam_hai_lan_bi_chan():
    db, svc, ky = _moi_truong()
    t = _komori(svc)
    svc.ghi_giam(t.id, ngay=date(2026, 5, 1), ly_do="Thanh ly")
    with pytest.raises(TaiSanValidationError):
        svc.ghi_giam(t.id, ngay=date(2026, 6, 1), ly_do="Thanh ly lan hai")
