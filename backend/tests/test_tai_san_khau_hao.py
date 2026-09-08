"""Engine khấu hao — hàm thuần, không DB. Số trong test là 4 ca thật ở plan/spec."""
from datetime import date

from app.services.tai_san.khau_hao import lich_du_kien, muc_trich_thang, trich_mot_ky


def test_muc_trich_tron_thang():
    assert muc_trich_thang(3_300_000_000, 120) == 27_500_000


def test_thang_dau_tinh_theo_ngay():
    """Komori dùng từ 10/03/2026: 22/31 ngày của tháng 3."""
    assert trich_mot_ky(
        co_so_trich=3_300_000_000, so_thang_con=120, moc_tu_ngay=date(2026, 3, 10),
        nguyen_gia=3_300_000_000, luy_ke=0, nam=2026, thang=3,
    ) == 19_516_129


def test_thang_tron_sau_thang_dau():
    assert trich_mot_ky(
        co_so_trich=3_300_000_000, so_thang_con=120, moc_tu_ngay=date(2026, 3, 10),
        nguyen_gia=3_300_000_000, luy_ke=19_516_129, nam=2026, thang=4,
    ) == 27_500_000


def test_chua_toi_moc_thi_khong_trich():
    assert trich_mot_ky(
        co_so_trich=3_300_000_000, so_thang_con=120, moc_tu_ngay=date(2026, 3, 10),
        nguyen_gia=3_300_000_000, luy_ke=0, nam=2026, thang=2,
    ) == 0


def test_nap_dau_ky_polar():
    """450tr / 120 tháng, đã trích 31 tháng ⇒ 333.750.000 chia 89 tháng."""
    assert trich_mot_ky(
        co_so_trich=333_750_000, so_thang_con=89, moc_tu_ngay=date(2026, 1, 1),
        nguyen_gia=450_000_000, luy_ke=116_250_000, nam=2026, thang=8,
    ) == 3_750_000


def test_sau_nang_cap():
    """Komori +180tr từ 01/09/2026: (3.480.000.000 − 157.016.129) / 114 tháng."""
    assert trich_mot_ky(
        co_so_trich=3_322_983_871, so_thang_con=114, moc_tu_ngay=date(2026, 9, 1),
        nguyen_gia=3_480_000_000, luy_ke=157_016_129, nam=2026, thang=9,
    ) == 29_148_981


def test_ccdc_giam_mot_phan_lo():
    """Lô 12 tấm cao su bỏ 1 tấm: 20.900.000 chia 19 tháng còn lại."""
    assert trich_mot_ky(
        co_so_trich=20_900_000, so_thang_con=19, moc_tu_ngay=date(2026, 12, 1),
        nguyen_gia=28_800_000, luy_ke=6_000_000, nam=2026, thang=12,
    ) == 1_100_000


def test_thang_ghi_giam_tinh_toi_ngay_giam():
    """Ngừng trích từ ngày giảm: 15/30 ngày của tháng 9."""
    assert trich_mot_ky(
        co_so_trich=3_300_000_000, so_thang_con=120, moc_tu_ngay=date(2026, 3, 10),
        nguyen_gia=3_300_000_000, luy_ke=157_016_129, nam=2026, thang=9,
        ngay_giam=date(2026, 9, 15),
    ) == 13_750_000


def test_sau_ngay_giam_khong_trich_nua():
    assert trich_mot_ky(
        co_so_trich=3_300_000_000, so_thang_con=120, moc_tu_ngay=date(2026, 3, 10),
        nguyen_gia=3_300_000_000, luy_ke=170_766_129, nam=2026, thang=10,
        ngay_giam=date(2026, 9, 15),
    ) == 0


def test_ky_cuoi_khong_trich_qua_nguyen_gia():
    """Còn lại 1.000.000 mà mức tháng 27.500.000 ⇒ chỉ trích nốt 1.000.000."""
    assert trich_mot_ky(
        co_so_trich=3_300_000_000, so_thang_con=120, moc_tu_ngay=date(2026, 3, 10),
        nguyen_gia=3_300_000_000, luy_ke=3_299_000_000, nam=2036, thang=3,
    ) == 1_000_000


def test_het_khau_hao_thi_thoi():
    assert trich_mot_ky(
        co_so_trich=3_300_000_000, so_thang_con=120, moc_tu_ngay=date(2026, 3, 10),
        nguyen_gia=3_300_000_000, luy_ke=3_300_000_000, nam=2036, thang=4,
    ) == 0


def test_lich_du_kien_cong_du_bang_nguyen_gia():
    """Tổng mọi kỳ = nguyên giá — phần lẻ do làm tròn dồn vào kỳ cuối."""
    lich = lich_du_kien(
        co_so_trich=3_300_000_000, so_thang_con=120, moc_tu_ngay=date(2026, 3, 10),
        nguyen_gia=3_300_000_000, luy_ke=0,
    )
    assert lich[0].nam == 2026 and lich[0].thang == 3
    assert lich[0].muc_trich == 19_516_129
    assert sum(d.muc_trich for d in lich) == 3_300_000_000
    assert lich[-1].con_lai == 0
