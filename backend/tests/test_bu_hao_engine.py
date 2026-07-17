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
