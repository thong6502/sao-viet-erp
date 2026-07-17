"""KIỂM TRA engine trên báo giá THẬT 'Hộp bộ đôi Đậu trái Italy + Rổ bông' (golden 3.001đ/sp).

Dựng phiếu = DICT thuần rồi gọi compute_phieu (hàm thuần, KHÔNG ghi DB) — verify trên throwaway.
So từng dòng với bảng giá Excel gốc (ảnh khách gửi). Đóng gói + Giao hàng = công đoạn sau in.

Chạy:  cd backend && PYTHONIOENCODING=utf-8 python scripts/verify_hop_doi.py
"""
from __future__ import annotations

import sys
sys.path.insert(0, ".")
from app.services.thanh_phan_engine import compute_phieu  # noqa: E402


def _vi(n) -> str:
    n = float(n or 0)
    if n == int(n):
        return f"{int(n):,}".replace(",", ".")
    return f"{n:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def cd(nhom, ten, ct, basis="per_other", run_rate=0):
    return {"nhom": nhom, "ten": ten, "cong_thuc_gia": ct,
            "che_do_tinh": "theo_san_luong", "pricing_basis": basis, "run_rate": run_rate,
            "kieu_bu_hao": "khong"}


def row(ten, cong_doan, don_gia=0, so_mat=0):
    return {"ten": ten, "so_luong": 0, "don_gia": don_gia, "so_mat": so_mat,
            "so_vi_tri": 0, "dien_tich": 0, "cong_doan": cong_doan}


# ── Phiếu 'Hộp bộ đôi' — dựng đúng như báo giá Excel ─────────────────────────
tp = {
    "ten": "Hộp bộ đôi Đậu trái Italy + Rổ bông",
    "so_luong": 4000, "so_to_per_sp": 1,
    "quy_cach_in": "mot_mat", "so_mau_a": 4, "so_mau_b": 0,
    # ① khổ giấy NGUYÊN (mua) 44,5×64 cm → tính cân: 0,445 × 0,64
    "kho_dai": 640, "kho_rong": 445,
    # ② khổ tờ IN (chạy máy) 43,5×64 cm → cán: 0,435 × 0,64
    "kho_in_dai": 640, "kho_in_rong": 435,
    "dai_thanh_pham": 400, "rong_thanh_pham": 300,   # box trải (không dùng — con_auto tắt)
    "con_auto": False, "so_con": 2,                   # ghép 2 con/tờ (1 hộp đậu + 1 hộp rổ)
    "gsm": 250, "nguon_giay": "cong_ty",
    "don_gia_giay": 17100, "don_gia_don_vi": "kg",    # 17,1 triệu/tấn = 17.100đ/kg
    "giay_ten": "Giấy D250 (bồi) 17.100đ/kg",
    "cong_thuc_gia": None,                            # → mặc định công thức theo cân
    "co_in": False,                                   # kẽm gộp trong khoán In → tắt fallback chế bản
    # Số tờ THỦ CÔNG (tắt auto bù hao công đoạn): net 2000 → +250 bù = 2250 (giấy);
    # −150 hao in = 2100 (sau in, dùng cho cán/bồi).
    "tinh_bu_hao_cd": False, "bu_hao_so_to": 250, "hao_so_to": 150,
    "vat_tus": [],
    "thanh_phams": [
        row("In offset 4 màu (khoán, gồm kẽm)",
            cd("print", "In khoán", "1200000 + 100000 * so_mau")),
        row("Cán màng bóng",
            cd("finishing", "Cán màng bóng", "dai_in * rong_in * don_gia_m2 * to_sau_in"),
            don_gia=1950),
        row("Bồi sóng E 2 lớp 120/120",
            cd("finishing", "Bồi sóng", "0.43 * 0.635 * don_gia_m2 * to_sau_in"),
            don_gia=4100),
        row("Bồi (nền) 1.000đ/m²",
            cd("finishing", "Bồi nền", "0.43 * 0.635 * don_gia_m2 * to_sau_in"),
            don_gia=1000),
        row("Khuôn bế (một lần)",
            cd("finishing", "Khuôn bế", "don_gia"), don_gia=800000),
        row("Bế thành phẩm",
            cd("finishing", "Bế TP", "so_luong / so_tp * don_gia"), don_gia=300),
        row("Dán thành phẩm",
            cd("finishing", "Dán TP", "so_luong * don_gia"), don_gia=300),
        row("Đóng gói",
            cd("finishing", "Đóng gói", "so_luong * don_gia"), don_gia=50),
        row("Giao hàng (Củ Chi)",
            cd("finishing", "Giao hàng", "don_gia"), don_gia=800000),
    ],
}

# ── Kỳ vọng theo Excel (đ/sp) ───────────────────────────────────────────────
EXPECT = {
    "Giấy D250 (bồi) 17.100đ/kg": 685,
    "In offset 4 màu (khoán, gồm kẽm)": 400,
    "Cán màng bóng": 285,
    "Bồi sóng E 2 lớp 120/120": 588,
    "Bồi (nền) 1.000đ/m²": 143,
    "Khuôn bế (một lần)": 200,
    "Bế thành phẩm": 150,
    "Dán thành phẩm": 300,
    "Đóng gói": 50,
    "Giao hàng (Củ Chi)": 200,
}

res = compute_phieu(so_luong=4000, thanh_phans=[tp], bu_hao_rows=[])
m = res["meta"]
comp = m["components"][0]

print("=" * 92)
print("HỘP BỘ ĐÔI ĐẬU TRÁI ITALY + RỔ BÔNG  —  SL 4.000 (2000 mỗi loại, ghép 2 con/tờ)")
print(f"  con/tờ={comp['con']} · tờ net={comp['to_net']} · tờ vào máy(giấy)={comp['to_nguyen']} · "
      f"tờ sau in(gia công)={comp['to_sau_in']}")
print(f"  bù tay={comp['bu_hao_tay']} · hao tay={comp['hao_tay']} · bù hao auto={comp['bu_hao_auto']}")
print("=" * 92)
print(f"  {'DÒNG':40} {'ENGINE đ/sp':>12} {'EXCEL đ/sp':>12}  KHỚP")
print("-" * 92)

ok_all = True
for g in res["groups"]:
    for r in g["rows"]:
        ten = r["ten"].split(" · ")[-1]        # bỏ tiền tố "<tên SP> · "
        sp = r["gia_don_sp"]
        exp = EXPECT.get(ten)
        khop = "✔" if exp is not None and abs(round(sp) - exp) <= 1 else ("?" if exp is None else "✗")
        if exp is not None and abs(round(sp) - exp) > 1:
            ok_all = False
        print(f"  {ten[:40]:40} {_vi(round(sp)):>12} {(_vi(exp) if exp else '—'):>12}  {khop}")
        print(f"      └ {r['cong_thuc']}")

print("-" * 92)
tong_sp = round(m["gia_von_don"])
print(f"  {'TỔNG CỘNG':40} {_vi(tong_sp):>12} {'3.001':>12}  {'✔' if abs(tong_sp - 3001) <= 2 else '✗'}")
print(f"  Tổng giá vốn: {_vi(res['grand_total'])}đ   |   Nhận 10% → {_vi(round(tong_sp * 1.1))}đ/sp")
if res.get("warnings"):
    print("  ⚠ CẢNH BÁO:", res["warnings"])
print("=" * 92)
print("KẾT LUẬN:", "ENGINE KHỚP EXCEL ✔" if ok_all and abs(tong_sp - 3001) <= 2 else "CÓ LỆCH — soi lại ✗")
