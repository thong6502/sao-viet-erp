"""Engine tính giá vốn THEO THÀNH PHẦN (redesign) — hàm THUẦN, không DB.

Khẳng định: bình bài con/tờ hình học (auto + override), xả giấy 2 mức tờ, 2 nhóm (nvl · cong_doan)
không hệ số.
"""
from __future__ import annotations

from math import ceil

from app.services.thanh_phan_engine import (
    binh_bai_con, binh_bai_layout, binh_bai_nghich, compute_phieu,
)


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


def test_binh_bai_nghich_dung_N_it_phe():
    # Name card 90×54, chừa 0, tờ nguyên 650×430, muốn ĐÚNG 49 con.
    # 49 = 7×7 → khổ tờ in 630×378 (lọt nguyên); phân rã khác (1×49 / 49×1) quá khổ.
    r = binh_bai_nghich(con=49, dai_tp=90, rong_tp=54, chua_mm=0,
                        kho_nguyen_dai=650, kho_nguyen_rong=430)
    assert r["con"] == 49
    assert r["kho_in_dai"] == 630 and r["kho_in_rong"] == 378
    assert r["rows"] == 7 and r["cols"] == 7
    # Round-trip: nạp khổ vừa tính vào bình bài XUÔI → đúng 49 con.
    assert binh_bai_con(kho_in_dai=630, kho_in_rong=378, dai_tp=90, rong_tp=54, chua_mm=0) == 49


def test_binh_bai_nghich_khong_xep_duoc_tra_0():
    # N=13 (nguyên tố) không xếp lọt tờ nguyên 650×430 với SP 90×54 → con=0 (FE báo đỏ).
    assert binh_bai_nghich(con=13, dai_tp=90, rong_tp=54, chua_mm=0,
                           kho_nguyen_dai=650, kho_nguyen_rong=430)["con"] == 0
    # Chưa nhập khổ giấy nguyên → KHÔNG tính (con=0).
    assert binh_bai_nghich(con=49, dai_tp=90, rong_tp=54, chua_mm=0,
                           kho_nguyen_dai=0, kho_nguyen_rong=0)["con"] == 0


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

    # Nguyên vật liệu (giấy) tính theo TỜ NGUYÊN: 52 × 5000
    nvl = _grp(res, "nvl")
    assert nvl["rows"][0]["so_to"] == ceil(to_net / 2)
    assert nvl["subtotal"] == ceil(to_net / 2) * 5000
    # Chỉ 2 nhóm — không còn A/B/C/D.
    assert [g["idx"] for g in res["groups"]] == ["nvl", "cong_doan"]
    # Công đoạn = Kẽm hai mặt (4+4)×100000 + Công in (tờ gross × 2 mặt)×100 (KHÔNG nhân số màu).
    kem = 8 * 100000
    cong_in = to_net * 2 * 100
    assert _grp(res, "cong_doan")["subtotal"] == kem + cong_in
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
    assert _grp(res, "nvl")["subtotal"] == 0


def test_formula_engine_ast_and_hao_so_to():
    tp = _component()
    tp["cong_thuc_gia"] = "dinh_luong * dai_nguyen * rong_nguyen * don_gia_kg * to_nguyen"
    tp["bu_hao_so_to"] = 250
    tp["hao_so_to"] = 150
    
    res = compute_phieu(so_luong=4000, thanh_phans=[tp])
    m = res["meta"]["components"][0]
    
    # 4000 / 49 = 82 con/to net
    # to_dau_vao = 82 + 0 (finishing spoilages) + 250 (bu_hao) = 332
    # to_sau_in = 332 - 150 = 182
    # to_nguyen = ceil(332 / 2) = 166
    assert m["to_dau_vao"] == 332
    assert m["to_sau_in"] == 182
    assert m["to_nguyen"] == 166

    # Verify formula calculation
    # dinh_luong = 0.3, dai_nguyen = 0.86, rong_nguyen = 0.65, don_gia_kg = 5000, to_nguyen = 166
    # 0.3 * 0.86 * 0.65 * 5000 * 166 = 139191.0
    assert _grp(res, "nvl")["subtotal"] == 139191.0

    # Check formula formatting
    row = _grp(res, "nvl")["rows"][0]
    assert "dinh_luong(0,30) × dai_nguyen(0,86) × rong_nguyen(0,65)" in row["cong_thuc"]


def test_giay_don_vi_tan_quy_ve_kg():
    """Giấy bán theo TẤN: đơn giá đ/tấn phải ÷1000 khi công thức dùng don_gia_kg (chống lệch 1000×).

    Neo theo phiếu hộp đôi: giấy D250, khổ nguyên 445×640, gsm 250, 17.100.000 đ/tấn,
    con=2, SL 4.000, bù 250 → to_nguyen 2.250 → tiền giấy = 0,25×0,445×0,64×17.100×2.250.
    """
    tp = {
        "ten": "Hộp D250", "so_to_per_sp": 1, "quy_cach_in": "mot_mat", "con_auto": False,
        "so_con": 2, "dai_thanh_pham": 300, "rong_thanh_pham": 200,
        "kho_dai": 640, "kho_rong": 445, "kho_in_dai": 640, "kho_in_rong": 445,
        "gsm": 250, "giay_ten": "Duplex D250",
        "don_gia_giay": 17_100_000, "don_gia_don_vi": "tan", "nguon_giay": "cong_ty",
        "bu_hao_so_to": 250, "co_in": False,
        "cong_thuc_gia": "dinh_luong * dai_nguyen * rong_nguyen * don_gia_kg * to_nguyen",
    }
    res = compute_phieu(so_luong=4000, thanh_phans=[tp])
    m = res["meta"]["components"][0]
    assert m["to_net"] == 2000
    assert m["to_dau_vao"] == 2250
    assert m["so_manh_xa"] == 1          # khổ in = khổ nguyên → không xả
    assert m["to_nguyen"] == 2250
    # 0.25 × 0.445 × 0.64 × 17100 × 2250 = 2.739.420 (don_gia_kg = 17.100.000 ÷ 1000)
    assert _grp(res, "nvl")["subtotal"] == 2739420.0
    # ≈ 685 đ/thành phẩm (đúng phiếu tay)
    assert round(2739420.0 / 4000) == 685


def test_in_kem_la_cong_doan_trong_chuoi():
    """In (nhom=print) & Kẽm (nhom=prepress) là CÔNG ĐOẠN trong chuỗi → tính bằng công thức;
    field cứng don_gia_cong_in/che_ban_don_gia BỊ BỎ QUA (fallback tắt). Cả 2 vào nhóm 'Công đoạn'."""
    tp = _component()   # field cứng: don_gia_cong_in=100, che_ban_don_gia=100000
    tp["thanh_phams"] = [
        {"ten": "In offset", "don_gia": 200,
         "cong_doan": {"nhom": "print", "cong_thuc_gia": "to_dau_vao * so_mat * don_gia"}},
        {"ten": "Chế bản kẽm", "don_gia": 90000,
         "cong_doan": {"nhom": "prepress", "cong_thuc_gia": "so_kem * don_gia"}},
    ]
    res = compute_phieu(so_luong=5000, thanh_phans=[tp])
    m = res["meta"]["components"][0]

    # Cả In offset & Chế bản kẽm nằm chung nhóm 'Công đoạn' (theo thứ tự routing).
    cd_rows = _grp(res, "cong_doan")["rows"]
    assert any("In offset" in r["ten"] for r in cd_rows)
    assert any("Chế bản kẽm" in r["ten"] for r in cd_rows)
    # In = to_dau_vao × 2 mặt × 200 (KHÔNG dùng field cứng 100); Kẽm = so_kem × 90000 (không dùng 100000).
    tien_in = m["to_dau_vao"] * 2 * 200   # hai_mat → 2 mặt
    tien_kem = m["so_kem"] * 90000        # 8 kẽm × 90.000 = 720.000
    assert _grp(res, "cong_doan")["subtotal"] == tien_in + tien_kem


def test_giay_kg_default_theo_can():
    """Giấy 'kg' KHÔNG khai công thức → mặc định tính theo CÂN (không phải × tờ)."""
    tp = _component()
    tp["don_gia_don_vi"] = "kg"
    tp["don_gia_giay"] = 5000      # đ/kg
    tp.pop("cong_thuc_gia", None)
    res = compute_phieu(so_luong=5000, thanh_phans=[tp])
    m = res["meta"]["components"][0]
    # 0.30 (gsm300) × dai_nguyen(0.86) × rong_nguyen(0.65) × 5000 × to_nguyen
    expected = 0.30 * 0.86 * 0.65 * 5000 * m["to_nguyen"]
    assert _grp(res, "nvl")["subtotal"] == round(expected, 2)


def test_cong_doan_default_theo_nhom_khong_can_khai_cong_thuc():
    """In (print) & Kẽm (prepress) KHÔNG khai cong_thuc_gia → engine tự dùng công thức mặc định theo nhom."""
    tp = _component()
    tp["thanh_phams"] = [
        {"ten": "In offset", "don_gia": 200, "cong_doan": {"nhom": "print"}},        # không cong_thuc_gia
        {"ten": "Ghi kẽm", "don_gia": 90000, "cong_doan": {"nhom": "prepress"}},      # không cong_thuc_gia
    ]
    res = compute_phieu(so_luong=5000, thanh_phans=[tp])
    m = res["meta"]["components"][0]
    # In (print → to_dau_vao × so_mat × don_gia) + Kẽm (prepress → so_kem × don_gia), gộp nhóm 'Công đoạn'.
    tien_in = m["to_dau_vao"] * 2 * 200
    tien_kem = m["so_kem"] * 90000
    assert _grp(res, "cong_doan")["subtotal"] == tien_in + tien_kem
