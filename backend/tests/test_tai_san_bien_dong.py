"""Hai chứng từ biến động: điều chuyển · nâng cấp.

Không còn kỳ chốt (08/09/2026): "đã trích tới tháng X" đọc thẳng từ lịch (`svc.hao_mon_den`).
Nâng cấp đẻ MỐC MỚI, mốc cũ giữ ⇒ lỗi 🔴 #1 của bản rà 08/09 (tháng chứng từ mất trích) không
còn. Ghi giảm đã bỏ cùng ngày (chủ: "cái ghi giảm bỏ đi") — món không dùng nữa thì xoá; dòng cũ
còn `da_giam` chỉ được đọc.
"""
from datetime import date

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base
import app.models  # noqa: F401
from app.models.department import Department
from app.models.tai_san import LOAI_TSCD, MOC_NANG_CAP, TT_DA_GIAM
from app.repositories.tai_san_repo import TaiSanRepository
from app.services.tai_san.service import TaiSanService, TaiSanValidationError


def _moi_truong():
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(eng)
    db = sessionmaker(bind=eng)()
    return db, TaiSanService(TaiSanRepository(db))


def _komori(svc):
    return svc.ghi_tang(dict(
        ten="May in Komori 4 mau", loai=LOAI_TSCD, so_thang=120,
        ngay_su_dung=date(2026, 3, 10),
        chi_phi=[{"dien_giai": "Nguyen gia", "so_tien": 3_300_000_000}],
    ))


def test_dieu_chuyen_doi_bo_phan_khong_dung_toi_so():
    db, svc = _moi_truong()
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
    assert len(t.moc) == 1                                   # không đẻ mốc


def test_nang_cap_tinh_lai_muc_trich_tu_ky_sau():
    """Komori +180tr từ 01/09/2026, lũy kế 157.016.129 ⇒ 3.322.983.871 / 114 = 29.148.981."""
    db, svc = _moi_truong()
    t = _komori(svc)
    assert svc.hao_mon_den(t, 2026, 8) == 157_016_129

    svc.nang_cap(t.id, ngay=date(2026, 9, 1), so_tien=180_000_000, so_thang_con_lai=114)
    db.refresh(t)
    assert t.nguyen_gia == 3_480_000_000
    assert t.co_so_trich == 3_322_983_871
    assert t.so_thang_con == 114
    assert t.moc_tu_ngay == date(2026, 9, 1)
    assert t.moc[-1].nguon == MOC_NANG_CAP and t.moc[-1].luy_ke_dau == 157_016_129
    assert svc.hao_mon_den(t, 2026, 8) == 157_016_129        # quá khứ không đổi
    assert svc.muc_thang(t, 2026, 9) == (29_148_981, 186_165_110)
    assert sum(d.muc_trich for d in svc.du_kien(t.id)) == 3_480_000_000


def test_nang_cap_giua_thang_ap_tu_thang_sau_thang_chung_tu_van_trich_gia_cu():
    """🔴 #1 bản rà 08/09: trước đây tháng chứng từ trích 0 vì bộ ba bị ghi đè tại chỗ."""
    db, svc = _moi_truong()
    t = _komori(svc)
    svc.nang_cap(t.id, ngay=date(2026, 4, 15), so_tien=100_000_000, so_thang_con_lai=118)
    db.refresh(t)
    assert t.moc_tu_ngay == date(2026, 5, 1)
    assert svc.muc_thang(t, 2026, 4)[0] == 27_500_000        # tháng 4: mốc cũ
    assert svc.muc_thang(t, 2026, 5)[0] == 28_415_117        # (3,4 tỷ − 47.016.129) // 118
    assert svc.hao_mon_den(t, 2026, 5) == 75_431_246


def test_dong_cu_da_ghi_giam_van_ngung_trich_va_khong_nang_cap():
    """Nghiệp vụ ghi giảm đã bỏ, nhưng dòng cũ còn `da_giam` + `ngay_giam` thì engine vẫn ngừng
    trích từ ngày đó và không cho nâng cấp — chỉ đọc, không tạo mới."""
    db, svc = _moi_truong()
    t = _komori(svc)
    t.trang_thai = TT_DA_GIAM
    t.ngay_giam = date(2026, 9, 15)
    db.commit()
    assert svc.muc_thang(t, 2026, 9)[0] == 13_750_000        # 15/30 ngày
    assert svc.hao_mon_den(t, 2026, 10) == 170_766_129
    assert (svc.lich(t)[-1].nam, svc.lich(t)[-1].thang) == (2026, 9)
    with pytest.raises(TaiSanValidationError):
        svc.nang_cap(t.id, ngay=date(2026, 10, 1), so_tien=10_000_000, so_thang_con_lai=100)


def test_chung_tu_truoc_ngay_su_dung_bi_chan():
    db, svc = _moi_truong()
    t = _komori(svc)
    with pytest.raises(TaiSanValidationError):
        svc.nang_cap(t.id, ngay=date(2026, 1, 1), so_tien=10_000_000, so_thang_con_lai=100)


def test_nang_cap_so_thang_con_lai_phai_duong():
    db, svc = _moi_truong()
    t = _komori(svc)
    with pytest.raises(TaiSanValidationError):
        svc.nang_cap(t.id, ngay=date(2026, 4, 1), so_tien=10_000_000, so_thang_con_lai=0)
