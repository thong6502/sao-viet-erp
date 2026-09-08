"""Engine khấu hao — hàm thuần, không DB. Số trong test là 4 ca thật ở plan/spec.

Nửa đầu: một mốc (chữ ký cũ `trich_mot_ky` / `lich_du_kien`). Nửa sau: NHIỀU mốc — nâng cấp và
giảm lô đẻ mốc mới, mốc cũ giữ nguyên (08/09/2026).
"""
from datetime import date

from app.services.tai_san.khau_hao import (
    Moc,
    lich_du_kien,
    lich_khau_hao,
    luy_ke_den,
    muc_thang,
    muc_trich_thang,
    trich_mot_ky,
)


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


# --- Nhiều mốc -------------------------------------------------------------------------------

KOMORI = Moc(tu_ngay=date(2026, 3, 10), nguyen_gia=3_300_000_000, co_so_trich=3_300_000_000,
             so_thang_con=120)
#: Nâng cấp 15/04/2026 +100tr, 118 tháng ⇒ áp từ 01/05, lũy kế trước đó 47.016.129.
NANG_CAP = Moc(tu_ngay=date(2026, 5, 1), nguyen_gia=3_400_000_000, co_so_trich=3_352_983_871,
               so_thang_con=118, luy_ke_dau=47_016_129)


def test_hai_moc_thang_truoc_moc_moi_giu_co_so_cu():
    mocs = [KOMORI, NANG_CAP]
    assert muc_thang(mocs, 2026, 4) == (27_500_000, 47_016_129)        # mốc cũ
    assert muc_thang(mocs, 2026, 5) == (28_415_117, 75_431_246)        # mốc mới: 3.352.983.871 // 118
    lich = lich_khau_hao(mocs)
    assert sum(d.muc_trich for d in lich) == 3_400_000_000             # tổng cả đời = NG mới
    assert lich[-1].con_lai == 0


def test_thu_tu_moc_dua_vao_khong_quan_trong():
    assert lich_khau_hao([NANG_CAP, KOMORI]) == lich_khau_hao([KOMORI, NANG_CAP])


def test_luy_ke_den_truoc_moc_dau_la_so_mang_sang():
    polar = Moc(tu_ngay=date(2026, 1, 1), nguyen_gia=450_000_000, co_so_trich=333_750_000,
                so_thang_con=89, luy_ke_dau=116_250_000)
    assert luy_ke_den([polar], 2025, 12) == 116_250_000
    assert luy_ke_den([polar], 2026, 1) == 120_000_000
    assert luy_ke_den([polar], 2040, 1) == 450_000_000                 # hết đời = nguyên giá


def test_moc_giam_lo_thang_truoc_khong_ve_0():
    lo = Moc(tu_ngay=date(2026, 7, 1), nguyen_gia=28_800_000, co_so_trich=28_800_000,
             so_thang_con=24)
    sau = Moc(tu_ngay=date(2026, 12, 1), nguyen_gia=26_400_000, co_so_trich=20_900_000,
              so_thang_con=19, luy_ke_dau=5_500_000)
    assert luy_ke_den([lo, sau], 2026, 11) == 6_000_000
    assert muc_thang([lo, sau], 2026, 12) == (1_100_000, 6_600_000)
    assert lich_khau_hao([lo, sau])[-1].con_lai == 0


def test_ngay_giam_cat_lich_o_moi_moc():
    mocs = [KOMORI, NANG_CAP]
    lich = lich_khau_hao(mocs, ngay_giam=date(2026, 6, 15))
    assert (lich[-1].nam, lich[-1].thang) == (2026, 6)
    assert lich[-1].muc_trich == 28_415_117 * 15 // 30
    assert muc_thang(mocs, 2026, 7, ngay_giam=date(2026, 6, 15))[0] == 0


def test_khong_moc_thi_lich_rong():
    assert lich_khau_hao([]) == []
    assert luy_ke_den([], 2026, 1) == 0
    assert muc_thang([], 2026, 1) == (0, 0)


def test_muc_trich_0_khong_lap_vo_tan():
    """Nguyên giá 10đ chia 120 tháng ⇒ mức 0 mỗi tháng — vòng lặp phải tự dừng."""
    ti_hon = Moc(tu_ngay=date(2026, 1, 1), nguyen_gia=10, co_so_trich=10, so_thang_con=120)
    assert lich_khau_hao([ti_hon]) == []
    assert luy_ke_den([ti_hon], 2030, 1) == 0
