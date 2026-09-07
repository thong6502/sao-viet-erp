"""Sổ tài sản — ghi tăng, nạp đầu kỳ, chặn sửa sau khi kỳ đã chốt."""
from datetime import date

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base
import app.models  # noqa: F401
from app.models.tai_san import KY_DA_CHOT, LOAI_CCDC, LOAI_TSCD, TaiSanKhauHao, TaiSanKy
from app.repositories.tai_san_repo import TaiSanRepository
from app.services.tai_san.service import (
    TaiSanDaChotKy,
    TaiSanService,
    TaiSanTrung,
    TaiSanValidationError,
)


def _svc():
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(eng)
    db = sessionmaker(bind=eng)()
    return db, TaiSanService(TaiSanRepository(db))


def _komori(**over):
    base = dict(
        ten="May in Komori 4 mau", loai=LOAI_TSCD, so_thang=120,
        ngay_su_dung=date(2026, 3, 10),
        chi_phi=[
            {"dien_giai": "Gia mua", "so_tien": 3_200_000_000},
            {"dien_giai": "Van chuyen", "so_tien": 40_000_000},
            {"dien_giai": "Lap dat chay thu", "so_tien": 60_000_000},
        ],
        ghi_chu="211 / 6274 - to In",
    )
    base.update(over)
    return base


def test_ghi_tang_cong_nguyen_gia_tu_cac_dong_chi_phi():
    db, svc = _svc()
    t = svc.ghi_tang(_komori())
    assert t.nguyen_gia == 3_300_000_000
    assert t.co_so_trich == 3_300_000_000
    assert t.so_thang_con == 120
    assert t.moc_tu_ngay == date(2026, 3, 10)
    assert t.hao_mon_luy_ke == 0
    assert t.ma.startswith("TS-")
    assert t.ghi_chu == "211 / 6274 - to In"


def test_du_kien_hien_ngay_sau_ghi_tang():
    db, svc = _svc()
    t = svc.ghi_tang(_komori())
    lich = svc.du_kien(t.id)
    assert lich[0].muc_trich == 19_516_129
    assert lich[1].muc_trich == 27_500_000
    assert sum(d.muc_trich for d in lich) == 3_300_000_000


def test_nap_dau_ky_tru_hao_mon_luy_ke():
    db, svc = _svc()
    t = svc.nap_dau_ky(dict(
        ten="May dao xen Polar", loai=LOAI_TSCD, so_thang=120,
        ngay_su_dung=date(2023, 6, 1), moc_tu_ngay=date(2026, 1, 1),
        chi_phi=[{"dien_giai": "Nguyen gia", "so_tien": 450_000_000}],
        thang_da_trich_dau_ky=31, hao_mon_dau_ky=116_250_000,
    ))
    assert t.nguyen_gia == 450_000_000
    assert t.hao_mon_luy_ke == 116_250_000
    assert t.co_so_trich == 333_750_000
    assert t.so_thang_con == 89
    assert svc.du_kien(t.id)[0].muc_trich == 3_750_000


def test_ccdc_nhap_theo_lo():
    db, svc = _svc()
    t = svc.ghi_tang(dict(
        ten="Tam cao su offset", loai=LOAI_CCDC, so_luong=12, don_gia=2_400_000,
        so_thang=24, ngay_su_dung=date(2026, 7, 1),
    ))
    assert t.nguyen_gia == 28_800_000
    assert t.ma.startswith("CC-")
    assert svc.du_kien(t.id)[0].muc_trich == 1_200_000


def test_ten_trung_ma_thi_bao_loi():
    db, svc = _svc()
    t = svc.ghi_tang(_komori())
    with pytest.raises(TaiSanTrung):
        svc.ghi_tang(_komori(ma=t.ma))


def test_so_thang_phai_duong():
    db, svc = _svc()
    with pytest.raises(TaiSanValidationError):
        svc.ghi_tang(_komori(so_thang=0))


def test_nguyen_gia_phai_duong():
    db, svc = _svc()
    with pytest.raises(TaiSanValidationError):
        svc.ghi_tang(_komori(chi_phi=[]))


def test_chan_sua_o_anh_huong_so_khi_ky_da_chot():
    db, svc = _svc()
    t = svc.ghi_tang(_komori())
    db.add(TaiSanKy(ky_nam=2026, ky_thang=3, trang_thai=KY_DA_CHOT))
    db.add(TaiSanKhauHao(tai_san_id=t.id, ky_nam=2026, ky_thang=3,
                         muc_trich=19_516_129, luy_ke=19_516_129, con_lai=3_280_483_871))
    db.commit()
    with pytest.raises(TaiSanDaChotKy):
        svc.sua(t.id, {"so_thang": 96})
    # ô mô tả vẫn sửa được
    t2 = svc.sua(t.id, {"vi_tri": "Xuong 2", "ghi_chu": "211 / 6274 - to Be"})
    assert t2.vi_tri == "Xuong 2"


def test_chan_xoa_khi_da_co_ky_chot():
    db, svc = _svc()
    t = svc.ghi_tang(_komori())
    db.add(TaiSanKy(ky_nam=2026, ky_thang=3, trang_thai=KY_DA_CHOT))
    db.add(TaiSanKhauHao(tai_san_id=t.id, ky_nam=2026, ky_thang=3,
                         muc_trich=19_516_129, luy_ke=19_516_129, con_lai=3_280_483_871))
    db.commit()
    with pytest.raises(TaiSanDaChotKy):
        svc.xoa(t.id)


def test_danh_sach_loc_va_cat_trang_o_sql():
    db, svc = _svc()
    for i in range(3):
        svc.ghi_tang(dict(
            ten=f"Tam cao su {i}", loai=LOAI_CCDC, so_luong=12, don_gia=2_400_000,
            so_thang=24, ngay_su_dung=date(2026, 7, 1),
        ))
    svc.ghi_tang(_komori())
    rows, tong = svc.repo.danh_sach(loai=LOAI_CCDC, offset=0, limit=2)
    assert tong == 3
    assert len(rows) == 2
    rows, tong = svc.repo.danh_sach(q="Komori")
    assert tong == 1
