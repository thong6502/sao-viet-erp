"""Quy đổi đơn vị — hàm thuần, test không cần DB.

Trọng tâm: (1) đổi theo CẶP người dùng khai, kể cả đi vòng qua trung gian; (2) chưa khai cặp thì
nói thẳng chứ không đoán; (3) quy đổi ĐỘNG — hệ số là công thức, số ra tuỳ khổ + định lượng của
chính việc đang làm; (4) thiếu biến thì nói THIẾU GÌ — số đoán chảy thẳng vào tiền khoán.
"""
from __future__ import annotations

import pytest

from app.seed_rebuild import _DON_VI_SEED, _QUY_DOI_SEED
from app.services.quy_doi_service import (
    canh_quy_cach, cap_map, don_vi_dung_duoc, don_vi_map, doi, doi_theo_quy_cach,
    ngu_canh, tien_khoan,
)

DVS = don_vi_map([{"ma": m, "ten": t, "ho": h} for m, t, h, _gc in _DON_VI_SEED])

# Cặp ĐỘNG khai NGAY TẠI ĐÂY, không mượn seed nữa (14/08/2026). Bốn dòng này đã gỡ khỏi
# `_QUY_DOI_SEED` — quy đổi động chuyển sang ô "Công thức tính lượng" ở chính đơn vị / mặt hàng.
# Nhưng CƠ CHẾ cặp động vẫn còn trong code, và đây là bộ test của chính cơ chế đó, nên nó phải tự
# dựng dữ liệu mồi. Test đi mượn seed cho đúng thứ nó đang test là buộc hai thứ vào nhau: đổi seed
# một cái là test đỏ mà chẳng có lỗi nào thật.
CAP_DONG: list[tuple[str, str, float, str]] = [
    ("to", "m2", 0, "dai_in * rong_in"),
    ("to", "kg", 0, "dinh_luong * dai_in * rong_in"),
    ("to", "cai", 0, "so_tp"),
    ("to_nguyen", "kg", 0, "dinh_luong * dai_nguyen * rong_nguyen"),
]
# Cách gọi thành phẩm cũng khai TẠI ĐÂY, cùng lý do (14/08/2026 — đã gỡ khỏi `_QUY_DOI_SEED`).
# Xưởng nào gọi thành phẩm là "cuốn" thì tự khai cặp ở màn Đơn vị & quy đổi; test thì tự mồi.
CAP_THANH_PHAM: list[tuple[str, str, float, str]] = [
    ("con", "cai", 1, ""),
    ("cuon", "cai", 1, ""),
    ("bo", "cai", 1, ""),
    ("hop", "cai", 1, ""),
]
# Dòng cặp GIỮ NGUYÊN (không dẹp sẵn thành đồ thị): dòng động chỉ ra hệ số sau khi thay biến.
CAP_ROWS = [{"tu_ma": a, "den_ma": b, "he_so": h, "cong_thuc": ct}
            for a, b, h, ct in (*_QUY_DOI_SEED, *CAP_THANH_PHAM, *CAP_DONG)]
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
    # Hệ số động phải KHOE nó từ đâu ra, không thì là số trên trời rơi xuống. Nhãn biến lấy từ
    # từ điển chung `bien_cong_thuc`; từ 11/08/2026 là khổ CỤ THỂ chứ không còn biến vai trò.
    assert "Dài tờ in" in kq["dien_giai"] and "Rộng tờ in" in kq["dien_giai"]


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
    assert set(kq["thieu"]) == {"dai_in", "rong_in"}
    # Lý do phải gọi tên biến bằng CHỮ NGƯỜI ĐỌC, không phơi mã `dai_in`/`rong_in`.
    assert "Dài tờ in" in kq["ly_do"]


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
    # Mọi dòng ĐỘNG xuất phát từ một mức TỜ (tờ in hoặc tờ nguyên) — không có dòng nào đi từ
    # `cai`/`con` ngược lên, vì đó mới là chỗ đẻ ra phép chia số tay sai.
    dong = [(a, b) for a, b, _h, ct in _QUY_DOI_SEED if ct]
    assert all(nguon in ("to", "to_nguyen") for nguon, _ in dong), dong
    kq = doi_theo_quy_cach(1_000, "cai", "cuon", QC_THE, DVS, CAP_ROWS)
    assert kq["gia_tri"] == 1_000


def test_ngu_canh_nhan_ca_khoa_moi_lan_cu():
    """Lệnh vẫn truyền `kho_in_dai` (mm) như cũ; khoá CŨ `dai` (m) hiểu là khổ tờ IN.

    Giữ nhận khoá cũ để `ke_hoach_vat_tu` (đang bơm `{dai, rong, gsm}`) khỏi phải sửa cùng lúc —
    bỏ đột ngột là bảng so tồn giấy im lặng mất cạnh tờ→kg.
    """
    assert ngu_canh({"kho_in_dai": 860, "gsm": 300})["dai_in"] == pytest.approx(0.86)
    assert ngu_canh({"dai": 1.09})["dai_in"] == pytest.approx(1.09)
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


# --- đơn vị dùng được cho MỘT mặt hàng (nguồn dropdown ở Kho / NCC) --------------

# Giấy Couché 150 khổ 65×86 — quy cách lấy từ chính bản ghi giấy trong danh mục.
QC_GIAY = {"dai": 0.86, "rong": 0.65, "gsm": 150}


def _ma(ds) -> set[str]:
    return {d["ma"] for d in ds}


def test_don_vi_dung_duoc_giay_co_kho_thi_thay_to_va_ram():
    """Giấy khai đủ khổ + định lượng → cạnh động `tờ → kg` sống, kéo theo cả ram/m²/cm²."""
    ds = don_vi_dung_duoc("kg", DVS, CAP_ROWS, QC_GIAY)
    assert {"kg", "g", "tan", "to", "ram", "m2", "cm2"} <= _ma(ds)


def test_don_vi_dung_duoc_thieu_kho_thi_tat_canh_dong():
    """Hoá chất chỉ khai kg, không có khổ/định lượng → cạnh động tắt, KHÔNG được hiện tờ/ram.

    Đây là chỗ dễ sai nhất: hiện `tờ` cho can hoá chất thì thủ kho nhập "10 tờ" và tồn ra số vô
    nghĩa."""
    ds = don_vi_dung_duoc("kg", DVS, CAP_ROWS, None)
    assert {"kg", "g", "tan"} <= _ma(ds)
    assert "to" not in _ma(ds) and "ram" not in _ma(ds)


def test_don_vi_dung_duoc_he_so_hai_chieu_khop_nhau():
    """1 kg = 1.000 g và ngược lại 1 g = 0,001 kg — nơi gọi lấy đúng chiều mình cần."""
    g = next(d for d in don_vi_dung_duoc("kg", DVS, CAP_ROWS, QC_GIAY) if d["ma"] == "g")
    assert g["he_so"] == pytest.approx(1_000)
    assert g["he_so_ve_goc"] == pytest.approx(0.001)


def test_don_vi_dung_duoc_giay_10_ram_ra_dung_can():
    """Số thật của xưởng: giấy Couché 150 khổ 65×86 → 1 tờ = 0,0839 kg, 1 ram (500 tờ) = 41,93 kg.
    Đây chính là con số tồn kho sẽ cộng khi thủ kho nhập "10 ram"."""
    ram = next(d for d in don_vi_dung_duoc("kg", DVS, CAP_ROWS, QC_GIAY) if d["ma"] == "ram")
    assert 10 * ram["he_so_ve_goc"] == pytest.approx(419.25, abs=0.5)


def test_don_vi_dung_duoc_goc_dung_dau_va_khong_lap():
    ds = don_vi_dung_duoc("kg", DVS, CAP_ROWS, QC_GIAY)
    assert ds[0]["ma"] == "kg" and ds[0]["la_goc"] and ds[0]["he_so"] == 1.0
    assert len(_ma(ds)) == len(ds)              # loang BFS không được trả trùng đơn vị


def test_don_vi_dung_duoc_canh_quy_cach_rieng_cua_mon():
    """Vật tư khác: "1 thùng = 3 kg" là hệ số của RIÊNG món đó — nối vào cap_rows lúc chạy, không
    khai vào bảng cặp chung (thùng keo ≠ thùng mực)."""
    rows = CAP_ROWS + canh_quy_cach("thung", 3, "kg")
    ds = don_vi_dung_duoc("kg", DVS, rows, None)
    thung = next(d for d in ds if d["ma"] == "thung")
    assert thung["he_so_ve_goc"] == pytest.approx(3)
    # Không có cạnh riêng thì thùng KHÔNG tự xuất hiện.
    assert "thung" not in _ma(don_vi_dung_duoc("kg", DVS, CAP_ROWS, None))


def test_don_vi_dung_duoc_goc_chua_khai_thi_rong():
    """Mặt hàng chưa chọn đơn vị gốc → trả rỗng để UI chặn, KHÔNG đoán bừa một đơn vị."""
    assert don_vi_dung_duoc("", DVS, CAP_ROWS, QC_GIAY) == []
    assert don_vi_dung_duoc("khong_co_ma_nay", DVS, CAP_ROWS, QC_GIAY) == []
