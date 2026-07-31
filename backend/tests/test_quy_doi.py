"""Quy đổi đơn vị — hàm thuần, test không cần DB.

Trọng tâm: (1) đổi theo CẶP người dùng khai, kể cả đi vòng qua trung gian; (2) chưa khai cặp thì
nói thẳng chứ không đoán; (3) quy đổi ĐỘNG — hệ số là công thức, số ra tuỳ khổ + định lượng của
chính việc đang làm; (4) thiếu biến thì nói THIẾU GÌ — số đoán chảy thẳng vào tiền khoán.
"""
from __future__ import annotations

import pytest

from app.seed_rebuild import _DON_VI_SEED, _QUY_DOI_SEED
from app.services.quy_doi_service import (
    cap_map, don_vi_map, doi, doi_theo_quy_cach, ngu_canh, tien_khoan,
)

DVS = don_vi_map([{"ma": m, "ten": t, "ho": h} for m, t, h, _gc in _DON_VI_SEED])
# Dòng cặp GIỮ NGUYÊN (không dẹp sẵn thành đồ thị): dòng động chỉ ra hệ số sau khi thay biến.
CAP_ROWS = [{"tu_ma": a, "den_ma": b, "he_so": h, "cong_thuc": ct}
            for a, b, h, ct in _QUY_DOI_SEED]
CAP = cap_map(CAP_ROWS)          # chỉ cạnh HẰNG — dùng cho `doi()` thuần

# Quy cách THẬT của lệnh thẻ nhân viên (tờ in 860×650, Couché 300, 99 con/tờ).
QC_THE = {"kho_in_dai": 860, "kho_in_rong": 650, "gsm": 300, "so_con": 99}
QC_RUOT = {"kho_in_dai": 860, "kho_in_rong": 650, "gsm": 70, "so_con": 1}


# --- đổi theo cặp đã khai -----------------------------------------------------


@pytest.mark.parametrize("gia_tri,tu,den,mong_doi", [
    (1_347_190, "cm2", "m2", 134.719),
    (134.719, "m2", "cm2", 1_347_190),
    (0.2035, "tan", "kg", 203.5),
    (203.5, "kg", "tan", 0.2035),
    (10, "ram", "to", 5_000),
    (5_000, "to", "ram", 10),
])
def test_doi_theo_cap(gia_tri, tu, den, mong_doi):
    kq = doi(gia_tri, tu, den, DVS, CAP)
    assert kq["gia_tri"] == pytest.approx(mong_doi, rel=1e-4)
    assert kq["dien_giai"]          # luôn khoe cách tính để người đọc kiểm bằng mắt


def test_doi_tra_cuu_duoc_ca_ma_lan_ten():
    """Bảng đơn giá khoán lưu CHỮ HIỂN THỊ ("m²") còn bước lệnh dùng MÃ ("to") — tra cứu phải nhận
    cả hai, không thì đơn giá 150 đ/m² vĩnh viễn báo "chưa khai đơn vị"."""
    assert doi(1, "m²", "cm2", DVS, CAP)["gia_tri"] == pytest.approx(10_000)
    assert doi(1, "tấn", "kg", DVS, CAP)["gia_tri"] == pytest.approx(1_000)


def test_cung_don_vi_khong_sinh_phep_tinh():
    """Mã và tên của CÙNG một đơn vị ("to" ↔ "tờ") thì đừng in "÷ 1" cho người đọc."""
    kq = doi(5_200, "to", "tờ", DVS, CAP)
    assert kq["gia_tri"] == 5_200
    assert "÷" not in kq["dien_giai"] and "×" not in kq["dien_giai"]


def test_cap_he_so_1_chi_la_cach_goi_khac():
    """cái ↔ cuốn ↔ hộp: khai cặp hệ số 1 — 1.000 cái LÀ 1.000 cuốn."""
    kq = doi(1_000, "cai", "cuon", DVS, CAP)
    assert kq["gia_tri"] == 1_000
    assert "1.000 cái = 1.000 cuốn" in kq["dien_giai"]


# --- chưa khai cặp: nói thẳng, không đoán --------------------------------------


def test_chua_khai_cap_thi_khong_tu_doi():
    """Tờ và m² không có cặp nào nối (không ai khai được: 1 tờ bằng mấy m² tuỳ khổ) → `doi()` phải
    từ chối. Việc bắc cầu là của `doi_theo_quy_cach`, nơi có quy cách lệnh."""
    kq = doi(241, "to", "m2", DVS, CAP)
    assert "gia_tri" not in kq
    assert kq["thieu"] == ["cap"]


def test_di_vong_qua_trung_gian():
    """Chỉ khai tấn→kg và kg→g, hỏi tấn→g thì máy tự nhân dọc đường và NÓI RÕ đi qua đâu."""
    kq = doi(2, "tan", "g", DVS, CAP)
    assert kq["gia_tri"] == pytest.approx(2_000_000)
    assert "qua" in kq["dien_giai"]


def test_dong_to_sang_m2():
    kq = doi_theo_quy_cach(241, "to", "m2", QC_THE, DVS, CAP_ROWS)
    assert kq["gia_tri"] == pytest.approx(134.719, rel=1e-4)
    assert "241 tờ" in kq["dien_giai"] and "m²" in kq["dien_giai"]
    # Hệ số động phải KHOE nó từ đâu ra, không thì là số trên trời rơi xuống.
    assert "dài" in kq["dien_giai"] and "rộng" in kq["dien_giai"]


def test_dong_to_sang_kg_va_tan():
    """Cạnh động nhả ra kg rồi đi tiếp bằng CẶP kg↔tấn — khỏi khai riêng cho từng đơn vị."""
    kg = doi_theo_quy_cach(5_200, "to", "kg", QC_RUOT, DVS, CAP_ROWS)
    tan = doi_theo_quy_cach(5_200, "to", "tan", QC_RUOT, DVS, CAP_ROWS)
    assert kg["gia_tri"] == pytest.approx(203.48, rel=1e-3)
    assert tan["gia_tri"] == pytest.approx(0.20348, rel=1e-3)


def test_dong_doi_nguoc_duoc_khong_can_khai_them():
    """Chốt của mô hình: động hay tĩnh thì hệ số cuối vẫn là MỘT số nhân, nên chiều ngược là chia.
    203,48 kg giấy ruột 65×86 Ford 70 phải quay về đúng 5.200 tờ."""
    kq = doi_theo_quy_cach(203.48, "kg", "to", QC_RUOT, DVS, CAP_ROWS)
    assert kq["gia_tri"] == pytest.approx(5_200, rel=1e-3)


def test_dong_lay_kho_ma_NOI_GOI_dua(  # noqa: N802 — tên nói rõ chốt thiết kế
):
    """Chốt B (2026-07-31): nơi gọi quyết định khổ nào. Cùng 1.000 tờ, khai khổ nguyên 79×109 thì
    cân nặng khác hẳn khổ in 65×86 — danh mục KHÔNG được tự chọn hộ."""
    to_in = doi_theo_quy_cach(1_000, "to", "kg", QC_THE, DVS, CAP_ROWS)
    to_nguyen = doi_theo_quy_cach(
        1_000, "to", "kg", {"dai": 1.09, "rong": 0.79, "gsm": 300}, DVS, CAP_ROWS)
    assert to_in["gia_tri"] == pytest.approx(167.7, rel=1e-3)
    assert to_nguyen["gia_tri"] == pytest.approx(258.3, rel=1e-3)


def test_dong_to_sang_con():
    kq = doi_theo_quy_cach(11, "to", "cai", QC_THE, DVS, CAP_ROWS)
    assert kq["gia_tri"] == pytest.approx(1_089)


def test_thieu_kho_thi_bao_thieu_chu_khong_doan():
    kq = doi_theo_quy_cach(241, "to", "m2", {"gsm": 300}, DVS, CAP_ROWS)
    assert "gia_tri" not in kq
    assert set(kq["thieu"]) == {"dai", "rong"}
    assert "khổ tờ" in kq["ly_do"]


def test_thieu_dinh_luong_thi_khong_ra_kg():
    kq = doi_theo_quy_cach(5_200, "to", "kg", {"kho_in_dai": 860, "kho_in_rong": 650},
                           DVS, CAP_ROWS)
    assert kq["thieu"] == ["dinh_luong"]


def test_khong_co_duong_thi_noi_thang():
    """kg → bản kẽm: không cặp nào nối, cũng không công thức nào bắc qua → báo thiếu cặp."""
    kq = doi_theo_quy_cach(10, "kg", "kem", QC_THE, DVS, CAP_ROWS)
    assert "gia_tri" not in kq
    assert kq["thieu"] == ["cap"]


def test_don_vi_chua_khai():
    kq = doi_theo_quy_cach(10, "to", "hop_carton_5_lop", QC_THE, DVS, CAP_ROWS)
    assert kq["thieu"] == ["hop_carton_5_lop"]


def test_khong_co_duong_con_sang_cuon_chia_so_tay():
    """CỐ Ý không có quy đổi "con → cuốn ÷ số tay": bước lệnh đếm `cai` nghĩa là đếm THÀNH PHẨM
    (1.000 cuốn), chia thêm số tay là sai 5 lần. Mọi dòng ĐỘNG đều xuất phát từ TỜ."""
    dong = [(a, b) for a, b, _h, ct in _QUY_DOI_SEED if ct]
    assert all(nguon == "to" for nguon, _ in dong)
    kq = doi_theo_quy_cach(1_000, "cai", "cuon", QC_THE, DVS, CAP_ROWS)
    assert kq["gia_tri"] == 1_000


def test_ngu_canh_nhan_ca_khoa_moi_lan_cu():
    """Lệnh sản xuất vẫn truyền `kho_in_dai` (mm) như cũ; nơi gọi mới truyền thẳng `dai` (m)."""
    assert ngu_canh({"kho_in_dai": 860, "gsm": 300})["dai"] == pytest.approx(0.86)
    assert ngu_canh({"dai": 1.09})["dai"] == pytest.approx(1.09)
    assert ngu_canh({"gsm": 300})["dinh_luong"] == pytest.approx(0.3)


# --- tiền khoán ----------------------------------------------------------------


def test_tien_khoan_can_mang():
    """Số của xưởng: 241 tờ 65×86 cán mờ 150 đ/m² → 20.208 đ (đối chiếu tính tay 134,72 m²)."""
    kq = tien_khoan(241, "to", "m²", 150, QC_THE, DVS, CAP_ROWS)
    assert kq["tien"] == pytest.approx(20_208, abs=1)
    assert "150 đ/m²" in kq["dien_giai"]


def test_tien_khoan_lam_tron_ve_dong():
    kq = tien_khoan(241, "to", "m²", 150, QC_THE, DVS, CAP_ROWS)
    assert kq["tien"] == round(kq["tien"])       # lương không có xu


def test_tien_khoan_cat_giay_theo_tan():
    kq = tien_khoan(5_200, "to", "tấn", 150_000, QC_RUOT, DVS, CAP_ROWS)
    assert kq["tien"] == pytest.approx(30_521, abs=2)


def test_tien_khoan_thieu_so_thi_khong_ra_tien():
    kq = tien_khoan(241, "to", "m²", 150, {}, DVS, CAP_ROWS)
    assert "tien" not in kq and kq["thieu"]
