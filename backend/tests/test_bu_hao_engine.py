"""Bù hao engine — tra bậc số lượng của 1 mã bù hao + nối công đoạn qua `bu_hao_id`.

Mô hình MỚI: công đoạn trỏ THẲNG 1 mã bù hao (bu_hao_id) → engine tra bậc theo SL (không còn
trục số màu/số con). Số liệu lấy đúng bảng xưởng (In 3-4 màu / Sóng 1 con…).
"""
from app.services import bu_hao_engine as be


def _bac(vals, pct):
    _SL = [(0, 3000), (3000, 7000), (7000, 10000), (10000, 15000), (15000, 20000), (20000, 30000)]
    b = [{"sl_tu": t, "sl_den": d, "gia_tri": v, "don_vi": "to"} for (t, d), v in zip(_SL, vals)]
    b.append({"sl_tu": 30000, "sl_den": None, "gia_tri": pct, "don_vi": "pct"})
    return b


# Danh mục bù hao (id + mã + bậc). Công đoạn trỏ theo id.
ROWS = [
    {"id": 2, "ma": "BH-IN-1-2", "bac": _bac([120, 150, 200, 250, 300, 350], 1.5)},
    {"id": 3, "ma": "BH-IN-3-4", "bac": _bac([150, 200, 250, 300, 350, 400], 1.7)},
    {"id": 4, "ma": "BH-IN-5", "bac": _bac([200, 250, 300, 350, 400, 450], 2)},
    {"id": 6, "ma": "BH-SONG-1CON", "bac": _bac([70, 100, 150, 170, 200, 250], 1)},
]


def _bh(ma):
    return next(r["bac"] for r in ROWS if r["ma"] == ma)


def test_tra_bac_theo_sl():
    # In 5 màu, 12.000 → bậc 10.000-15.000 → 350 tờ
    assert be.tra_bac(_bh("BH-IN-5"), 12000) == 350
    # In 3-4 màu, 12.000 → bậc 10.000-15.000 → 300
    assert be.tra_bac(_bh("BH-IN-3-4"), 12000) == 300
    # In 3-4 màu, 5.000 → bậc 3.000-7.000 → 200
    assert be.tra_bac(_bh("BH-IN-3-4"), 5000) == 200
    # In 1-2 màu, 40.000 → bậc >30.000 = 1,5% × 40.000 = 600 tờ
    assert be.tra_bac(_bh("BH-IN-1-2"), 40000) == 600
    # Sóng 1 con, 8.000 → bậc 7.000-10.000 → 150
    assert be.tra_bac(_bh("BH-SONG-1CON"), 8000) == 150


def test_bien_bac_chan_tren_bao_gom():
    # SL đúng biên 3.000 → "trở xuống" (bậc đầu) → 150
    assert be.tra_bac(_bh("BH-IN-3-4"), 3000) == 150
    # 3.001 → bậc kế → 200
    assert be.tra_bac(_bh("BH-IN-3-4"), 3001) == 200


def test_khong_khop_tra_0():
    assert be.tra_bac(_bh("BH-SONG-1CON"), 0) == 0.0   # SL 0: không bậc
    assert be.tra_bac([], 5000) == 0.0                 # không bậc nào


def test_bu_hao_cong_doan_theo_kieu():
    ctx = dict(rows=ROWS, sl=12000)
    assert be.bu_hao_cong_doan({"kieu_bu_hao": "khong"}, **ctx) == 0.0
    assert be.bu_hao_cong_doan({"kieu_bu_hao": "co_dinh", "so_to_bu_hao": 50}, **ctx) == 50
    # tra_bang → trỏ mã BH-IN-3-4 (id 3), 12.000 → 300
    assert be.bu_hao_cong_doan({"kieu_bu_hao": "tra_bang", "bu_hao_id": 3}, **ctx) == 300
    # tra_bang nhưng bu_hao_id None hoặc không có trong danh mục → 0
    assert be.bu_hao_cong_doan({"kieu_bu_hao": "tra_bang", "bu_hao_id": None}, **ctx) == 0.0
    assert be.bu_hao_cong_doan({"kieu_bu_hao": "tra_bang", "bu_hao_id": 999}, **ctx) == 0.0


def test_tong_bu_hao_don():
    # Đơn 12.000: In (BH-IN-3-4 → 300) + Ép kim (cố định 50) + Bồi (cố định 50) = 400
    cds = [
        {"kieu_bu_hao": "tra_bang", "bu_hao_id": 3},
        {"kieu_bu_hao": "co_dinh", "so_to_bu_hao": 50},
        {"kieu_bu_hao": "co_dinh", "so_to_bu_hao": 50},
        {"kieu_bu_hao": "khong"},                         # ghi kẽm → 0
    ]
    assert be.tong_bu_hao(cds, rows=ROWS, sl=12000) == 400
    # + đơn yêu cầu 2% → +240 tờ
    assert be.tong_bu_hao(cds, rows=ROWS, sl=12000, pct_yeu_cau=2) == 400 + 240


# ============================ Bù hao NGƯỢC theo chuỗi công đoạn ============================

def test_hao_buoc_tach_to_va_pct():
    """Đi ngược cần tờ-cố-định và % TÁCH RIÊNG: tờ thì cộng, % thì chia."""
    assert be.hao_buoc({"kieu_bu_hao": "khong"}, rows=ROWS, sl=12000) == (0.0, 0.0)
    assert be.hao_buoc({"kieu_bu_hao": "co_dinh", "so_to_bu_hao": 50}, rows=ROWS, sl=12000) == (50, 0.0)
    # bậc đơn vị "to" → về vế TỜ
    assert be.hao_buoc({"kieu_bu_hao": "tra_bang", "bu_hao_id": 3}, rows=ROWS, sl=12000) == (300, 0.0)
    # bậc đơn vị "pct" (>30.000) → về vế %, KHÔNG quy sẵn ra tờ như `bu_hao_cong_doan`
    assert be.hao_buoc({"kieu_bu_hao": "tra_bang", "bu_hao_id": 3}, rows=ROWS, sl=40000) == (0.0, 1.7)
    assert be.hao_buoc({"kieu_bu_hao": "tra_bang", "bu_hao_id": 999}, rows=ROWS, sl=12000) == (0.0, 0.0)


def test_chuoi_nguoc_rong_thi_khong_hao():
    assert be.chuoi_nguoc([], rows=ROWS, to_can=500) == []


def test_chuoi_nguoc_buoc_dau_roi_bac_cao_hon():
    """Bằng chứng "ngược" đã chạy: bước IN ở ĐẦU chuỗi tra bậc theo số tờ nó thật sự chạy."""
    chain = [
        {"kieu_bu_hao": "tra_bang", "bu_hao_id": 3},      # In 3-4 màu
        {"kieu_bu_hao": "co_dinh", "so_to_bu_hao": 50},   # Bế
        {"kieu_bu_hao": "co_dinh", "so_to_bu_hao": 50},   # Xén
    ]
    b = be.chuoi_nguoc(chain, rows=ROWS, to_can=2950)
    # Xén 2.950→3.000 · Bế 3.000→3.050 · In tra bậc theo 3.050 → bậc 3.000-7.000 = 200 tờ
    assert [x["ra"] for x in b] == [3050, 3000, 2950]
    assert [x["vao"] for x in b] == [3250, 3050, 3000]
    # Cộng xuôi phẳng tra bậc In theo to_net=2.950 → bậc "3.000 trở xuống" = 150 → chỉ 3.200 tờ.
    assert be.tong_bu_hao(chain, rows=ROWS, sl=2950) + 2950 == 3200


def _b(ten, dv_vao, dv_ra, cd=None):
    return {"ten": ten, "cd": cd or {}, "dv_vao": dv_vao, "dv_ra": dv_ra}


def test_chuoi_nguoc_dv_tra_bac_theo_DUNG_don_vi_cua_buoc():
    """Ca chứng minh bug gốc: bước đếm CON phải tra bậc theo số CON, không theo số tờ.

    Đóng gói xử lý 5.000 con → bậc "3.000–7.000". Bản phẳng cũ truyền số TỜ (24) nên rơi bậc
    "3.000 trở xuống" — sai bậc, sai lượng, sai đơn vị.
    """
    chain = [
        _b("In offset", "to", "to", {"kieu_bu_hao": "tra_bang", "bu_hao_id": 3}),
        _b("Bế", "to", "cai", {"kieu_bu_hao": "co_dinh", "so_to_bu_hao": 50}),
        _b("Đóng gói", "cai", "cai", {"kieu_bu_hao": "tra_bang", "bu_hao_id": 3}),
    ]
    kq, canh_bao = be.chuoi_nguoc_dv(chain, rows=ROWS, to_can=5000, he_so={("to", "cai"): 210})
    assert canh_bao == []
    b_in, b_be, b_dg = kq
    # Đóng gói: 5.000 con → bậc 3.000-7.000 của BH-IN-3-4 = 200 (con) → vào 5.200 con
    assert b_dg["ra"] == 5000 and b_dg["vao"] == 5200
    # Bế: quy 5.200 con ÷ 210 con/tờ = 24,76 tờ, + 50 tờ canh khuôn
    assert round(b_be["vao"], 2) == round(5200 / 210 + 50, 2)
    assert b_be["dv_vao"] == "to" and b_be["dv_ra"] == "cai"
    # In: ra ~74,8 tờ → bậc "3.000 trở xuống" = 150 tờ
    assert round(b_in["vao"], 2) == round(5200 / 210 + 50 + 150, 2)


def test_chuoi_nguoc_dv_cau_to_nguyen_sang_to_in():
    """Bước xả giấy là ranh giới tờ NGUYÊN → tờ IN; hao của nó khai bằng tờ nguyên."""
    chain = [
        _b("Xả giấy", "to_nguyen", "to", {"kieu_bu_hao": "co_dinh", "so_to_bu_hao": 5}),
        _b("In offset", "to", "to", {"kieu_bu_hao": "co_dinh", "so_to_bu_hao": 150}),
    ]
    kq, canh_bao = be.chuoi_nguoc_dv(chain, rows=ROWS, to_can=100, he_so={("to_nguyen", "to"): 2})
    assert canh_bao == []
    assert kq[1]["vao"] == 250            # in: 100 tờ in ra + 150 canh máy
    assert kq[0]["vao"] == 130            # xả: 250 ÷ 2 mảnh = 125 tờ nguyên + 5 tờ hao xả


def test_chuoi_nguoc_dv_bao_dut_don_vi():
    """Bế nhả CON mà bước sau lại ăn TỜ → chuỗi đứt. Engine KHÔNG tự bắc cầu, chỉ nói ra."""
    chain = [_b("Bế", "to", "cai"), _b("Cán màng", "to", "to")]
    _kq, canh_bao = be.chuoi_nguoc_dv(chain, rows=ROWS, to_can=100, he_so={("to", "cai"): 210})
    assert len(canh_bao) == 1 and "đứt đơn vị" in canh_bao[0]


def test_chuoi_nguoc_dv_thieu_he_so_thi_keu_chu_khong_doan():
    chain = [_b("Bế", "to", "cai")]
    kq, canh_bao = be.chuoi_nguoc_dv(chain, rows=ROWS, to_can=5000, he_so={})
    assert len(canh_bao) == 1 and "hệ số" in canh_bao[0]
    assert kq[0]["vao"] == 5000            # tạm hệ số 1, KHÔNG đoán bừa một con số


def test_chuoi_nguoc_pct_la_phep_chia():
    """Bậc % đi ngược phải CHIA (`ra / (1−%)`), cộng `ra × %` là ra thiếu giấy."""
    b = be.chuoi_nguoc([{"kieu_bu_hao": "tra_bang", "bu_hao_id": 2}], rows=ROWS, to_can=40000)
    assert round(b[0]["vao"], 2) == round(40000 / 0.985, 2)   # 1,5% → chia
    assert b[0]["vao"] > 40000 + 600                          # > cách cộng xuôi (40.600)
