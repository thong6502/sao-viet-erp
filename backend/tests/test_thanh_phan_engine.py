"""Engine tính giá vốn THEO THÀNH PHẦN (redesign) — hàm THUẦN, không DB.

Khẳng định: bình bài con/tờ hình học (auto + override), xả giấy 2 mức tờ, 2 nhóm (nvl · cong_doan)
không hệ số.
"""
from __future__ import annotations

from math import ceil

from app.services.thanh_phan_engine import (
    binh_bai_con, binh_bai_layout, compute_phieu,
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


def test_chua_tach_chieu_khong_an_chieu_con_lai():
    """Nhíp là cạnh NẠP giấy — chỉ ăn chiều DÀI. Bản cũ trừ đều 2 chiều → hụt con."""
    # Tem 100×43 lên tờ in 1020×720. Cùng một số chừa 44mm, chỉ khác trừ 1 chiều hay 2 chiều.
    gop = binh_bai_con(kho_in_dai=1020, kho_in_rong=720, dai_tp=100, rong_tp=43, chua_mm=44)
    tach = binh_bai_con(kho_in_dai=1020, kho_in_rong=720, dai_tp=100, rong_tp=43,
                        chua_dai_mm=44, chua_rong_mm=0)
    assert (gop, tach) == (135, 154)       # chiều rộng không còn bị trừ oan → +19 con
    # Nhíp GIẤY thật (~10mm) thay vì nhíp KẼM (44mm) — gộp cả 2 lỗi thì hụt 135 vs 161.
    assert binh_bai_con(kho_in_dai=1020, kho_in_rong=720, dai_tp=100, rong_tp=43,
                        chua_dai_mm=10, chua_rong_mm=0) == 161
    # Lề hông ăn chiều RỘNG, không đụng chiều dài.
    assert binh_bai_con(kho_in_dai=1020, kho_in_rong=720, dai_tp=100, rong_tp=43,
                        chua_dai_mm=0, chua_rong_mm=40) == 150


def test_bleed_phinh_con_moi_chieu():
    """bleed cộng 2 CẠNH mỗi chiều: con 100×43 + bleed 3 → 106×49."""
    khong = binh_bai_con(kho_in_dai=1020, kho_in_rong=720, dai_tp=100, rong_tp=43)
    co = binh_bai_con(kho_in_dai=1020, kho_in_rong=720, dai_tp=100, rong_tp=43, bleed_mm=3)
    assert khong == 161                    # xoay: floor(1020/43) × floor(720/100) = 23 × 7
    assert co == 9 * 14                    # thẳng: floor(1020/106) × floor(720/49)
    lay = binh_bai_layout(kho_in_dai=1020, kho_in_rong=720, dai_tp=100, rong_tp=43, bleed_mm=3)
    assert lay["piece_dai"] == 106 and lay["piece_rong"] == 49


def test_khe_cat_n_con_chi_co_n_tru_1_khe():
    """3 con chỉ có 2 khe. Khổ vừa khít 3 con + 2 khe → đúng 3; hụt 1mm → chỉ còn 2."""
    # 3×100 + 2×5 = 310
    assert binh_bai_con(kho_in_dai=310, kho_in_rong=43, dai_tp=100, rong_tp=43, khe_cat_mm=5) == 3
    assert binh_bai_con(kho_in_dai=309, kho_in_rong=43, dai_tp=100, rong_tp=43, khe_cat_mm=5) == 2
    # Không khe thì 3 con chỉ cần 300.
    assert binh_bai_con(kho_in_dai=300, kho_in_rong=43, dai_tp=100, rong_tp=43) == 3


def test_tham_so_moi_mac_dinh_giu_nguyen_hanh_vi_cu():
    """bleed=0, khe=0, KHÔNG truyền chua_dai/rong → y hệt bản cũ (tương thích ngược)."""
    for d, r, dt, rt, ch in ((650, 430, 90, 54, 0), (1090, 800, 210, 140, 60),
                             (1020, 720, 100, 43, 44), (100, 100, 200, 50, 0)):
        lay = binh_bai_layout(kho_in_dai=d, kho_in_rong=r, dai_tp=dt, rong_tp=rt, chua_mm=ch)
        assert lay["usable_dai"] == max(d - ch, 0) and lay["usable_rong"] == max(r - ch, 0)
        assert lay["piece_dai"] == dt and lay["piece_rong"] == rt


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
    # Chuỗi công đoạn RỖNG → KHÔNG có tiền in / kẽm. Engine không tự đẻ dòng thay thế nữa
    # (bỏ fallback `don_gia_cong_in` / `che_ban_don_gia`), chỉ NHẮC để người dùng tự thêm.
    assert _grp(res, "cong_doan")["rows"] == []
    assert _grp(res, "cong_doan")["subtotal"] == 0
    w = " ".join(res["warnings"])
    assert "chưa có công đoạn IN" in w and "CHẾ BẢN/KẼM" in w
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


def test_che_ban_khong_nam_trong_dong_giay():
    """Chế bản để TRỐNG đơn vị (nhả kẽm, không nhả tờ) → tự rơi khỏi chuỗi bù hao theo tờ."""
    tp = _component()
    tp["thanh_phams"] = [
        {"ten": "Ghi kẽm CTP", "cong_doan": {"ten": "Ghi kẽm CTP", "nhom": "prepress",
                                             "kieu_bu_hao": "co_dinh", "so_to_bu_hao": 999,
                                             "don_vi_vao": None, "don_vi_ra": None}},
        {"ten": "In offset", "cong_doan": {"ten": "In offset", "nhom": "print",
                                           "kieu_bu_hao": "co_dinh", "so_to_bu_hao": 150,
                                           "don_vi_vao": "to", "don_vi_ra": "to"}},
        {"ten": "Cán màng", "cong_doan": {"ten": "Cán màng", "nhom": "finishing",
                                          "kieu_bu_hao": "co_dinh", "so_to_bu_hao": 50,
                                          "don_vi_vao": "to", "don_vi_ra": "to"}},
    ]
    res = compute_phieu(so_luong=5000, thanh_phans=[tp])
    m = res["meta"]["components"][0]
    # Chế bản để trống là CỐ Ý → không kêu. (Bước khác quên khai thì có cảnh báo riêng.)
    assert not [w for w in res.get("warnings", []) if "chưa khai đơn vị" in w]
    # 5000/49 = 103 tờ net. Ngược: Cán 103→153 · In 153→303. 999 tờ của CHẾ BẢN không được cộng.
    assert m["bu_hao_auto"] == 200
    assert m["to_dau_vao"] == 303
    # Chế bản KHÔNG có mặt trong phân rã (nó không chạm tờ nào).
    assert [b["ten"] for b in m["bu_hao_chi_tiet"]] == ["In offset", "Cán màng"]
    # Tờ sau in = `ra` của bước in → cán màng chỉ tính tiền trên 153 tờ, không phải 303.
    assert m["to_sau_in"] == 153


def test_routing_qua_ranh_gioi_be_thi_chuoi_bat_dau_tu_SL_KHACH_DAT():
    """Routing có bế → chuỗi đi ngược từ 5.000 CON, quy về tờ tại đúng bước bế."""
    tp = _component()
    tp["thanh_phams"] = [
        {"ten": "In offset", "cong_doan": {"ten": "In offset", "nhom": "print",
                                           "kieu_bu_hao": "co_dinh", "so_to_bu_hao": 150,
                                           "don_vi_vao": "to", "don_vi_ra": "to"}},
        {"ten": "Bế", "cong_doan": {"ten": "Bế", "nhom": "finishing",
                                    "kieu_bu_hao": "co_dinh", "so_to_bu_hao": 50,
                                    "don_vi_vao": "to", "don_vi_ra": "cai"}},
        {"ten": "Đóng gói", "cong_doan": {"ten": "Đóng gói", "nhom": "finishing",
                                          "don_vi_vao": "cai", "don_vi_ra": "cai"}},
    ]
    res = compute_phieu(so_luong=5000, thanh_phans=[tp])
    m = res["meta"]["components"][0]
    # con=49, xả=2. Ngược: Đóng gói 5.000 con → Bế 5.000÷49=102,04 +50 = 152,04 tờ →
    # In 152,04 + 150 = 302,04 → ceil 303 tờ vào máy.
    assert m["to_dau_vao"] == 303
    assert m["bu_hao_auto"] == 303 - m["to_net"]        # to_net = ceil(5000/49) = 103
    assert m["to_nguyen"] == 152                        # ceil(303 / 2 mảnh xả)
    assert m["to_sau_in"] == 153                        # `ra` của bước in = ceil(152,04)
    # Chuỗi nhắm ĐÚNG số khách đặt nên không dư — khác ca không có bế (bình bài thừa ra vài con).
    assert m["so_tp_ra"] == 5000
    # Phân rã mang theo đơn vị để UI chỉ ra chỗ đổi.
    be_row = next(b for b in m["bu_hao_chi_tiet"] if b["ten"] == "Bế")
    assert (be_row["dv_vao"], be_row["dv_ra"]) == ("to", "cai")
    assert be_row["hao"] == 50                          # hao đo bằng ĐƠN VỊ VÀO (tờ), không phải con
    assert not [w for w in res.get("warnings", []) if "đứt đơn vị" in w]


def _sach_tp() -> dict:
    """Ruột sách 160 trang, tay 32 → 5 tay/cuốn. Trang A5 trên tờ in 650×430."""
    tp = _component()
    tp.update({"ten": "Ruột sách", "so_trang": 160, "trang_moi_tay": 32,
               "dai_thanh_pham": 210, "rong_thanh_pham": 148})
    return tp


def _buoc(ten: str, dv_vao, dv_ra, *, nhom="finishing", hao=0) -> dict:
    return {"ten": ten, "cong_doan": {
        "ten": ten, "nhom": nhom, "kieu_bu_hao": "co_dinh" if hao else "khong",
        "so_to_bu_hao": hao, "don_vi_vao": dv_vao, "don_vi_ra": dv_ra}}


def test_duong_tay_sach_ra_dung_bang_duong_tat_to_cai():
    """Sách khai `tờ in → tay → cuốn` phải ra ĐÚNG số giấy như khai tắt `tờ in → cuốn`.

    Cầu `to→tay` là 1 (gấp không sinh không mất tờ) nên cầu `tay→cai` phải gánh trọn `1/so_tay`.
    Sai chỗ này thì chuỗi ngược chạy 1:1 qua bước gấp và mỗi cuốn chỉ đòi 1 tờ thay vì 5.
    """
    tat = _sach_tp()
    tat["thanh_phams"] = [
        _buoc("In offset", "to", "to", nhom="print", hao=150),
        _buoc("Bắt tay + vào keo", "to", "cai"),
        _buoc("Xén 3 mặt", "cai", "cai"),
    ]
    dai = _sach_tp()
    dai["thanh_phams"] = [
        _buoc("In offset", "to", "to", nhom="print", hao=150),
        _buoc("Gấp tay sách", "to", "tay"),
        _buoc("Bắt tay + vào keo", "tay", "cai"),
        _buoc("Xén 3 mặt", "cai", "cai"),
    ]
    m_tat = compute_phieu(so_luong=2000, thanh_phans=[tat])["meta"]["components"][0]
    res_dai = compute_phieu(so_luong=2000, thanh_phans=[dai])
    m_dai = res_dai["meta"]["components"][0]

    # 2.000 cuốn × 5 tay = 10.000 tờ net, + 150 tờ canh máy.
    assert m_tat["to_net"] == 10_000
    assert (m_dai["to_net"], m_dai["to_dau_vao"]) == (m_tat["to_net"], m_tat["to_dau_vao"])
    assert m_dai["to_dau_vao"] == 10_150
    # Đi qua `tay` không được đẻ cảnh báo "thiếu cầu quy đổi".
    assert not [w for w in res_dai.get("warnings", []) if "quy đổi" in w or "đứt" in w]
    # Bước gấp nhận 10.000 tờ và nhả 10.000 tay — hệ số 1, không phải 1/5.
    gap = next(b for b in m_dai["bu_hao_chi_tiet"] if b["ten"] == "Gấp tay sách")
    assert (gap["dv_vao"], gap["dv_ra"], gap["he_so"]) == ("to", "tay", 1.0)


def test_hao_o_buoc_tay_sang_cuon_doi_du_so_tay():
    """Hỏng 100 CUỐN ở bước vào keo phải đòi bù 100 × 5 tay, không phải 100 tay."""
    tp = _sach_tp()
    tp["thanh_phams"] = [
        _buoc("In offset", "to", "to", nhom="print"),
        _buoc("Gấp tay sách", "to", "tay"),
        _buoc("Bắt tay + vào keo", "tay", "cai", hao=100),
    ]
    m = compute_phieu(so_luong=2000, thanh_phans=[tp])["meta"]["components"][0]
    # Ngược: 2.000 cuốn ÷ (1/5) = 10.000 tay, + 100 tay hao = 10.100 tay → 10.100 tờ.
    assert m["to_dau_vao"] == 10_100
    keo = next(b for b in m["bu_hao_chi_tiet"] if b["ten"] == "Bắt tay + vào keo")
    assert (keo["dv_vao"], keo["dv_ra"]) == ("tay", "cai")
    assert keo["hao"] == 100                 # hao đo bằng ĐƠN VỊ VÀO (tay)
    assert keo["ra_quy"] == 10_000           # 2.000 cuốn quy về tay


def test_formula_engine_ast_and_bu_them():
    tp = _component()
    tp["cong_thuc_gia"] = "dinh_luong * dai_nguyen * rong_nguyen * don_gia_kg * to_nguyen"
    tp["bu_hao_so_to"] = 250
    tp["hao_so_to"] = 150   # ô "− Hao" ĐÃ BỎ — engine phải lờ đi, không trừ vào to_sau_in

    res = compute_phieu(so_luong=4000, thanh_phans=[tp])
    m = res["meta"]["components"][0]

    # 4000 / 49 = 82 to net
    # to_dau_vao = 82 + 0 (chuỗi công đoạn rỗng → bù hao 0) + 250 (bù thêm tay) = 332
    # to_sau_in = 332: chuỗi KHÔNG có bước in → fallback = tờ vào máy (không trừ hao tay nữa)
    # to_nguyen = ceil(332 / 2) = 166
    assert m["to_dau_vao"] == 332
    assert m["to_sau_in"] == 332
    assert m["hao_tay"] == 0
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


def _fin_row(**kw) -> dict:
    """1 dòng công đoạn gia công có công thức phẳng: tiền = so_luong × don_gia."""
    return {"ten": "Bế", "don_gia": 300, "cong_doan": {
        "ten": "Bế", "nhom": "finishing", "cong_thuc_gia": "so_luong * don_gia"}, **kw}


def _tp_co_cong_doan(**kw) -> dict:
    tp = _component()
    tp["thanh_phams"] = [_fin_row(**kw.pop("row", {}))]
    tp.update(kw)
    return tp


def test_mau_pha_cong_them_ban_kem():
    """Mỗi màu mực = 1 bản kẽm, màu pha cũng vậy: 4 màu CMYK + 1 Pantone = 5 kẽm."""
    khong = compute_phieu(so_luong=2000, thanh_phans=[_tp_co_cong_doan()])
    co = compute_phieu(so_luong=2000, thanh_phans=[_tp_co_cong_doan(so_mau_pha=1)])
    k0 = khong["meta"]["components"][0]["so_kem"]
    k1 = co["meta"]["components"][0]["so_kem"]
    assert k1 == k0 + 1                      # ĐÚNG 1 bản kẽm cho 1 màu pha
    # In 1 mặt 4 màu process + 1 Pantone → 5 kẽm.
    tp = _component()
    tp.update({"quy_cach_in": "mot_mat", "so_mau_a": 4, "so_mau_b": 0, "so_mau_pha": 1,
               "so_to_per_sp": 1})
    assert compute_phieu(so_luong=1000, thanh_phans=[tp])["meta"]["components"][0]["so_kem"] == 5
    # Túi in 2 màu Pantone, không dùng CMYK → 2 kẽm.
    tp2 = _component()
    tp2.update({"quy_cach_in": "mot_mat", "so_mau_a": 0, "so_mau_b": 0, "so_mau_pha": 2,
                "so_to_per_sp": 1})
    assert compute_phieu(so_luong=1000, thanh_phans=[tp2])["meta"]["components"][0]["so_kem"] == 2


def test_mau_pha_nhan_theo_so_tay():
    """Ruột sách 128 trang, tay 16 → 8 tay; 4 màu + 1 pha mỗi tay → (4+1) × 8 = 40 kẽm.

    Số tay là DẪN XUẤT `so_trang / trang_moi_tay` — gửi thẳng `so_to_per_sp` không còn tác dụng."""
    tp = _component()
    tp.update({"quy_cach_in": "mot_mat", "so_mau_a": 4, "so_mau_b": 0, "so_mau_pha": 1,
               "so_trang": 128, "trang_moi_tay": 16})
    out = compute_phieu(so_luong=1000, thanh_phans=[tp])["meta"]["components"][0]
    assert out["so_to_per_sp"] == 8
    assert out["so_kem"] == 40


def test_duong_con_to_roi_ra_dung_bang_duong_tat_to_cai():
    """Tờ rời khai `tờ in → con → thành phẩm` phải ra ĐÚNG số giấy như khai tắt `tờ in → cái`.

    Cắt xong con nào là thẻ ấy, không gom, nên `con → thành phẩm` = 1 và cầu `tờ in → con` gánh
    trọn số con. Khác biệt thật giữa hai đường KHÔNG nằm ở số giấy mà ở đơn vị tra bậc bù hao:
    đường dài thì bước đóng gói tra theo 5.000 CON, đường tắt thì bước bế tra theo 102 TỜ.
    """
    tat = _component()
    tat["thanh_phams"] = [
        _buoc("In offset", "to", "to", nhom="print", hao=150),
        _buoc("Bế", "to", "cai", hao=50),
        _buoc("Đóng gói", "cai", "cai"),
    ]
    dai = _component()
    dai["thanh_phams"] = [
        _buoc("In offset", "to", "to", nhom="print", hao=150),
        _buoc("Bế", "to", "con", hao=50),
        _buoc("Đóng gói", "con", "cai"),
    ]
    res_dai = compute_phieu(so_luong=5000, thanh_phans=[dai])
    m_tat = compute_phieu(so_luong=5000, thanh_phans=[tat])["meta"]["components"][0]
    m_dai = res_dai["meta"]["components"][0]

    assert m_tat["con"] == 49
    assert (m_dai["to_dau_vao"], m_dai["to_nguyen"]) == (m_tat["to_dau_vao"], m_tat["to_nguyen"])
    assert m_dai["to_dau_vao"] == 303
    # Đi qua `con` KHÔNG được đẻ cảnh báo "chưa biết hệ số quy đổi — tạm tính 1" nữa.
    assert not [w for w in res_dai.get("warnings", []) if "hệ số quy đổi" in w]
    be = next(b for b in m_dai["bu_hao_chi_tiet"] if b["ten"] == "Bế")
    goi = next(b for b in m_dai["bu_hao_chi_tiet"] if b["ten"] == "Đóng gói")
    assert (be["dv_vao"], be["dv_ra"], be["he_so"]) == ("to", "con", 49.0)
    assert (goi["dv_vao"], goi["dv_ra"], goi["he_so"]) == ("con", "cai", 1.0)
    assert goi["ra_quy"] == 5000                 # bước đóng gói đếm CON, không đếm tờ


def test_duong_con_cua_sach_van_khoa_bang_cau_tat():
    """Bất biến tích-hai-cầu giữ cả với sách, nơi `tờ in → cái` NHỎ hơn 1 (gom tay).

    Sách không khai `con` trong thực tế, nhưng cầu vẫn phải nhất quán — viết dạng chia là để
    không có tổ hợp nào rơi ra ngoài.
    """
    tp = _sach_tp()
    tp["thanh_phams"] = [
        _buoc("In offset", "to", "to", nhom="print"),
        _buoc("Bế", "to", "con"),
        _buoc("Đóng gói", "con", "cai"),
    ]
    tat = _sach_tp()
    tat["thanh_phams"] = [
        _buoc("In offset", "to", "to", nhom="print"),
        _buoc("Bắt tay + vào keo", "to", "cai"),
    ]
    m = compute_phieu(so_luong=2000, thanh_phans=[tp])["meta"]["components"][0]
    m_tat = compute_phieu(so_luong=2000, thanh_phans=[tat])["meta"]["components"][0]
    assert m["to_dau_vao"] == m_tat["to_dau_vao"] == 10_000


# --- Mực in: TẬP mã, không phải con số ----------------------------------------------------------


def _kem(qc: str, a: list[str], b: list[str], **kw) -> int:
    tp = _component()
    tp.update({"quy_cach_in": qc, "muc_a": a, "muc_b": b, **kw})
    return compute_phieu(so_luong=1000, thanh_phans=[tp])["meta"]["components"][0]["so_kem"]


def test_kem_ab_cong_hai_mat_tu_tro_hop_hai_mat():
    """AB dùng hai bộ bản riêng (`|A|+|B|`); tự trở/trở nhíp chung một bộ (`|A ∪ B|`)."""
    cmyk = ["C", "M", "Y", "K"]
    assert _kem("hai_mat", cmyk, ["K"]) == 5          # 4 + 1, hai bộ bản
    assert _kem("tu_tro", cmyk, ["K"]) == 4           # {C,M,Y,K} — mặt B là tập con
    assert _kem("tro_nhip", cmyk, ["K"]) == 4         # nhíp khác trục lật, KHÔNG khác số bản
    assert _kem("mot_mat", cmyk, ["K"]) == 4          # mặt B không tồn tại


def test_kem_tu_tro_khong_phai_max_khi_hai_mat_muc_khac_nhau():
    """`max(|A|,|B|)` chỉ đúng khi tập bên ít màu nằm gọn trong bên kia — hai ca dưới thì không.

    Đây là lý do phải lưu TẬP MÃ: hai con số `4` và `1` không cho biết cái `1` đó là K (đã có
    trong CMYK) hay một Pantone riêng, mà hai đáp án lệch nhau đúng một bản kẽm.
    """
    cmyk = ["C", "M", "Y", "K"]
    # 4/1 nhưng mặt sau là Pantone riêng → hợp ra 5, max ra 4.
    assert _kem("tu_tro", cmyk, ["185C"]) == 5
    # 2/2 nhưng bốn mực khác nhau hoàn toàn → hợp ra 4, max ra 2.
    assert _kem("tu_tro", ["K", "185C"], ["300C", "123C"]) == 4
    # Cùng một Pantone hai mặt: tự trở gộp còn 1 bản, AB vẫn phải 2 (hai bộ bản riêng).
    assert _kem("tu_tro", ["185C"], ["185C"]) == 1
    assert _kem("hai_mat", ["185C"], ["185C"]) == 2


def test_muc_chuan_hoa_va_nhan_theo_so_tay():
    """Mã mực chuẩn hoá (viết hoa, gộp khoảng trắng, bỏ trùng); kẽm nhân theo SỐ TAY."""
    # " 185c " và "185C" là MỘT mực — không có danh mục nên chuẩn hoá chuỗi là hàng rào duy nhất.
    assert _kem("tu_tro", ["C", "M", "Y", "K"], [" 185c "]) == 5
    assert _kem("tu_tro", ["185C"], ["185 C"]) == 2      # khoảng trắng GIỮA là mã khác, không gộp
    assert _kem("hai_mat", ["K", "K", "k"], []) == 1     # trùng trong cùng một mặt → bỏ
    # Ruột sách 128 trang tay 16 → 8 tay, AB 4/1 → 5 bản mỗi tay → 40 kẽm.
    assert _kem("hai_mat", ["C", "M", "Y", "K"], ["K"], so_trang=128, trang_moi_tay=16) == 40


def test_ba_so_mau_van_la_dan_xuat_dung_nghia_cu():
    """`so_mau_a/b` = mực PROCESS mỗi mặt; `so_mau_pha` = mực pha PHÂN BIỆT của cả hai mặt."""
    tp = _component()
    tp.update({"quy_cach_in": "hai_mat", "muc_a": ["C", "M", "Y", "K", "185C"],
               "muc_b": ["K", "185C", "300C"]})
    m = compute_phieu(so_luong=1000, thanh_phans=[tp])["meta"]["components"][0]
    assert (m["so_mau_a"], m["so_mau_b"]) == (4, 1)   # chỉ đếm CMYK
    assert m["so_mau_pha"] == 2                       # 185C dùng hai mặt vẫn là MỘT màu phải pha


def test_thanh_phan_chi_co_so_mau_ra_y_het_so_cu():
    """Dữ liệu chỉ-có-số (seed/script/phiếu chưa backfill) không được đổi giá.

    Luật dựng tập từ số (`tap_muc_tu_so`, migration 0154 dùng chung) cố ý cho tập bên ít màu là
    CON của bên nhiều màu ⇒ `|A ∪ B| = max` = đúng số kẽm engine cũ tính.
    """
    for qc, ky_vong in (("hai_mat", 4 + 2 + 1), ("tu_tro", 4 + 1), ("mot_mat", 4 + 1)):
        tp = _component()
        tp.update({"quy_cach_in": qc, "so_mau_a": 4, "so_mau_b": 2, "so_mau_pha": 1,
                   "so_to_per_sp": 1})
        m = compute_phieu(so_luong=1000, thanh_phans=[tp])["meta"]["components"][0]
        assert m["so_kem"] == ky_vong, qc
        # Ba số dẫn xuất quay về đúng giá trị đưa vào → tiền mực không nhúc nhích.
        assert (m["so_mau_a"], m["so_mau_b"], m["so_mau_pha"]) == (4, 2, 1), qc


def test_khai_qua_4_mau_process_tach_thanh_pha_nhung_giu_TONG():
    """Khai `so_mau_a = 5` là dữ liệu không có thật — mực process chỉ có bốn (CMYK).

    DB dev đang có 2 hàng như vậy. Luật dựng tập đọc phần dư thành mực chưa rõ tên: `(5,0,0)` →
    4 process + 1 pha. Tách lại thế này ĐÚNG HƠN bản khai, và quan trọng là **giữ nguyên TỔNG**
    `so_mau_a + so_mau_b + so_mau_pha` — thứ mà công thức tiền mực dùng — nên giá không đổi.
    """
    tp = _component()
    tp.update({"quy_cach_in": "mot_mat", "so_mau_a": 5, "so_mau_b": 0, "so_mau_pha": 0,
               "so_to_per_sp": 1})
    m = compute_phieu(so_luong=1000, thanh_phans=[tp])["meta"]["components"][0]
    assert m["so_kem"] == 5                                      # y hệt công thức cũ
    assert (m["so_mau_a"], m["so_mau_b"], m["so_mau_pha"]) == (4, 0, 1)
    assert m["so_mau_a"] + m["so_mau_b"] + m["so_mau_pha"] == 5   # TỔNG giữ nguyên


# --- Chừa tách theo chiều: MỘT bản duy nhất ------------------------------------------------------


def test_chua_tach_chieu_nhip_khong_an_chieu_rong():
    """Thẻ nhân viên thật: nhíp 10 + đuôi 5 → DÀI 15; lề hông 5 hai bên → RỘNG 10.

    Nhíp là mép máy kẹp ở CẠNH NẠP, không liên quan chiều rộng. Cộng gộp các khoản thành một số
    rồi trừ đều hai chiều (20/20) là cách màn lệnh sản xuất từng làm."""
    from app.services.thanh_phan_engine import chua_theo_chieu

    # NGUỒN = danh mục MÁY. `gripper_mm` là nhíp KẼM, KHÔNG được dùng.
    assert chua_theo_chieu(
        {"nhip_giay_mm": 10, "duoi_thang_mau_mm": 5, "le_hong_mm": 5, "gripper_mm": 44}
    ) == (15, 10)
    assert chua_theo_chieu(
        {"nhip_giay_mm": 8, "duoi_thang_mau_mm": 4, "le_hong_mm": 3}
    ) == (12, 6)
    # `chua_nhip` trên phiếu ĐÈ nhíp của máy — khoản duy nhất còn đè được (mig 0139).
    assert chua_theo_chieu(
        {"chua_nhip": 12, "nhip_giay_mm": 8, "duoi_thang_mau_mm": 4, "le_hong_mm": 3}
    ) == (16, 6)
    # Không chọn máy + không đè → 0 cả hai chiều (bình sát mép, số con thổi phồng — cảnh báo ở UI).
    assert chua_theo_chieu({}) == (0, 0)


def test_binh_bai_the_nhan_vien_ra_99_con():
    """Số THẬT của xưởng: thẻ 54×86 trên tờ in 860×650, bleed 2 → 11×9 = 99 con/tờ.

    Canh nguyên cụm lỗi cũ của sơ đồ ở màn lệnh: bỏ bleed + trừ chừa đều hai chiều thì ra 105 con
    (7×15 xoay 90°) — cùng một tờ mà hai màn vẽ hai hình khác nhau."""
    from app.services.thanh_phan_engine import binh_bai_layout, chua_theo_chieu

    chua_d, chua_r = chua_theo_chieu(
        {"nhip_giay_mm": 10, "duoi_thang_mau_mm": 5, "le_hong_mm": 5}
    )
    lay = binh_bai_layout(kho_in_dai=860, kho_in_rong=650, dai_tp=86, rong_tp=54,
                          chua_dai_mm=chua_d, chua_rong_mm=chua_r, bleed_mm=2)
    assert (lay["con"], lay["cols"], lay["rows"], lay["rotated"]) == (99, 11, 9, False)
    # Bỏ bleed + gộp chừa = đúng cách sai cũ → 105. Giữ lại để thấy vì sao hai màn từng lệch.
    sai = binh_bai_layout(kho_in_dai=860, kho_in_rong=650, dai_tp=86, rong_tp=54,
                          chua_mm=20, bleed_mm=0)
    assert sai["con"] == 105
