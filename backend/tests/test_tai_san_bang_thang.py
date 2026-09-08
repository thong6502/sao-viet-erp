"""Bảng khấu hao THÁNG — tính tại chỗ từ sổ, không kỳ, không chốt (chốt 08/09/2026).

Thay `test_tai_san_ky.py`: không còn Tính / Chốt / Mở, nên cũng không còn "kỳ trước chưa chốt",
"kỳ đã chốt không tính lại", "mở kỳ trừ lũy kế". Hỏi tháng nào cũng ra đúng một số. Mỗi dòng kèm
sự kiện của tháng (chip ngắn + câu trước → sau) để hai tab nối được với nhau.
"""
from datetime import date

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base
import app.models  # noqa: F401
from app.models.department import Department
from app.models.tai_san import LOAI_CCDC, LOAI_TSCD, NGUON_DAU_KY, TT_DA_GIAM, TaiSan
from app.repositories.tai_san_repo import TaiSanRepository
from app.services.tai_san.bang_thang import bang_thang
from app.services.tai_san.service import TaiSanService, mocs_cua


def _moi_truong():
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(eng)
    db = sessionmaker(bind=eng)()
    return db, TaiSanService(TaiSanRepository(db))


def _komori(svc, **over):
    return svc.ghi_tang(dict(
        ten="May in Komori 4 mau", loai=LOAI_TSCD, so_thang=120,
        ngay_su_dung=date(2026, 3, 10),
        chi_phi=[{"dien_giai": "Nguyen gia", "so_tien": 3_300_000_000}],
        **over,
    ))


def _lo_cao_su(svc):
    return svc.ghi_tang(dict(
        ten="Tam cao su offset", loai=LOAI_CCDC, so_luong=12, don_gia=2_400_000,
        so_thang=24, ngay_su_dung=date(2026, 7, 1),
    ))


def test_thang_dau_tinh_theo_ngay():
    db, svc = _moi_truong()
    t = _komori(svc)
    b = bang_thang(db, 2026, 3)
    assert len(b) == 1
    assert b[0]["tai_san_id"] == t.id and b[0]["ma"] == t.ma
    assert b[0]["muc_trich"] == 19_516_129
    assert b[0]["luy_ke"] == 19_516_129
    assert b[0]["con_lai"] == 3_280_483_871


def test_thang_chua_toi_moc_thi_khong_co_dong():
    db, svc = _moi_truong()
    _komori(svc)
    assert bang_thang(db, 2026, 2) == []


def test_hoi_lai_bao_nhieu_lan_cung_mot_so():
    db, svc = _moi_truong()
    _komori(svc)
    lan1 = bang_thang(db, 2026, 8)
    lan2 = bang_thang(db, 2026, 8)
    assert lan1 == lan2
    assert lan1[0]["muc_trich"] == 27_500_000
    assert lan1[0]["luy_ke"] == 157_016_129


def test_nhieu_tai_san_moi_mon_mot_dong():
    db, svc = _moi_truong()
    _komori(svc)
    _lo_cao_su(svc)
    b = bang_thang(db, 2026, 7)
    assert [r["muc_trich"] for r in b] == [1_200_000, 27_500_000]     # xếp theo mã: CC- trước TS-
    assert [r["so_luong"] for r in b] == [12, 1]
    assert sum(r["muc_trich"] for r in b) == 28_700_000


def test_bo_phan_la_bo_phan_dang_giu():
    db, svc = _moi_truong()
    to_in = Department(name="To In", code="PB801")
    to_be = Department(name="To Be", code="PB802")
    db.add_all([to_in, to_be])
    db.commit()
    t = _komori(svc, bo_phan_id=to_in.id)
    assert bang_thang(db, 2026, 4)[0]["bo_phan_ten"] == "To In"
    svc.dieu_chuyen(t.id, ngay=date(2026, 5, 10), bo_phan_moi_id=to_be.id)
    assert bang_thang(db, 2026, 4)[0]["bo_phan_ten"] == "To Be"        # không giữ lịch sử theo tháng


def test_dong_cu_da_ghi_giam_khong_len_bang_thang_sau():
    """Ghi giảm đã bỏ (08/09/2026) nhưng dòng cũ còn `da_giam` + `ngay_giam`: engine vẫn ngừng
    trích từ ngày đó, tháng giảm "còn lại" hiện 0 (đã ra khỏi sổ), tháng sau không có dòng."""
    db, svc = _moi_truong()
    t = _komori(svc)
    t.trang_thai = TT_DA_GIAM
    t.ngay_giam = date(2026, 9, 15)
    db.commit()
    r = bang_thang(db, 2026, 9)[0]
    assert r["muc_trich"] == 13_750_000 and r["luy_ke"] == 170_766_129 and r["con_lai"] == 0
    assert bang_thang(db, 2026, 10) == []


def test_het_khau_hao_thi_thoi():
    db, svc = _moi_truong()
    _lo_cao_su(svc)
    cuoi = bang_thang(db, 2028, 6)
    assert cuoi[0]["muc_trich"] == 1_200_000 and cuoi[0]["con_lai"] == 0
    assert cuoi[0]["su_kien"][0]["loai"] == "cuoi" and cuoi[0]["su_kien"][0]["nhan"] == "Tháng cuối"
    assert cuoi[0]["dien_giai"].startswith("Hết khấu hao")
    assert bang_thang(db, 2028, 7) == []


def test_dong_cu_chua_co_moc_van_tinh_duoc():
    """Tài sản có trước mg 0281 (chưa có dòng mốc) ⇒ bộ ba trên `tai_san` là mốc duy nhất."""
    db, svc = _moi_truong()
    t = TaiSan(
        ma="TS-0099", ten="May dao xen Polar (dong cu)", loai=LOAI_TSCD,
        nguyen_gia=450_000_000, so_thang=120, ngay_su_dung=date(2023, 6, 1),
        co_so_trich=333_750_000, so_thang_con=89, moc_tu_ngay=date(2026, 1, 1),
        nguon_vao=NGUON_DAU_KY, hao_mon_dau_ky=116_250_000, thang_da_trich_dau_ky=31,
    )
    db.add(t)
    db.commit()
    mocs = mocs_cua(svc.repo.lay(t.id))
    assert len(mocs) == 1 and mocs[0].luy_ke_dau == 116_250_000
    b = bang_thang(db, 2026, 1)
    assert b[0]["muc_trich"] == 3_750_000 and b[0]["luy_ke"] == 120_000_000


def test_su_kien_thang_dau_nang_cap_dieu_chuyen():
    """Chủ 08/09: hai tab phải liên quan — tháng có chuyện phải nói số trước → sau."""
    db, svc = _moi_truong()
    to_be = Department(name="To Be", code="PB802")
    db.add(to_be)
    db.commit()
    t = _komori(svc)
    dau = bang_thang(db, 2026, 3)[0]
    assert dau["dien_giai"] == "Dùng từ 10/03: tháng đầu trích 22/31 ngày"
    assert dau["su_kien"] == [{
        "loai": "dau", "nhan": "Tháng đầu 22/31 ngày",
        "chi_tiet": "Dùng từ 10/03: tháng đầu trích 22/31 ngày",
    }]
    binh_thuong = bang_thang(db, 2026, 4)[0]
    assert binh_thuong["dien_giai"] is None and binh_thuong["su_kien"] == []

    svc.nang_cap(t.id, ngay=date(2026, 4, 15), so_tien=100_000_000, so_thang_con_lai=118)
    svc.dieu_chuyen(t.id, ngay=date(2026, 5, 10), bo_phan_moi_id=to_be.id)
    assert bang_thang(db, 2026, 4)[0]["dien_giai"] is None         # tháng chứng từ: vẫn mức cũ
    t5 = bang_thang(db, 2026, 5)[0]
    assert t5["dien_giai"] == (
        "Sửa chữa lớn +100.000.000 ngày 15/04: nguyên giá 3.300.000.000 → 3.400.000.000, "
        "mức tháng 27.500.000 → 28.415.117; Điều chuyển sang To Be ngày 10/05"
    )
    assert [(s["loai"], s["nhan"]) for s in t5["su_kien"]] == [
        ("nang_cap", "Sửa chữa lớn +100.000.000"), ("chuyen", "Chuyển sang To Be 10/05"),
    ]


def test_su_kien_nap_dau_ky():
    db, svc = _moi_truong()
    t = svc.nap_dau_ky(dict(
        ten="May dao xen Polar", loai=LOAI_TSCD, so_thang=120,
        ngay_su_dung=date(2023, 6, 1), moc_tu_ngay=date(2026, 1, 1),
        chi_phi=[{"dien_giai": "Nguyen gia", "so_tien": 450_000_000}],
        thang_da_trich_dau_ky=31, hao_mon_dau_ky=116_250_000,
    ))
    dau = bang_thang(db, 2026, 1)[0]
    assert dau["tai_san_id"] == t.id
    assert dau["dien_giai"] == "Bắt đầu tính trên phần mềm, hao mòn mang sang 116.250.000"
    assert dau["su_kien"][0]["nhan"] == "Số dư mang sang"
    assert bang_thang(db, 2026, 2)[0]["dien_giai"] is None


def test_thang_ngoai_1_12_bi_chan():
    db, svc = _moi_truong()
    with pytest.raises(ValueError):
        bang_thang(db, 2026, 13)
