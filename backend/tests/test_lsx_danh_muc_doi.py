"""Phép SO ảnh chụp lệnh ↔ danh mục — phần THUẦN, không dựng lệnh không đụng DB.

Tách riêng khỏi `test_lsx_service` cố ý: mấy luật ở đây (rỗng-là-rỗng, dòng người khai không bị
đè, rổ BỎ chỉ báo) là luật NGHIỆP VỤ nhỏ mà dễ sửa hỏng lúc tối ưu, nên phải có chỗ chỉ đúng vào
chúng thay vì đọc ngược qua một lệnh 5 bước.
"""
from __future__ import annotations

from app.services.lsx_danh_muc_doi import o_lech, vat_tu_lech

# Bộ ô băng "Danh mục đã đổi" của MẺ (§7.2b) — nửa khoán của bước lệnh (`khoan_lech`) gỡ 18/09/2026,
# ba luật so thuần dưới đây giờ đứng sau băng mẻ.
_O_ME = (("ten", "Tên việc"), ("don_vi", "Đơn vị"), ("don_gia", "Đơn giá"))


# --- phép so ô ---------------------------------------------------------------
def test_khong_lech_thi_khong_bao_gi():
    kh = {"ten": "Dán thường", "don_vi": "cái", "don_gia": 1000}
    assert o_lech(kh, dict(kh), _O_ME) == []


def test_chi_so_dung_bo_o_noi_goi_truyen_vao():
    """Ô ngoài bộ so (ghi chú, mã…) đổi thế nào cũng không lên băng."""
    assert o_lech({"ten": "A", "ghi_chu": "x"}, {"ten": "A", "ghi_chu": "y"}, _O_ME) == []


def test_rong_va_thieu_khoa_la_MOT_THU():
    """Ảnh chụp cũ mang chuỗi rỗng, bản mới VẮNG hẳn khoá — không quy về một dạng thì mọi bản ghi
    cũ đều báo lệch giả, băng mất uy tín ngay lần đầu bật lên."""
    assert o_lech({"don_vi": "", "ten": "A"}, {"ten": "A"}, _O_ME) == []
    assert o_lech({"don_vi": "   ", "ten": "A"}, {"don_vi": None, "ten": "A"}, _O_ME) == []


def test_lech_so_thuc_o_chu_so_cuoi_KHONG_tinh_la_doi():
    """Hai đường tính khác nhau lệch nhau ở chữ số cuối là chuyện thường; báo "600 → 600" thì
    người dùng thôi tin cái băng."""
    assert o_lech({"don_gia": 600.0}, {"don_gia": 600.0 + 1e-12}, _O_ME) == []
    assert [x["truong"] for x in o_lech({"don_gia": 600}, {"don_gia": 601}, _O_ME)] == ["don_gia"]


def test_bao_dich_danh_o_nao_kem_nhan_doc_duoc():
    lech = o_lech({"don_gia": 250.0, "ten": "Bế"}, {"don_gia": 400, "ten": "Bế hộp"}, _O_ME)
    theo_truong = {x["truong"]: x for x in lech}
    assert theo_truong["don_gia"]["nhan"] == "Đơn giá"
    # 250.0 bày thành 250 — con số người vừa gõ, không phải thứ máy sinh.
    assert (theo_truong["don_gia"]["cu"], theo_truong["don_gia"]["moi"]) == ("250", "400")
    assert (theo_truong["ten"]["cu"], theo_truong["ten"]["moi"]) == ("Bế", "Bế hộp")


def test_o_bo_trong_tra_None_de_FE_ve_dau_gach():
    [x] = o_lech({"don_vi": "tờ"}, {"don_vi": None}, _O_ME)
    assert x["cu"] == "tờ" and x["moi"] is None


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
    # `hang_loai` đi kèm từ 08/09/2026: bước ăn cả giấy lẫn vật tư nên món được nhận dạng bằng
    # cặp (hang_loai, id); dòng cũ không mang khoá này thì hiểu là vật tư.
    assert vt["lech"] == [{"hang_loai": "vat_tu", "vat_tu_id": 3, "ma": "VT-3", "ten": "Mực Cyan",
                           "don_vi": "kg", "so_luong_cu": 1.5, "so_luong_moi": 2.0}]


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
