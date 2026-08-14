"""Quy đổi đơn vị — hàm thuần, test không cần DB.

Trọng tâm: (1) đổi theo CẶP người dùng khai, kể cả đi vòng qua trung gian; (2) chưa khai cặp thì
nói thẳng chứ không đoán.

🔴 QUY ĐỔI ĐỘNG ĐÃ GỠ 14/08/2026 (mg `0198`). Cặp CHỈ còn hệ số cố định, nên mọi phép đổi ở đây là
HẰNG — không còn phụ thuộc khổ/định lượng của lệnh nào. Mười ca kiểm cạnh động (`to → kg` theo định
lượng · báo thiếu biến · dropdown Kho nở ra theo quy cách giấy) bị gỡ CÙNG cơ chế chứ không sửa cho
xanh: giữ lại là test một tính năng không tồn tại. Bốn ca ở cuối file thay chỗ chúng, khoá lại đúng
cái ĐANG đúng — không có quy cách thì kết quả vẫn thế, và câu hỏi tờ↔kg nay bị từ chối ở đây.

Câu hỏi "1 tờ nặng mấy kg" trả lời ở chỗ khác và bằng cách khác: CÁCH ĐO khai ở chính đơn vị
(`don_vi_do.cong_thuc`) / chính mặt hàng (`giay_nguyen.cong_thuc_luong`), trả thẳng LƯỢNG của cả
lệnh chứ không phải tỉ lệ giữa hai đơn vị. Test đường đó ở `test_ke_hoach_vat_tu.py` và
`test_lsx_service.py`.
"""
from __future__ import annotations

import pytest

from app.seed_rebuild import _DON_VI_SEED, _QUY_DOI_SEED
from app.services.quy_doi_service import (
    canh_quy_cach, cap_map, don_vi_dung_duoc, don_vi_map, doi, doi_theo_quy_cach,
    ngu_canh, tien_khoan,
)

DVS = don_vi_map([{"ma": m, "ten": t, "ho": h} for m, t, h, _gc in _DON_VI_SEED])

# Cách gọi thành phẩm khai NGAY TẠI ĐÂY, không mượn seed (14/08/2026 — đã gỡ khỏi `_QUY_DOI_SEED`).
# Xưởng nào gọi thành phẩm là "cuốn" thì tự khai cặp ở màn Đơn vị & quy đổi; test thì tự mồi. Test
# đi mượn seed cho đúng thứ nó đang test là buộc hai thứ vào nhau: đổi seed một cái là test đỏ mà
# chẳng có lỗi nào thật.
CAP_THANH_PHAM: list[tuple[str, str, float]] = [
    ("con", "cai", 1),
    ("cuon", "cai", 1),
    ("bo", "cai", 1),
    ("hop", "cai", 1),
]
# Dòng cặp GIỮ NGUYÊN hình dạng nơi gọi thật truyền vào (chưa dẹp thành đồ thị).
CAP_ROWS = [{"tu_ma": a, "den_ma": b, "he_so": h}
            for a, b, h in (*_QUY_DOI_SEED, *CAP_THANH_PHAM)]
CAP = cap_map(CAP_ROWS)

# Quy cách THẬT của lệnh thẻ nhân viên (tờ in 860×650, Couché 300, 99 con/tờ). Giữ lại để chứng
# minh chốt mới: truyền hay không truyền quy cách thì đáp án KHÔNG đổi.
QC_THE = {"kho_in_dai": 860, "kho_in_rong": 650, "gsm": 300, "so_con": 99}


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


def test_di_vong_qua_trung_gian():
    """Chỉ khai tấn→kg và kg→g, hỏi tấn→g thì máy tự nhân dọc đường và NÓI RÕ đi qua đâu."""
    kq = doi(2, "tan", "g", DVS, CAP)
    assert kq["gia_tri"] == pytest.approx(2_000_000)
    assert "qua" in kq["dien_giai"]


# --- chưa khai cặp: nói thẳng, không đoán --------------------------------------


def test_chua_khai_cap_thi_khong_tu_doi():
    """Tờ và m² không có cặp nào nối → `doi()` từ chối, không bịa hệ số."""
    kq = doi(241, "to", "m2", DVS, CAP)
    assert "gia_tri" not in kq
    assert kq["thieu"] == ["cap"]


def test_khong_co_duong_thi_noi_thang():
    """kg → bản kẽm: không cặp nào nối → báo thiếu cặp, kèm câu chỉ chỗ đi khai."""
    kq = doi_theo_quy_cach(10, "kg", "kem", QC_THE, DVS, CAP_ROWS)
    assert "gia_tri" not in kq
    assert kq["thieu"] == ["cap"]
    assert "Đơn vị & quy đổi" in kq["ly_do"]


def test_don_vi_chua_khai():
    kq = doi_theo_quy_cach(10, "to", "hop_carton_5_lop", QC_THE, DVS, CAP_ROWS)
    assert kq["thieu"] == ["hop_carton_5_lop"]


def test_khong_co_duong_con_sang_cuon_chia_so_tay():
    """CỐ Ý không có quy đổi "con → cuốn ÷ số tay": bước lệnh đếm `cai` nghĩa là đếm THÀNH PHẨM
    (1.000 cuốn), chia thêm số tay là sai 5 lần."""
    kq = doi_theo_quy_cach(1_000, "cai", "cuon", QC_THE, DVS, CAP_ROWS)
    assert kq["gia_tri"] == 1_000


def test_ngu_canh_nhan_ca_khoa_moi_lan_cu():
    """Lệnh vẫn truyền `kho_in_dai` (mm) như cũ; khoá CŨ `dai` (m) hiểu là khổ tờ IN.

    `ngu_canh` KHÔNG còn phục vụ quy đổi (cặp hết công thức) nhưng vẫn là cửa bơm biến cho công
    thức LƯỢNG / TIỀN — hai lối đọc cùng một bộ chip, nên luật nhận khoá cũ phải giữ nguyên.
    """
    assert ngu_canh({"kho_in_dai": 860, "gsm": 300})["dai_in"] == pytest.approx(0.86)
    assert ngu_canh({"dai": 1.09})["dai_in"] == pytest.approx(1.09)
    assert ngu_canh({"gsm": 300})["dinh_luong"] == pytest.approx(0.3)


# --- chốt sau khi gỡ quy đổi động ----------------------------------------------


def test_quy_cach_khong_con_doi_duoc_ket_qua():
    """Chốt 14/08/2026: `doi_theo_quy_cach` nhận `quy_cach` nhưng KHÔNG ăn nó nữa.

    Cùng câu hỏi, ba quy cách khác hẳn nhau (tờ in 65×86 · tờ nguyên 79×109 · không có gì) phải ra
    ĐÚNG một đáp án. Trước đây ba ca này ra ba số khác nhau — đó chính là thứ làm BOM không biết
    chọn đường nào.
    """
    ket = [doi_theo_quy_cach(5_000, "to", "ram", qc, DVS, CAP_ROWS)["gia_tri"]
           for qc in (QC_THE, {"dai": 1.09, "rong": 0.79, "gsm": 300}, None)]
    assert ket == [10, 10, 10]


def test_to_sang_kg_nay_bi_tu_choi():
    """Cân của tờ giấy KHÔNG còn là việc của bảng cặp — hỏi thẳng thì phải bị từ chối, chứ không
    lặng lẽ trả một hệ số nào đó. Câu trả lời nằm ở `giay_nguyen.cong_thuc_luong` (mg 0195/0197)."""
    for den in ("kg", "tan", "m2"):
        kq = doi_theo_quy_cach(5_200, "to", den, QC_THE, DVS, CAP_ROWS)
        assert "gia_tri" not in kq and kq["thieu"] == ["cap"], den


def test_cap_khong_con_nhan_cong_thuc():
    """Dòng cặp có `he_so <= 0` (hình dạng của dòng động cũ) bị LOẠI khỏi đồ thị — có sót lại trong
    DB thì nó cũng không đẻ ra cạnh nào. Migration `0198` xoá chúng, đây là lưới thứ hai."""
    rows = CAP_ROWS + [{"tu_ma": "to", "den_ma": "kg", "he_so": 0,
                        "cong_thuc": "dinh_luong * dai_in * rong_in"}]
    assert "to" not in cap_map(rows).get("kg", {})


# --- tiền khoán ----------------------------------------------------------------


def test_tien_khoan_theo_cap_da_khai():
    """Bước đếm `ram`, đơn giá theo `tờ`: 10 ram × 500 = 5.000 tờ × 30 đ = 150.000 đ."""
    kq = tien_khoan(10, "ram", "tờ", 30, QC_THE, DVS, CAP_ROWS)
    assert kq["tien"] == pytest.approx(150_000)
    assert "30 đ/tờ" in kq["dien_giai"]
    assert kq["tien"] == round(kq["tien"])       # lương không có xu


def test_tien_khoan_chua_khai_cap_thi_khong_ra_tien():
    """Đơn giá đ/m² mà bước đếm tờ: từ 14/08/2026 KHÔNG còn cạnh động bắc qua ⇒ không ra tiền.

    Đây là cái mất đã lường trước khi gỡ: 3 đầu việc khoán đ/m² (cán màng bóng/mờ, ghép metalize)
    im tiền cho tới khi xưởng khai công thức lượng cho `m²`. Thà không ra tiền còn hơn ra một số
    tính bằng đường mà không ai chọn.
    """
    kq = tien_khoan(241, "to", "m²", 150, QC_THE, DVS, CAP_ROWS)
    assert "tien" not in kq and kq["thieu"] == ["cap"]


# --- đơn vị dùng được cho MỘT mặt hàng (nguồn dropdown ở Kho / NCC) --------------


def _ma(ds) -> set[str]:
    return {d["ma"] for d in ds}


def test_don_vi_dung_duoc_chi_con_cum_hang():
    """Gốc kg → chỉ những đơn vị nối bằng hệ số CỐ ĐỊNH (kg · g · tấn).

    Trước 14/08/2026 danh sách này nở thêm `tờ`/`ram`/`m²` khi mặt hàng có khổ + định lượng, nhờ
    cạnh động. Gỡ cạnh động là mất phần nở đó — ghi thẳng vào test để người sau thấy đây là CHỦ Ý,
    không phải hồi quy. Đổi lại: cùng một mặt hàng thì thủ kho và người mua thấy đúng một danh sách,
    không tuỳ lúc đó lệnh có khai khổ hay không.
    """
    ds = don_vi_dung_duoc("kg", DVS, CAP_ROWS, {"dai": 0.86, "rong": 0.65, "gsm": 150})
    assert {"kg", "g", "tan"} <= _ma(ds)
    assert "to" not in _ma(ds) and "ram" not in _ma(ds)


def test_don_vi_dung_duoc_bo_qua_quy_cach():
    """Cùng lý do trên: có hay không có quy cách thì danh sách y hệt nhau."""
    co = _ma(don_vi_dung_duoc("kg", DVS, CAP_ROWS, {"dai": 0.86, "rong": 0.65, "gsm": 150}))
    khong = _ma(don_vi_dung_duoc("kg", DVS, CAP_ROWS, None))
    assert co == khong


def test_don_vi_dung_duoc_he_so_hai_chieu_khop_nhau():
    """1 kg = 1.000 g và ngược lại 1 g = 0,001 kg — nơi gọi lấy đúng chiều mình cần."""
    g = next(d for d in don_vi_dung_duoc("kg", DVS, CAP_ROWS) if d["ma"] == "g")
    assert g["he_so"] == pytest.approx(1_000)
    assert g["he_so_ve_goc"] == pytest.approx(0.001)


def test_don_vi_dung_duoc_goc_dung_dau_va_khong_lap():
    ds = don_vi_dung_duoc("kg", DVS, CAP_ROWS)
    assert ds[0]["ma"] == "kg" and ds[0]["la_goc"] and ds[0]["he_so"] == 1.0
    assert len(_ma(ds)) == len(ds)              # loang BFS không được trả trùng đơn vị


def test_don_vi_dung_duoc_canh_quy_cach_rieng_cua_mon():
    """Vật tư khác: "1 thùng = 3 kg" là hệ số của RIÊNG món đó — nối vào cap_rows lúc chạy, không
    khai vào bảng cặp chung (thùng keo ≠ thùng mực).

    Đây là đường CÒN LẠI để một mặt hàng có đơn vị riêng sau khi gỡ cạnh động, và nó khoẻ hơn:
    hệ số do người khai cho đúng món đó, không suy từ khổ giấy của lệnh nào.
    """
    rows = CAP_ROWS + canh_quy_cach("thung", 3, "kg")
    ds = don_vi_dung_duoc("kg", DVS, rows)
    thung = next(d for d in ds if d["ma"] == "thung")
    assert thung["he_so_ve_goc"] == pytest.approx(3)
    # Không có cạnh riêng thì thùng KHÔNG tự xuất hiện.
    assert "thung" not in _ma(don_vi_dung_duoc("kg", DVS, CAP_ROWS))


def test_don_vi_dung_duoc_goc_chua_khai_thi_rong():
    """Mặt hàng chưa chọn đơn vị gốc → trả rỗng để UI chặn, KHÔNG đoán bừa một đơn vị."""
    assert don_vi_dung_duoc("", DVS, CAP_ROWS) == []
    assert don_vi_dung_duoc("khong_co_ma_nay", DVS, CAP_ROWS) == []
