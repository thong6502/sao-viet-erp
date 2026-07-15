"""Bù hao engine — tra 2 bước (số màu/số con × bậc SL) + nối theo kiểu công đoạn.

Số liệu lấy đúng bảng xưởng: In 1-2/3-4/5/6 màu (trục số màu) + Sóng 1 con/nhiều con (trục số con).
"""
from app.services import bu_hao_engine as be


def _bac(vals, pct):
    _SL = [(0, 3000), (3000, 7000), (7000, 10000), (10000, 15000), (15000, 20000), (20000, 30000)]
    b = [{"sl_tu": t, "sl_den": d, "gia_tri": v, "don_vi": "to"} for (t, d), v in zip(_SL, vals)]
    b.append({"sl_tu": 30000, "sl_den": None, "gia_tri": pct, "don_vi": "pct"})
    return b


ROWS = [
    {"truc": "so_mau", "key_tu": 1, "key_den": 2, "bac": _bac([120, 150, 200, 250, 300, 350], 1.5)},
    {"truc": "so_mau", "key_tu": 3, "key_den": 4, "bac": _bac([150, 200, 250, 300, 350, 400], 1.7)},
    {"truc": "so_mau", "key_tu": 5, "key_den": 5, "bac": _bac([200, 250, 300, 350, 400, 450], 2)},
    {"truc": "so_mau", "key_tu": 6, "key_den": 6, "bac": _bac([250, 300, 350, 450, 500, 600], 2.5)},
    {"truc": "so_con", "key_tu": 1, "key_den": 1, "bac": _bac([70, 100, 150, 170, 200, 250], 1)},
    {"truc": "so_con", "key_tu": 2, "key_den": 999, "bac": _bac([50, 70, 120, 150, 170, 200], 0.7)},
]


def test_tra_bang_2_buoc():
    # 5 màu, 12.000 → dòng "In 5 màu" (5-5), bậc 10.000-15.000 → 350 tờ
    assert be.tra_bang(ROWS, "so_mau", 5, 12000) == 350
    # 4 màu, 12.000 → "In 3-4 màu", bậc 10.000-15.000 → 300
    assert be.tra_bang(ROWS, "so_mau", 4, 12000) == 300
    # 4 màu, 5.000 → "In 3-4 màu", bậc 3.000-7.000 → 200
    assert be.tra_bang(ROWS, "so_mau", 4, 5000) == 200
    # 2 màu, 40.000 → "In 1-2 màu", bậc >30.000 = 1,5% × 40.000 = 600 tờ
    assert be.tra_bang(ROWS, "so_mau", 2, 40000) == 600
    # sóng 1 con, 8.000 → bậc 7.000-10.000 → 150
    assert be.tra_bang(ROWS, "so_con", 1, 8000) == 150
    # sóng nhiều con (3), 8.000 → dòng 2-999, bậc 7.000-10.000 → 120
    assert be.tra_bang(ROWS, "so_con", 3, 8000) == 120


def test_bien_bac_chan_tren_bao_gom():
    # SL đúng biên 3.000 → "trở xuống" (bậc đầu), 3 màu → 150
    assert be.tra_bang(ROWS, "so_mau", 3, 3000) == 150
    # 3.001 → bậc kế → 200
    assert be.tra_bang(ROWS, "so_mau", 3, 3001) == 200


def test_khong_khop_tra_0():
    assert be.tra_bang(ROWS, "so_mau", 9, 5000) == 0.0   # 9 màu: không dòng nào
    assert be.tra_bang(ROWS, "so_con", 1, 0) == 0.0      # SL 0: không bậc


def test_bu_hao_cong_doan_theo_kieu():
    ctx = dict(rows=ROWS, so_mau=4, so_con=1, sl=12000)
    assert be.bu_hao_cong_doan({"kieu_bu_hao": "khong"}, **ctx) == 0.0
    assert be.bu_hao_cong_doan({"kieu_bu_hao": "co_dinh", "so_to_bu_hao": 50}, **ctx) == 50
    assert be.bu_hao_cong_doan({"kieu_bu_hao": "theo_so_mau"}, **ctx) == 300      # 4 màu/12.000
    assert be.bu_hao_cong_doan({"kieu_bu_hao": "theo_so_con"}, **ctx) == 170      # 1 con/12.000 (bậc 10-15k)


def test_tong_bu_hao_don():
    # Đơn 4 màu, 12.000: In (bảng 300) + Ép kim (cố định 50) + Bồi (cố định 50) = 400
    cds = [
        {"kieu_bu_hao": "theo_so_mau"},
        {"kieu_bu_hao": "co_dinh", "so_to_bu_hao": 50},
        {"kieu_bu_hao": "co_dinh", "so_to_bu_hao": 50},
        {"kieu_bu_hao": "khong"},                         # ghi kẽm → 0
    ]
    assert be.tong_bu_hao(cds, rows=ROWS, so_mau=4, so_con=1, sl=12000) == 400
    # + đơn yêu cầu 2% → +240 tờ
    assert be.tong_bu_hao(cds, rows=ROWS, so_mau=4, so_con=1, sl=12000, pct_yeu_cau=2) == 400 + 240
