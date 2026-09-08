"""Sổ tài sản — ghi tăng, nạp đầu kỳ, hao mòn đọc từ lịch, khoá ô số sau khi có chứng từ.

Không còn kỳ chốt (08/09/2026): "đã trích tới tháng X" là `svc.hao_mon_den(t, nam, thang)`, hỏi
lúc nào cũng ra đúng một số. Luật khoá: có chứng từ biến động thì không sửa ô số; xoá thì luôn
được (ghi giảm đã bỏ — xoá là lối ra cho món không dùng nữa).
"""
from datetime import date

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base
import app.models  # noqa: F401
from app.models.department import Department
from app.models.tai_san import (
    LOAI_CCDC,
    LOAI_TSCD,
    MOC_DAU_KY,
    MOC_GHI_TANG,
    MOC_SUA,
    TaiSanBienDong,
    TaiSanMoc,
)
from app.repositories.tai_san_repo import TaiSanRepository
from app.services.tai_san.service import (
    TaiSanDaCoChungTu,
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


def _polar():
    return dict(
        ten="May dao xen Polar", loai=LOAI_TSCD, so_thang=120,
        ngay_su_dung=date(2023, 6, 1), moc_tu_ngay=date(2026, 1, 1),
        chi_phi=[{"dien_giai": "Nguyen gia", "so_tien": 450_000_000}],
        thang_da_trich_dau_ky=31, hao_mon_dau_ky=116_250_000,
    )


def _bo_phan(db, ten="To Be", ma="PB901"):
    bp = Department(name=ten, code=ma)
    db.add(bp)
    db.commit()
    return bp


def test_ghi_tang_cong_nguyen_gia_tu_cac_dong_chi_phi():
    db, svc = _svc()
    t = svc.ghi_tang(_komori())
    assert t.nguyen_gia == 3_300_000_000
    assert t.co_so_trich == 3_300_000_000
    assert t.so_thang_con == 120
    assert t.moc_tu_ngay == date(2026, 3, 10)
    assert t.ma.startswith("TS-")
    assert t.ghi_chu == "211 / 6274 - to In"
    assert [m.nguon for m in t.moc] == [MOC_GHI_TANG]
    assert t.moc[0].luy_ke_dau == 0


def test_hao_mon_tinh_tu_lich_khong_can_chot():
    db, svc = _svc()
    t = svc.ghi_tang(_komori())
    assert svc.hao_mon_den(t, 2026, 2) == 0
    assert svc.hao_mon_den(t, 2026, 3) == 19_516_129
    assert svc.hao_mon_den(t, 2026, 8) == 157_016_129
    assert svc.muc_thang(t, 2026, 4) == (27_500_000, 47_016_129)
    # hỏi lại bao nhiêu lần cũng ra một số — không có gì để "tính lại"
    assert svc.hao_mon_den(t, 2026, 8) == 157_016_129


def test_hao_mon_hien_tai_la_toi_het_thang_truoc():
    db, svc = _svc()
    t = svc.ghi_tang(_komori())
    assert svc.hao_mon_hien_tai(t, hom_nay=date(2026, 9, 8)) == 157_016_129
    assert svc.hao_mon_hien_tai(t, hom_nay=date(2026, 3, 20)) == 0        # tháng 3 chưa hết
    assert svc.hao_mon_hien_tai(t, hom_nay=date(2026, 4, 1)) == 19_516_129
    assert [(d.nam, d.thang) for d in svc.lich_da_tinh(t, hom_nay=date(2026, 5, 3))] == [
        (2026, 3), (2026, 4),
    ]


def test_du_kien_hien_ngay_sau_ghi_tang():
    db, svc = _svc()
    t = svc.ghi_tang(_komori())
    lich = svc.du_kien(t.id)
    assert lich[0].muc_trich == 19_516_129
    assert lich[1].muc_trich == 27_500_000
    assert sum(d.muc_trich for d in lich) == 3_300_000_000


def test_nap_dau_ky_mang_hao_mon_sang():
    db, svc = _svc()
    t = svc.nap_dau_ky(_polar())
    assert t.nguyen_gia == 450_000_000
    assert t.hao_mon_dau_ky == 116_250_000
    assert t.co_so_trich == 333_750_000
    assert t.so_thang_con == 89
    assert t.moc[0].nguon == MOC_DAU_KY and t.moc[0].luy_ke_dau == 116_250_000
    assert svc.hao_mon_den(t, 2025, 12) == 116_250_000      # trước mốc = số mang sang
    assert svc.hao_mon_den(t, 2026, 1) == 120_000_000
    assert svc.du_kien(t.id)[0].muc_trich == 3_750_000


def test_nap_dau_ky_ep_moc_ve_ngay_1():
    """Số mang sang là số tròn tháng — không có chuyện "từ 15/01 chia lẻ ngày"."""
    db, svc = _svc()
    t = svc.nap_dau_ky({**_polar(), "moc_tu_ngay": date(2026, 1, 15)})
    assert t.moc_tu_ngay == date(2026, 1, 1)
    assert svc.muc_thang(t, 2026, 1) == (3_750_000, 120_000_000)


def test_nap_dau_ky_hao_mon_phai_nho_hon_nguyen_gia():
    db, svc = _svc()
    with pytest.raises(TaiSanValidationError):
        svc.nap_dau_ky({**_polar(), "hao_mon_dau_ky": 450_000_000})
    with pytest.raises(TaiSanValidationError):
        svc.nap_dau_ky({**_polar(), "thang_da_trich_dau_ky": 120})


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


def test_sua_o_so_khi_chua_co_chung_tu_thi_dung_lai_moc():
    db, svc = _svc()
    t = svc.ghi_tang(_komori())
    svc.sua(t.id, {"so_thang": 96})
    db.refresh(t)
    assert t.so_thang_con == 96
    assert [m.nguon for m in t.moc] == [MOC_SUA]
    assert svc.muc_thang(t, 2026, 4)[0] == 3_300_000_000 // 96
    assert db.query(TaiSanMoc).count() == 1                  # mốc cũ bị thay, không chồng


def test_chan_sua_o_anh_huong_so_khi_da_co_chung_tu():
    db, svc = _svc()
    t = svc.ghi_tang(_komori())
    bp = _bo_phan(db)
    svc.dieu_chuyen(t.id, ngay=date(2026, 4, 1), bo_phan_moi_id=bp.id)
    with pytest.raises(TaiSanDaCoChungTu):
        svc.sua(t.id, {"so_thang": 96})
    # ô mô tả vẫn sửa được
    t2 = svc.sua(t.id, {"nguoi_quan_ly": "Anh Tu", "ghi_chu": "211 / 6274 - to Be"})
    assert t2.nguoi_quan_ly == "Anh Tu"
    assert t2.ghi_chu == "211 / 6274 - to Be"


def test_xoa_duoc_ca_khi_da_co_chung_tu():
    """Không có nghiệp vụ ghi giảm (chủ bỏ 08/09/2026) ⇒ xoá là lối ra duy nhất cho món bán /
    hỏng — kể cả khi đã điều chuyển / nâng cấp; chứng từ và mốc đi theo."""
    db, svc = _svc()
    t = svc.ghi_tang(_komori())
    bp = _bo_phan(db)
    svc.dieu_chuyen(t.id, ngay=date(2026, 4, 1), bo_phan_moi_id=bp.id)
    svc.nang_cap(t.id, ngay=date(2026, 5, 1), so_tien=10_000_000, so_thang_con_lai=100)
    svc.xoa(t.id)
    assert svc.repo.lay(t.id) is None
    assert db.query(TaiSanBienDong).count() == 0
    assert db.query(TaiSanMoc).count() == 0


def test_xoa_duoc_khi_chua_co_chung_tu_va_moc_di_theo():
    db, svc = _svc()
    t = svc.ghi_tang(_komori())
    svc.xoa(t.id)
    assert svc.repo.lay(t.id) is None
    assert db.query(TaiSanMoc).count() == 0


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
