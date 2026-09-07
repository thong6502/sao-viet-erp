"""Phép SO ảnh chụp lệnh ↔ danh mục — phần THUẦN, không dựng lệnh không đụng DB.

Tách riêng khỏi `test_lsx_service` cố ý: mấy luật ở đây (rỗng-là-rỗng, dòng người khai không bị
đè, rổ BỎ chỉ báo) là luật NGHIỆP VỤ nhỏ mà dễ sửa hỏng lúc tối ưu, nên phải có chỗ chỉ đúng vào
chúng thay vì đọc ngược qua một lệnh 5 bước.
"""
from __future__ import annotations

from app.services.lsx_danh_muc_doi import khoan_lech, vat_tu_lech


# --- ảnh chụp khoán -----------------------------------------------------------
def test_khoan_khong_lech_thi_khong_bao_gi():
    kh = {"rate_id": 7, "ten": "Dán thường", "don_vi": "cái", "don_gia": 250}
    assert khoan_lech(kh, dict(kh)) == []


def test_rong_va_thieu_khoa_la_MOT_THU():
    """`khoan_snapshot` VẮNG hẳn khoá `cong_thuc` khi công thức rỗng, ảnh chụp cũ lại có khoá ấy
    mang chuỗi rỗng. Không quy về một dạng thì MỌI bước cũ đều báo lệch giả — băng mất uy tín ngay
    lần đầu bật lên."""
    assert khoan_lech({"cong_thuc": "", "ten": "A"}, {"ten": "A"}) == []
    assert khoan_lech({"cong_thuc": "   ", "ten": "A"}, {"cong_thuc": None, "ten": "A"}) == []


def test_lech_so_thuc_o_chu_so_cuoi_KHONG_tinh_la_doi():
    """Hai đường tính khác nhau lệch nhau ở chữ số cuối là chuyện thường; báo "600 → 600" thì
    người dùng thôi tin cái băng."""
    assert khoan_lech({"don_gia": 600.0}, {"don_gia": 600.0 + 1e-12}) == []
    assert [x["truong"] for x in khoan_lech({"don_gia": 600}, {"don_gia": 601})] == ["don_gia"]


def test_bao_dich_danh_o_nao_kem_nhan_doc_duoc():
    lech = khoan_lech({"don_gia": 250, "so_nguoi_tieu_chuan": 2},
                      {"don_gia": 400, "so_nguoi_tieu_chuan": 3})
    theo_truong = {x["truong"]: x for x in lech}
    assert theo_truong["don_gia"]["nhan"] == "Đơn giá khoán"
    assert (theo_truong["don_gia"]["cu"], theo_truong["don_gia"]["moi"]) == ("250", "400")
    assert theo_truong["so_nguoi_tieu_chuan"]["nhan"] == "Kíp chuẩn"


def test_cong_thuc_hien_ra_CHU_chu_khong_bay_ma_bien():
    """Người lập kế hoạch đọc băng này để QUYẾT, không phải để debug — bày `sl_vao * don_gia` ra
    thì họ không biết mình đang đồng ý với cái gì."""
    [x] = khoan_lech({"cong_thuc": "sl_vao * don_gia"}, {"cong_thuc": "sl_ra * don_gia"})
    assert "sl_vao" not in (x["cu"] or "") and "sl_ra" not in (x["moi"] or "")
    assert x["cu"] and x["moi"] and x["cu"] != x["moi"]


def test_o_bo_trong_tra_None_de_FE_ve_dau_gach():
    [x] = khoan_lech({"don_gia": 250}, {"don_gia": None})
    assert x["cu"] == "250" and x["moi"] is None


# --- dòng vật tư --------------------------------------------------------------
def _mon(vid, so_luong, *, tu_dong=True, ten="Mực Cyan"):
    return {"vat_tu_id": vid, "ma": f"VT-{vid}", "ten": ten, "don_vi": "kg",
            "so_luong": so_luong, "tu_dong": tu_dong}


def test_danh_muc_co_ma_buoc_chua_co_thi_vao_ro_THEM():
    vt = vat_tu_lech([], [_mon(3, 1.5)])
    assert [x["vat_tu_id"] for x in vt["them"]] == [3]
    assert vt["them"][0]["so_luong_cu"] is None and vt["them"][0]["so_luong_moi"] == 1.5
    assert vt["bo"] == [] and vt["lech"] == []


def test_cung_mon_khac_so_thi_vao_ro_LECH():
    vt = vat_tu_lech([_mon(3, 1.5)], [_mon(3, 2.0)])
    assert vt["lech"] == [{"vat_tu_id": 3, "ma": "VT-3", "ten": "Mực Cyan", "don_vi": "kg",
                           "so_luong_cu": 1.5, "so_luong_moi": 2.0}]


def test_dong_NGUOI_KHAI_dung_ngoai_ca_bo_lan_lech():
    """Người ta đã cố ý gõ đè số đó; lấy số danh mục ghi lên là xoá việc họ vừa làm."""
    tay = _mon(3, 9.9, tu_dong=False)
    assert vat_tu_lech([tay], [_mon(3, 2.0)])["lech"] == []
    assert vat_tu_lech([tay], [])["bo"] == []


def test_danh_muc_khong_con_bung_thi_CHI_BAO_khong_xoa():
    """Rổ BỎ là báo cáo. Dòng ấy vẫn giữ số cũ và vẫn tính vào nhu cầu vật tư — máy đoán sai thì
    mất một dòng vật tư thật, nên bỏ hay giữ là quyết định của người lập kế hoạch."""
    vt = vat_tu_lech([_mon(3, 1.5)], [])
    assert [x["vat_tu_id"] for x in vt["bo"]] == [3]
    assert vt["bo"][0]["so_luong_cu"] == 1.5 and vt["bo"][0]["so_luong_moi"] is None


def test_khop_het_thi_ba_ro_deu_rong():
    assert vat_tu_lech([_mon(3, 1.5)], [_mon(3, 1.5)]) == {"them": [], "bo": [], "lech": []}
