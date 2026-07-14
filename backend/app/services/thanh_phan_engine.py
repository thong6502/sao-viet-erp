"""Engine tính giá vốn THEO THÀNH PHẦN — hàm THUẦN (không I/O, không ORM).

Bản REDESIGN (theo `docs/redesign-tinh-gia.md`): giá vốn theo SẢN LƯỢNG, KHÔNG hệ số.
1 phiếu = nhiều "thành phần" (mỗi thành phần = 1 tờ giấy). Mỗi thành phần tính 4 nhóm rồi CỘNG:

  A Giấy       ← số TỜ NGUYÊN (đã xả) × đơn giá giấy (theo tờ | theo tấn).
  B Công in    ← (tờ IN gross × số mặt) lượt × đơn giá công in (mực GỘP; KHÔNG nhân số màu).
  C Chế bản/kẽm← (màu A + màu B) × số tay × đơn giá kẽm.
  D Gia công   ← từng dòng finishing (đơn giá phẳng HOẶC compute_step_cost công đoạn).

BỐN KHỔ (mm) — không lẫn:
  ① khổ giấy nguyên (kho_ng_dai/rong) — MUA về, tính tiền giấy.
  ② khổ tờ in (kho_in_dai/rong)       — chạy máy, tính số lượt + bình bài. Thiếu → = ① (không xả).
  ③ khổ thành phẩm (dai/rong_thanh_pham) — input bình bài.
  ④ con/tờ = tự bình bài ③ lên ② (trừ chừa); override bằng so_con khi con_auto=False.

HAI PHÉP CHIA:
  • Xả giấy ① → ②: số mảnh = fit hình học của ② lên ① (min 1).
  • Bình bài ② → ④: con = fit hình học của ③ lên (② − chừa).

KHÔNG hệ số (mọi hệ số khoán/quy đổi = 1 → đã gỡ). Giá vốn → BỎ QUA lợi nhuận dòng finishing.
"""
from __future__ import annotations

from math import ceil, floor

from .routing_engine import basis_qty, compute_step_cost


def _f(v, d: float = 0.0) -> float:
    if v is None:
        return d
    try:
        return float(v)
    except (TypeError, ValueError):
        return d


def _i(v, d: int = 0) -> int:
    try:
        return int(v)
    except (TypeError, ValueError):
        return d


def _r(v: float) -> float:
    """Làm tròn 2 số lẻ → number (JSON)."""
    return round(_f(v), 2)


_COLS = {
    "A": [
        {"key": "ten", "label": "Loại giấy", "align": "left", "kind": "text"},
        {"key": "so_to", "label": "SL tờ", "align": "right", "kind": "number"},
        {"key": "don_gia", "label": "Đơn giá", "align": "right", "kind": "money"},
        {"key": "thanh_tien", "label": "Số tiền", "align": "right", "kind": "money"},
        {"key": "cong_thuc", "label": "Công thức", "align": "left", "kind": "formula"},
    ],
    "B": [
        {"key": "ten", "label": "Tên công đoạn", "align": "left", "kind": "text"},
        {"key": "thanh_tien", "label": "Số tiền", "align": "right", "kind": "money"},
        {"key": "cong_thuc", "label": "Công thức", "align": "left", "kind": "formula"},
        {"key": "ghi_chu", "label": "Ghi chú", "align": "left", "kind": "text"},
    ],
    "C": [
        {"key": "ten", "label": "Nội dung", "align": "left", "kind": "text"},
        {"key": "sl", "label": "SL", "align": "right", "kind": "number"},
        {"key": "don_gia", "label": "Đơn giá", "align": "right", "kind": "money"},
        {"key": "thanh_tien", "label": "Số tiền", "align": "right", "kind": "money"},
        {"key": "cong_thuc", "label": "Công thức", "align": "left", "kind": "formula"},
    ],
    "D": [
        {"key": "ten", "label": "Tên công đoạn", "align": "left", "kind": "text"},
        {"key": "thanh_tien", "label": "Số tiền", "align": "right", "kind": "money"},
        {"key": "cong_thuc", "label": "Công thức", "align": "left", "kind": "formula"},
        {"key": "ghi_chu", "label": "Ghi chú", "align": "left", "kind": "text"},
    ],
}
_NAMES = {"A": "Giấy", "B": "Công in", "C": "Chế bản", "D": "Gia công sau in"}


def _pre(name: str, label: str) -> str:
    name = (name or "").strip()
    return f"{name} · {label}" if name else label


def _fit(outer_d: float, outer_r: float, inner_d: float, inner_r: float) -> int:
    """Số ô (inner) xếp vừa vào (outer) — thử cả 2 hướng, lấy max. 0 nếu không vừa."""
    if inner_d <= 0 or inner_r <= 0 or outer_d <= 0 or outer_r <= 0:
        return 0
    straight = floor(outer_d / inner_d) * floor(outer_r / inner_r)
    rotated = floor(outer_d / inner_r) * floor(outer_r / inner_d)
    return max(straight, rotated)


def binh_bai_layout(*, kho_in_dai: float, kho_in_rong: float, dai_tp: float, rong_tp: float,
                    chua_mm: float = 0.0) -> dict:
    """Bình bài ③ lên ② (trừ chừa) — trả LAYOUT đầy đủ để FE vẽ sơ đồ ĐÚNG engine.

    Trả {con, cols, rows, rotated, usable_dai, usable_rong, kho_in_dai, kho_in_rong, dai_tp, rong_tp}.
    `rotated`: True nếu hướng xoay 90° cho nhiều con hơn. cols = theo chiều RỘNG, rows = theo chiều DÀI.
    """
    usable_d = max(kho_in_dai - chua_mm, 0.0)
    usable_r = max(kho_in_rong - chua_mm, 0.0)
    base = {"kho_in_dai": kho_in_dai, "kho_in_rong": kho_in_rong,
            "dai_tp": dai_tp, "rong_tp": rong_tp,
            "usable_dai": usable_d, "usable_rong": usable_r}
    if dai_tp <= 0 or rong_tp <= 0 or usable_d <= 0 or usable_r <= 0:
        return {**base, "con": 0, "cols": 0, "rows": 0, "rotated": False}
    s_rows, s_cols = floor(usable_d / dai_tp), floor(usable_r / rong_tp)   # thẳng
    r_rows, r_cols = floor(usable_d / rong_tp), floor(usable_r / dai_tp)   # xoay 90°
    if r_rows * r_cols > s_rows * s_cols:
        rows, cols, rot = r_rows, r_cols, True
    else:
        rows, cols, rot = s_rows, s_cols, False
    con = rows * cols
    if con == 0:                      # không vừa → không vẽ lưới lệch (1 chiều lọt vẫn = 0 con)
        rows = cols = 0
    return {**base, "con": con, "cols": cols, "rows": rows, "rotated": rot}


def binh_bai_con(*, kho_in_dai: float, kho_in_rong: float, dai_tp: float, rong_tp: float,
                 chua_mm: float = 0.0) -> int:
    """Số con/tờ in (chỉ số) — bọc `binh_bai_layout`. mm; chua_mm trừ mỗi chiều. >= 0."""
    return binh_bai_layout(kho_in_dai=kho_in_dai, kho_in_rong=kho_in_rong,
                           dai_tp=dai_tp, rong_tp=rong_tp, chua_mm=chua_mm)["con"]


def _vi(n) -> str:
    """Số → chuỗi vi-VN (chấm ngăn nghìn, phẩy thập phân) cho ghi chú diễn giải."""
    n = _f(n)
    if n == int(n):
        return f"{int(n):,}".replace(",", ".")
    return f"{n:,.2f}".replace(",", "\x00").replace(".", ",").replace("\x00", ".")


def _ct(dan: str, tien: float, sl: int) -> str:
    """Công thức đã-THAY-SỐ cho phiếu in: '<dẫn giải> ÷ <SL> = <đ/sp>'. sl≤0 → chỉ tổng.

    `dan` = chuỗi dẫn giải cho ra `tien` (vd '24 × 28.000đ'). Cho người đọc tự cộng lại được.
    """
    tien = _f(tien)
    if sl <= 0:
        return f"{dan} = {_vi(tien)}đ"
    return f"{dan} ÷ {_vi(sl)} = {_vi(round(tien / sl, 2))}đ/sp"


def _step_cost_safe(cd: dict, ctx: dict, warnings: list[str], ten: str) -> tuple[float, str]:
    """Tiền 1 công đoạn theo compute_step_cost, KHÔNG crash. Ghi chú = diễn giải `số × đơn giá`."""
    if cd.get("che_do_tinh", "theo_san_luong") == "theo_gio":
        warnings.append(f"Công đoạn '{ten}': tính theo giờ — bản này theo sản lượng, tính 0đ.")
        return 0.0, "theo giờ — không tính (bản sản lượng)"
    try:
        res = compute_step_cost(cd, ctx)
    except Exception as e:  # noqa: BLE001 — không crash, gom vào warnings
        warnings.append(f"Công đoạn '{ten}': không tính được ({e}) — tính 0đ.")
        return 0.0, "lỗi cấu hình — 0đ"
    rate = res.get("rate_used")
    bq = res.get("basis_qty")
    ghi = f"{_vi(bq)} × {_vi(rate)}đ" if (rate is not None and bq is not None) else ""
    return _f(res.get("total")), ghi


def _compute_one(tp: dict, so_luong_mac_dinh: int, warnings: list[str], flags: dict) -> dict:
    """Tính 4 nhóm chi phí cho 1 SẢN PHẨM (theo SL riêng của nó). Trả {name, rows, total, meta}."""
    name = tp.get("ten") or ""
    sl = _i(tp.get("so_luong")) or _i(so_luong_mac_dinh)   # SL của sản phẩm này; 0 → SL mặc định phiếu
    so_to_per_sp = max(_i(tp.get("so_to_per_sp"), 1), 1)   # số tờ (tay) trên 1 sản phẩm
    qc = tp.get("quy_cach_in", "mot_mat")
    passes = 1 if qc == "mot_mat" else 2                    # số mặt qua máy (2 mặt / tự trở = 2)

    # --- Khổ (mm) ---
    kho_ng_d = _f(tp.get("kho_dai"))     # giấy nguyên ①
    kho_ng_r = _f(tp.get("kho_rong"))
    kho_in_d = _f(tp.get("kho_in_dai"))  # tờ in ②
    kho_in_r = _f(tp.get("kho_in_rong"))
    if kho_in_d <= 0 or kho_in_r <= 0:   # thiếu khổ in → in thẳng khổ giấy nguyên (không xả)
        kho_in_d, kho_in_r = kho_ng_d, kho_ng_r
    dai_tp = _f(tp.get("dai_thanh_pham"))    # thành phẩm ③
    rong_tp = _f(tp.get("rong_thanh_pham"))
    chua_mm = (_f(tp.get("chua_xen")) + _f(tp.get("chua_tay_ke")) + _f(tp.get("chua_nhip"))
               + _f(tp.get("chua_duoi")) + _f(tp.get("chua_ca_gay")))   # ĐÃ là mm (thống nhất mm toàn phiếu)

    # --- ④ con/tờ: auto bình bài, override được ---
    con_auto = tp.get("con_auto", True)
    con = 0
    if con_auto and dai_tp > 0 and rong_tp > 0 and kho_in_d > 0 and kho_in_r > 0:
        con = binh_bai_con(kho_in_dai=kho_in_d, kho_in_rong=kho_in_r,
                           dai_tp=dai_tp, rong_tp=rong_tp, chua_mm=chua_mm)
        if con < 1:
            warnings.append(f"Thành phần '{name}': khổ thành phẩm lớn hơn khổ tờ in — bình bài = 0, tạm 1 con/tờ.")
            con = 1
    if con < 1:
        con = max(_i(tp.get("so_con"), 1), 1)   # fallback: nhập tay

    # --- Số mảnh xả (② lên ①) ---
    xa = _fit(kho_ng_d, kho_ng_r, kho_in_d, kho_in_r) if (kho_ng_d > 0 and kho_ng_r > 0) else 1
    xa = max(xa, 1)

    # --- Số tờ: net → gross (tờ in) → tờ nguyên ---
    to_net = ceil(sl * so_to_per_sp / con) if sl > 0 else 0
    bu_hao = _i(tp.get("bu_hao_so_to"))         # bù hao (tờ in cộng thêm) — KHÔNG hệ số
    if bu_hao > 0 and not flags.get("chua_warned"):
        flags["chua_warned"] = True
    to_gross = to_net + bu_hao
    to_nguyen = ceil(to_gross / xa) if to_gross > 0 else 0

    so_mau_a = _i(tp.get("so_mau_a"))
    so_mau_b = _i(tp.get("so_mau_b"))
    co_in = bool(tp.get("co_in", True))

    rows: dict[str, list[dict]] = {"A": [], "B": [], "C": [], "D": []}

    # --- A Giấy (theo TỜ NGUYÊN) ---
    nguon = tp.get("nguon_giay", "cong_ty")
    don_gia_giay = _f(tp.get("don_gia_giay"))
    don_vi = tp.get("don_gia_don_vi", "to")
    gsm = _f(tp.get("gsm"))
    giay_ten = tp.get("giay_ten") or tp.get("kho_nguyen") or "Giấy"
    if nguon == "khach":
        rows["A"].append({"ten": _pre(name, giay_ten), "so_to": to_nguyen,
                          "don_gia": 0.0, "thanh_tien": 0.0, "ghi_chu": "Khách cấp giấy",
                          "cong_thuc": "Khách cấp giấy — 0đ/sp"})
    elif don_vi == "tan":
        if kho_ng_d > 0 and kho_ng_r > 0 and gsm > 0:
            kg_to = (kho_ng_d / 1000.0) * (kho_ng_r / 1000.0) * gsm / 1000.0   # kg / 1 tờ nguyên
            tan = to_nguyen * kg_to / 1000.0
            gia_giay = tan * don_gia_giay
            dan_a = f"{to_nguyen}tờ ≈ {_vi(round(tan, 4))}tấn × {_vi(don_gia_giay)}đ/tấn"
        else:
            warnings.append(f"Thành phần '{name or giay_ten}': thiếu khổ/định lượng giấy — tính theo TỜ (có thể lệch).")
            gia_giay = to_nguyen * don_gia_giay
            dan_a = f"{to_nguyen} × {_vi(don_gia_giay)}đ (theo tờ — thiếu gsm)"
        rows["A"].append({"ten": _pre(name, giay_ten), "so_to": to_nguyen,
                          "don_gia": _r(don_gia_giay), "thanh_tien": _r(gia_giay),
                          "cong_thuc": _ct(dan_a, gia_giay, sl)})
    else:  # 'to' — tính theo tờ nguyên
        rows["A"].append({"ten": _pre(name, giay_ten), "so_to": to_nguyen,
                          "don_gia": _r(don_gia_giay), "thanh_tien": _r(to_nguyen * don_gia_giay),
                          "cong_thuc": _ct(f"{to_nguyen} × {_vi(don_gia_giay)}đ", to_nguyen * don_gia_giay, sl)})

    so_kem = 0
    so_luot = 0
    if co_in:
        # --- C Chế bản / kẽm: (màu A + màu B) × số tay ---
        if qc == "mot_mat":
            kem_mau = so_mau_a
        elif qc == "tu_tro":
            kem_mau = so_mau_a          # tự trở: 1 bộ kẽm, in 2 lượt
        else:  # hai_mat
            kem_mau = so_mau_a + so_mau_b
        so_kem = kem_mau * so_to_per_sp
        che_ban_dg = _f(tp.get("che_ban_don_gia"))
        if so_kem > 0:
            rows["C"].append({"ten": _pre(name, "Chế bản / kẽm"), "sl": so_kem,
                              "don_gia": _r(che_ban_dg), "thanh_tien": _r(so_kem * che_ban_dg),
                              "cong_thuc": _ct(f"{so_kem} kẽm × {_vi(che_ban_dg)}đ", so_kem * che_ban_dg, sl)})

        # --- B Công in: số lượt = tờ IN gross × số mặt (KHÔNG nhân màu; mực gộp) ---
        so_luot = to_gross * passes
        dg_in = _f(tp.get("don_gia_cong_in"))
        tien_in = so_luot * dg_in
        rows["B"].append({"ten": _pre(name, "Công in"), "thanh_tien": _r(tien_in),
                          "cong_thuc": _ct(f"{so_luot} lượt × {_vi(dg_in)}đ", tien_in, sl),
                          "ghi_chu": f"{so_luot} lượt ({to_gross} tờ × {passes} mặt)"})

    # --- D Gia công sau in (trên tờ in net; basis từ công đoạn) ---
    ctx_base = {
        "so_to_in_gross": to_net,
        "so_luong_thanh_pham": sl,
        "dt_to_in_cm2": (kho_in_d / 10.0) * (kho_in_r / 10.0),
        "so_con": con,
        # Cạnh dài thành phẩm (cm) — trục cho bậc đơn giá theo kích thước (công dán/bế…).
        "size_cm": max(dai_tp, rong_tp) / 10.0,
        "so_trang": 0, "so_cuon": 0, "so_bao": 0, "so_thung": 0,
    }
    for row in tp.get("thanh_phams") or []:
        cd = row.get("cong_doan") or {}
        ten_r = row.get("ten") or cd.get("ten") or "Công đoạn"
        row_sl = _i(row.get("so_luong"))
        don_gia_r = _f(row.get("don_gia"))
        basis = cd.get("pricing_basis") if cd else None
        ctx = dict(ctx_base)
        ctx["so_mat"] = _i(row.get("so_mat"), 1)
        ctx["so_vi_tri"] = _i(row.get("so_vi_tri"))
        ctx["dt_thanh_pham_cm2"] = _f(row.get("dien_tich"))
        ghi_chu = ""
        dan_d = None
        if don_gia_r > 0:
            if basis:
                try:
                    qty = basis_qty(basis, ctx)
                except Exception:  # noqa: BLE001
                    qty = row_sl if row_sl > 0 else sl
            else:
                qty = row_sl if row_sl > 0 else sl
            tien = don_gia_r * qty
            dan_d = f"{_vi(round(qty, 2))} × {_vi(don_gia_r)}đ"
        elif cd:
            tien, ghi_chu = _step_cost_safe(cd, ctx, warnings, ten_r)
            if "×" in ghi_chu:            # _step_cost_safe trả 'bq × rateđ' → dùng làm dẫn giải
                dan_d = ghi_chu
        else:
            warnings.append(f"Dòng gia công '{ten_r}': thiếu đơn giá & công đoạn — tính 0đ.")
            tien, ghi_chu = 0.0, "thiếu đơn giá/công đoạn — 0đ"
        cong_thuc = _ct(dan_d, tien, sl) if dan_d else (ghi_chu or f"{_vi(tien)}đ")
        if row.get("nha_cung_cap"):
            suffix = f"(thuê ngoài: {row['nha_cung_cap']})"
            ghi_chu = f"{ghi_chu} {suffix}".strip() if ghi_chu else suffix
        rows["D"].append({"ten": _pre(name, ten_r), "thanh_tien": _r(tien),
                          "cong_thuc": cong_thuc, "ghi_chu": ghi_chu})

    total = sum(_f(r.get("thanh_tien")) for grp in rows.values() for r in grp)
    return {
        "name": name,
        "rows": rows,
        "total": _r(total),
        "meta": {
            "so_luong": sl, "gia_von_don": _r(total / sl) if sl > 0 else 0.0,
            "con": con, "con_auto": bool(con_auto), "so_manh_xa": xa,
            "to_net": to_net, "to_gross": to_gross, "to_nguyen": to_nguyen,
            "so_kem": so_kem, "so_luot": so_luot,
        },
    }


def compute_phieu(*, so_luong: int, thanh_phans: list[dict], warnings: list[str] | None = None) -> dict:
    """Tính giá vốn 1 phiếu theo thành phần → cấu trúc 4 nhóm (A/B/C/D).

    Returns:
        {meta:{so_luong, so_thanh_phan, gia_von_don, components:[{idx,name,gia_von_tp,...}]},
         groups:[{idx,name,columns,rows,subtotal}], grand_total, warnings}.
    """
    warns = warnings if warnings is not None else []
    so_luong = _i(so_luong)
    flags: dict = {}

    grouped: dict[str, list[dict]] = {"A": [], "B": [], "C": [], "D": []}
    components: list[dict] = []

    for i, tp in enumerate(thanh_phans or []):
        one = _compute_one(tp, so_luong, warns, flags)
        for idx in ("A", "B", "C", "D"):
            grouped[idx].extend(one["rows"][idx])
        components.append({"idx": i, "name": one["name"], "gia_von_tp": one["total"], **one["meta"]})

    if not thanh_phans:
        warns.append("Phiếu chưa có thành phần nào — giá vốn = 0.")

    groups = []
    grand_total = 0.0
    for idx in ("A", "B", "C", "D"):
        rws = grouped[idx]
        subtotal = sum(_f(r.get("thanh_tien")) for r in rws)
        grand_total += subtotal
        groups.append({"idx": idx, "name": _NAMES[idx], "columns": _COLS[idx],
                       "rows": rws, "subtotal": _r(subtotal)})

    tong_sl = sum(_i(c.get("so_luong")) for c in components)
    gia_von_don = (grand_total / tong_sl) if tong_sl > 0 else 0.0
    return {
        "meta": {
            "so_luong": so_luong,            # SL mặc định phiếu (dùng khi sản phẩm chưa nhập SL)
            "tong_so_luong": tong_sl,        # Σ SL các sản phẩm
            "so_thanh_phan": len(thanh_phans or []),   # = SỐ SẢN PHẨM
            "gia_von_don": _r(gia_von_don),            # đơn giá BÌNH QUÂN (Σ giá vốn / Σ SL)
            "components": components,
        },
        "groups": groups,
        "grand_total": _r(grand_total),
        "warnings": warns,
    }
