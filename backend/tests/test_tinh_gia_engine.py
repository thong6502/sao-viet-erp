"""Engine tính giá MỚI (`services.tinh_gia_engine.tinh_gia`) — hàm THUẦN, không DB.

Case: 1 công đoạn In (per_sheet) + 1 công đoạn Cán (per_area_sides) + kẽm + giấy, có bù hao.
Khẳng định: số tờ gross đúng, tiền từng nhóm hợp lý, tổng = Σ nhóm, cảnh báo theo_gio/mực.
"""
from __future__ import annotations

from math import ceil

from app.services.tinh_gia_engine import tinh_gia

# --- Bù hao: In 3-4 màu, bậc SL ≤ 5000 → +150 tờ (trục so_mau) ---
BU_HAO_ROWS = [
    {"truc": "so_mau", "key_tu": 3, "key_den": 4,
     "bac": [{"sl_tu": 0, "sl_den": 5000, "gia_tri": 150, "don_vi": "to"},
             {"sl_tu": 5000, "sl_den": None, "gia_tri": 3, "don_vi": "pct"}]},
]

# In offset: theo số tờ in (per_sheet), 200đ/tờ, setup 100k. Góp bù hao? kiểu 'khong' (bù hao lấy từ dòng trên).
CD_IN = {
    "ten": "In offset 4 màu", "nhom": "print", "che_do_tinh": "theo_san_luong",
    "pricing_basis": "per_sheet", "run_rate": 200, "setup_cost": 100000,
    "kieu_bu_hao": "theo_so_mau", "so_to_bu_hao": 0,  # kéo bù hao canh máy từ bảng theo số màu
}
# Cán màng: theo diện tích × số mặt (per_area_sides), 0.05đ/cm²/mặt.
CD_CAN = {
    "ten": "Cán màng bóng", "nhom": "finishing", "che_do_tinh": "theo_san_luong",
    "pricing_basis": "per_area_sides", "run_rate": 0.05, "setup_cost": 50000,
    "kieu_bu_hao": "khong",
}
# Bế: tính theo giờ (v1 bỏ qua) — để kiểm cảnh báo.
CD_BE_GIO = {
    "ten": "Bế nổi", "nhom": "finishing", "che_do_tinh": "theo_gio",
    "pricing_basis": "per_sheet",
}

GIAY = {"ten": "Couche 150", "don_gia": 2000, "don_vi_gia": "to", "gsm": 150}


def _grp(res, idx):
    return next(g for g in res["groups"] if g["idx"] == idx)


def test_tinh_gia_full_case():
    qty, pieces, so_mau, so_mat = 3000, 2, 4, 1
    res = tinh_gia(
        qty=qty, pieces_per_sheet=pieces, so_mau=so_mau, so_mat=so_mat,
        giay=GIAY, kem_don_gia=80000,
        cong_doans=[CD_IN, CD_CAN, CD_BE_GIO], bu_hao_rows=BU_HAO_ROWS,
        dt_to_in_cm2=79 * 109, dt_thanh_pham_cm2=9 * 5.5,
    )

    # --- Số tờ ---
    to_net = ceil(qty / pieces)              # 1500
    bu_hao = 150                              # bậc ≤5000 của In 3-4 màu
    to_gross = to_net + bu_hao                # 1650
    assert res["meta"]["to_net"] == to_net
    assert res["meta"]["bu_hao_to"] == bu_hao
    assert res["meta"]["to_gross"] == to_gross
    assert res["meta"]["so_kem"] == so_mau * so_mat  # 4

    # --- A Giấy: 1650 × 2000 = 3.300.000 ---
    a = _grp(res, "A")
    assert len(a["rows"]) == 1
    assert a["rows"][0]["so_to"] == to_gross
    assert a["subtotal"] == to_gross * 2000

    # --- C Chế bản: kẽm 4 × 80000 = 320.000 ---
    c = _grp(res, "C")
    kem_row = c["rows"][0]
    assert kem_row["sl"] == 4
    assert kem_row["thanh_tien"] == 4 * 80000
    assert c["subtotal"] == 320000

    # --- B Công in: In per_sheet = setup 100k + 1650×200 = 430.000 ---
    b = _grp(res, "B")
    assert len(b["rows"]) == 1
    assert b["rows"][0]["thanh_tien"] == 100000 + to_gross * 200
    assert b["subtotal"] == 430000

    # --- D Gia công: Cán per_area_sides + Bế (theo giờ → 0đ) ---
    d = _grp(res, "D")
    # Cán = setup 50k + (dt_to × so_mat × to_gross) × 0.05
    can_basis = (79 * 109) * so_mat * to_gross
    can_expected = round(50000 + can_basis * 0.05, 2)
    can_row = next(r for r in d["rows"] if "Cán" in r["ten"])
    assert can_row["thanh_tien"] == can_expected
    be_row = next(r for r in d["rows"] if "Bế" in r["ten"])
    assert be_row["thanh_tien"] == 0.0

    # --- Tổng = Σ nhóm ---
    assert res["grand_total"] == round(sum(g["subtotal"] for g in res["groups"]), 2)

    # --- Cảnh báo theo_gio ---
    assert any("theo giờ" in w for w in res["warnings"])


def test_thieu_gia_kem_va_khong_giay():
    res = tinh_gia(
        qty=1000, pieces_per_sheet=1, so_mau=2, so_mat=1,
        giay=None, kem_don_gia=0,
        cong_doans=[CD_IN], bu_hao_rows=[],
    )
    assert any("Chưa chọn giấy" in w for w in res["warnings"])
    assert any("đơn giá kẽm" in w for w in res["warnings"])
    # Không giấy → nhóm A rỗng; không bù hao rows → gross = net = 1000.
    assert _grp(res, "A")["rows"] == []
    assert res["meta"]["to_gross"] == 1000
    # In: setup 100k + 1000×200 = 300.000
    assert _grp(res, "B")["subtotal"] == 300000
