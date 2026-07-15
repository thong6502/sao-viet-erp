"""Engine tính giá vốn THEO THÀNH PHẦN (redesign) — hàm THUẦN, không DB.

Khẳng định: bình bài con/tờ hình học (auto + override), xả giấy 2 mức tờ, 4 nhóm không hệ số.
"""
from __future__ import annotations

from math import ceil

from app.services.thanh_phan_engine import binh_bai_con, binh_bai_layout, compute_phieu


def test_binh_bai_con_geometric():
    # Name card 90×54 mm lên tờ in 650×430 mm, không chừa → chọn hướng tốt hơn.
    con = binh_bai_con(kho_in_dai=650, kho_in_rong=430, dai_tp=90, rong_tp=54, chua_mm=0)
    # straight = floor(650/90)*floor(430/54) = 7*7 = 49 ; rotated = 12*4 = 48 → 49
    assert con == 49


def test_binh_bai_layout_chi_tiet():
    # 210×140 lên tờ in 1090×800, chừa 60mm → usable 1030×740, xoay 90° = 3×7 = 21.
    lay = binh_bai_layout(kho_in_dai=1090, kho_in_rong=800, dai_tp=210, rong_tp=140, chua_mm=60)
    assert lay["con"] == 21
    assert lay["rotated"] is True
    assert lay["cols"] == 3 and lay["rows"] == 7
    assert lay["usable_dai"] == 1030 and lay["usable_rong"] == 740
    # Quá khổ → layout rỗng, không vỡ.
    empty = binh_bai_layout(kho_in_dai=100, kho_in_rong=100, dai_tp=200, rong_tp=50)
    assert empty["con"] == 0 and empty["cols"] == 0


def test_binh_bai_con_qua_kho_tra_0():
    assert binh_bai_con(kho_in_dai=100, kho_in_rong=100, dai_tp=200, rong_tp=50) == 0


def _component() -> dict:
    """Thành phần đã RESOLVE (như service bơm): giấy nguyên 650×860, tờ in 430×650."""
    return {
        "ten": "Card", "so_to_per_sp": 1, "quy_cach_in": "hai_mat", "con_auto": True,
        "dai_thanh_pham": 90, "rong_thanh_pham": 54,
        "kho_in_dai": 650, "kho_in_rong": 430,
        "kho_dai": 860, "kho_rong": 650, "gsm": 300, "giay_ten": "Couche 300",
        "don_gia_giay": 5000, "don_gia_don_vi": "to", "nguon_giay": "cong_ty",
        "bu_hao_so_to": 0,
        "che_ban_don_gia": 100000, "don_gia_cong_in": 100,
        "so_mau_a": 4, "so_mau_b": 4, "co_in": True,
    }


def _grp(res, idx):
    return next(g for g in res["groups"] if g["idx"] == idx)


def test_compute_phieu_auto_binhbai_xa_giay():
    res = compute_phieu(so_luong=5000, thanh_phans=[_component()])
    m = res["meta"]["components"][0]

    # Bình bài auto = 49 con/tờ; xả giấy: tờ in 650×430 lên nguyên 860×650 = 2 mảnh.
    assert m["con"] == 49
    assert m["so_manh_xa"] == 2
    to_net = ceil(5000 / 49)          # 103
    assert m["to_net"] == to_net
    assert m["to_gross"] == to_net     # bù hao 0
    assert m["to_nguyen"] == ceil(to_net / 2)   # 52 (2 mức tờ)

    # A Giấy tính theo TỜ NGUYÊN: 52 × 5000
    assert _grp(res, "A")["rows"][0]["so_to"] == ceil(to_net / 2)
    assert _grp(res, "A")["subtotal"] == ceil(to_net / 2) * 5000
    # C Kẽm hai mặt: (4+4) × 100000
    assert _grp(res, "C")["subtotal"] == 8 * 100000
    # B Công in: (tờ gross × 2 mặt) × 100 — KHÔNG nhân số màu
    assert _grp(res, "B")["subtotal"] == to_net * 2 * 100
    # Tổng = Σ nhóm
    assert res["grand_total"] == round(sum(g["subtotal"] for g in res["groups"]), 2)


def test_con_override_khi_con_auto_false():
    tp = _component()
    tp["con_auto"] = False
    tp["so_con"] = 10          # override — bỏ qua bình bài hình học
    res = compute_phieu(so_luong=5000, thanh_phans=[tp])
    assert res["meta"]["components"][0]["con"] == 10


def test_moi_san_pham_co_sl_rieng():
    # 1 phiếu = nhiều SẢN PHẨM, mỗi sản phẩm SL riêng → giá vốn + đơn giá riêng, phiếu = Σ.
    a = _component(); a["so_luong"] = 1000
    b = _component(); b["so_luong"] = 3000
    res = compute_phieu(so_luong=0, thanh_phans=[a, b])   # SL mặc định phiếu = 0 → dùng SL từng SP
    comps = res["meta"]["components"]
    assert comps[0]["so_luong"] == 1000 and comps[1]["so_luong"] == 3000
    assert res["meta"]["tong_so_luong"] == 4000
    assert res["meta"]["so_thanh_phan"] == 2
    # SP nhiều SL hơn (cùng cấu hình) → giá vốn cao hơn.
    assert comps[1]["gia_von_tp"] > comps[0]["gia_von_tp"]
    # Đơn giá riêng mỗi sản phẩm = giá vốn / SL của nó.
    assert comps[0]["gia_von_don"] == round(comps[0]["gia_von_tp"] / 1000, 2)
    # Tổng phiếu = Σ giá vốn sản phẩm.
    assert res["grand_total"] == round(comps[0]["gia_von_tp"] + comps[1]["gia_von_tp"], 2)


def test_san_pham_khong_nhap_sl_thi_lay_mac_dinh_phieu():
    tp = _component()   # không có so_luong
    res = compute_phieu(so_luong=2000, thanh_phans=[tp])
    assert res["meta"]["components"][0]["so_luong"] == 2000   # rơi về SL mặc định phiếu


def test_khach_cap_giay_thi_giay_0():
    tp = _component()
    tp["nguon_giay"] = "khach"
    res = compute_phieu(so_luong=1000, thanh_phans=[tp])
    assert _grp(res, "A")["subtotal"] == 0
