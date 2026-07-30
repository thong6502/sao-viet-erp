"""Quy đổi đơn vị — hàm thuần, test không cần DB.

Trọng tâm: (1) cùng họ đổi bằng hệ số; (2) khác họ KHÔNG tự đổi mà phải qua cầu có quy cách;
(3) thiếu biến thì nói THIẾU GÌ chứ không đoán số — vì số đoán chảy thẳng vào tiền khoán.
"""
from __future__ import annotations

import pytest

from app.seed_rebuild import _DON_VI_SEED
from app.services.quy_doi_service import don_vi_map, doi, doi_theo_quy_cach, tien_khoan

DVS = don_vi_map([{"ma": m, "ten": t, "ho": h, "he_so_goc": s} for m, t, h, s in _DON_VI_SEED])

# Quy cách THẬT của lệnh thẻ nhân viên (tờ in 860×650, Couché 300, 99 con/tờ).
QC_THE = {"kho_in_dai": 860, "kho_in_rong": 650, "gsm": 300, "so_con": 99}
QC_RUOT = {"kho_in_dai": 860, "kho_in_rong": 650, "gsm": 70, "so_con": 1}


# --- cùng họ ------------------------------------------------------------------


@pytest.mark.parametrize("gia_tri,tu,den,mong_doi", [
    (1_347_190, "cm2", "m2", 134.719),
    (134.719, "m2", "cm2", 1_347_190),
    (0.2035, "tan", "kg", 203.5),
    (203.5, "kg", "tan", 0.2035),
    (10, "ram", "to", 5_000),
    (5_000, "to", "ram", 10),
])
def test_doi_cung_ho(gia_tri, tu, den, mong_doi):
    kq = doi(gia_tri, tu, den, DVS)
    assert kq["gia_tri"] == pytest.approx(mong_doi, rel=1e-4)
    assert kq["dien_giai"]          # luôn khoe cách tính để người đọc kiểm bằng mắt


def test_doi_tra_cuu_duoc_ca_ma_lan_ten():
    """Bảng đơn giá khoán lưu CHỮ HIỂN THỊ ("m²") còn bước lệnh dùng MÃ ("to") — tra cứu phải nhận
    cả hai, không thì đơn giá 150 đ/m² vĩnh viễn báo "chưa khai đơn vị"."""
    assert doi(1, "m²", "cm2", DVS)["gia_tri"] == pytest.approx(10_000)
    assert doi(1, "tấn", "kg", DVS)["gia_tri"] == pytest.approx(1_000)


def test_cung_don_vi_khong_sinh_phep_tinh():
    """Mã và tên của CÙNG một đơn vị ("to" ↔ "tờ") thì đừng in "÷ 1" cho người đọc."""
    kq = doi(5_200, "to", "tờ", DVS)
    assert kq["gia_tri"] == 5_200
    assert "÷" not in kq["dien_giai"] and "×" not in kq["dien_giai"]


def test_cung_ho_cung_he_so_chi_la_cach_goi_khac():
    """cái ↔ cuốn ↔ hộp: cùng họ thành phẩm, hệ số 1 — 1.000 cái LÀ 1.000 cuốn."""
    kq = doi(1_000, "cai", "cuon", DVS)
    assert kq["gia_tri"] == 1_000
    assert "1.000 cái = 1.000 cuốn" in kq["dien_giai"]


# --- khác họ: phải có quy cách -------------------------------------------------


def test_khac_ho_khong_tu_doi_bang_he_so():
    kq = doi(241, "to", "m2", DVS)
    assert "gia_tri" not in kq
    assert kq["thieu"] == ["quy_cach"]


def test_cau_to_sang_m2():
    kq = doi_theo_quy_cach(241, "to", "m2", QC_THE, DVS)
    assert kq["gia_tri"] == pytest.approx(134.719, rel=1e-4)
    assert "241 tờ" in kq["dien_giai"] and "m²" in kq["dien_giai"]


def test_cau_to_sang_kg_va_tan():
    """Cầu nhả ra đơn vị GỐC của họ (kg) rồi đi tiếp bằng hệ số → tấn, khỏi viết cầu riêng."""
    kg = doi_theo_quy_cach(5_200, "to", "kg", QC_RUOT, DVS)
    tan = doi_theo_quy_cach(5_200, "to", "tan", QC_RUOT, DVS)
    assert kg["gia_tri"] == pytest.approx(203.48, rel=1e-3)
    assert tan["gia_tri"] == pytest.approx(0.20348, rel=1e-3)


def test_cau_to_sang_con():
    kq = doi_theo_quy_cach(11, "to", "cai", QC_THE, DVS)
    assert kq["gia_tri"] == pytest.approx(1_089)


def test_thieu_kho_thi_bao_thieu_chu_khong_doan():
    kq = doi_theo_quy_cach(241, "to", "m2", {"gsm": 300}, DVS)
    assert "gia_tri" not in kq
    assert set(kq["thieu"]) == {"kho_in_dai", "kho_in_rong"}
    assert "khổ tờ in" in kq["ly_do"]


def test_thieu_dinh_luong_thi_khong_ra_kg():
    kq = doi_theo_quy_cach(5_200, "to", "kg", {"kho_in_dai": 860, "kho_in_rong": 650}, DVS)
    assert kq["thieu"] == ["gsm"]


def test_khong_co_cau_thi_noi_thang():
    kq = doi_theo_quy_cach(10, "kg", "cai", QC_THE, DVS)
    assert kq["thieu"] == ["cau"]


def test_don_vi_chua_khai():
    kq = doi_theo_quy_cach(10, "to", "hop_carton_5_lop", QC_THE, DVS)
    assert kq["thieu"] == ["hop_carton_5_lop"]


def test_khong_co_cau_con_sang_cuon():
    """CỐ Ý không có cầu "con → cuốn ÷ số tay": bước lệnh đếm `cai` nghĩa là đếm THÀNH PHẨM
    (1.000 cuốn), chia thêm số tay là sai 5 lần. Cầu này mà mọc lại thì test đỏ."""
    from app.services.quy_doi_service import CAU

    assert ("thanh_pham", "thanh_pham") not in CAU
    assert all(nguon != "thanh_pham" for nguon, _ in CAU)


# --- tiền khoán ----------------------------------------------------------------


def test_tien_khoan_can_mang():
    """Số của xưởng: 241 tờ 65×86 cán mờ 150 đ/m² → 20.208 đ (đối chiếu tính tay 134,72 m²)."""
    kq = tien_khoan(241, "to", "m²", 150, QC_THE, DVS)
    assert kq["tien"] == pytest.approx(20_208, abs=1)
    assert "150 đ/m²" in kq["dien_giai"]


def test_tien_khoan_lam_tron_ve_dong():
    kq = tien_khoan(241, "to", "m²", 150, QC_THE, DVS)
    assert kq["tien"] == round(kq["tien"])       # lương không có xu


def test_tien_khoan_cat_giay_theo_tan():
    kq = tien_khoan(5_200, "to", "tấn", 150_000, QC_RUOT, DVS)
    assert kq["tien"] == pytest.approx(30_521, abs=2)


def test_tien_khoan_thieu_so_thi_khong_ra_tien():
    kq = tien_khoan(241, "to", "m²", 150, {}, DVS)
    assert "tien" not in kq and kq["thieu"]
