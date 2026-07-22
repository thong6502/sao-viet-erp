"""Engine tính giá vốn THEO THÀNH PHẦN — hàm THUẦN (không I/O, không ORM).

Bản REDESIGN (theo `docs/redesign-tinh-gia.md` §0/§1.6): giá vốn theo SẢN LƯỢNG, KHÔNG hệ số.
CHI PHÍ CHỈ 2 LOẠI DÒNG (không còn rổ A/B/C/D):

  • Nguyên vật liệu (nvl) ← giấy + vật tư in ấn (kẽm/mực/keo/màng…).
  • Công đoạn (cong_doan) ← MỌI công đoạn (chế bản/kẽm · in · gia công) theo thứ tự routing.

Quy cách in (mẫu/cách/màu/kẽm) chỉ MÔ TẢ + phơi biến (so_mau/so_mat/so_kem) cho công thức — KHÔNG
phải rổ chi phí. Giá vốn = Σ dòng nvl + Σ dòng công đoạn.

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

import ast
import operator
import re
from math import ceil, floor

from .routing_engine import basis_qty, compute_step_cost
from .bu_hao_engine import bu_hao_cong_doan


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


OPERATORS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: operator.pow,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}

FUNCTIONS = {
    'ceil': ceil,
    'floor': floor,
    'round': round,
    'max': max,
    'min': min,
}

MATH_FUNCS = {"ceil", "floor", "round", "max", "min"}


def _eval_node(node, variables: dict) -> float:
    if isinstance(node, ast.Num):
        return float(node.n)
    elif isinstance(node, ast.Constant):
        if isinstance(node.value, (int, float)):
            return float(node.value)
        raise ValueError(f"Hằng số không hợp lệ: {node.value}")
    elif isinstance(node, ast.Name):
        name = node.id
        if name in variables:
            return float(variables[name] or 0.0)
        raise ValueError(f"Biến không xác định: {name}")
    elif isinstance(node, ast.BinOp):
        left = _eval_node(node.left, variables)
        right = _eval_node(node.right, variables)
        op_type = type(node.op)
        if op_type in OPERATORS:
            return OPERATORS[op_type](left, right)
        raise ValueError(f"Toán tử không được hỗ trợ: {op_type}")
    elif isinstance(node, ast.UnaryOp):
        operand = _eval_node(node.operand, variables)
        op_type = type(node.op)
        if op_type in OPERATORS:
            return OPERATORS[op_type](operand)
        raise ValueError(f"Toán tử một ngôi không được hỗ trợ: {op_type}")
    elif isinstance(node, ast.Call):
        if not isinstance(node.func, ast.Name):
            raise ValueError("Gọi hàm không hợp lệ")
        func_name = node.func.id
        if func_name not in FUNCTIONS:
            raise ValueError(f"Hàm không được hỗ trợ: {func_name}")
        args = [_eval_node(arg, variables) for arg in node.args]
        return float(FUNCTIONS[func_name](*args))
    else:
        raise ValueError(f"Cú pháp không được hỗ trợ: {type(node)}")


def safe_eval(expr_str: str, variables: dict) -> float:
    if not expr_str or not expr_str.strip():
        return 0.0
    expr_str = expr_str.replace('×', '*').replace('÷', '/').replace('−', '-')
    try:
        node = ast.parse(expr_str.strip(), mode='eval').body
        return _eval_node(node, variables)
    except Exception as e:
        raise ValueError(f"Lỗi công thức: {e}")


def format_substituted_formula(formula_str: str, variables: dict) -> str:
    if not formula_str or not formula_str.strip():
        return ""
    word_regex = re.compile(r'\b([a-zA-Z_][a-zA-Z0-9_]*)\b')
    def replacer(match):
        word = match.group(1)
        if word in MATH_FUNCS:
            return word
        if word in variables:
            val = variables[word]
            return f"{word}({_vi(val)})"
        return word
    substituted = word_regex.sub(replacer, formula_str)
    substituted = substituted.replace('*', ' × ').replace('/', ' ÷ ').replace('-', ' − ').replace('+', ' + ')
    substituted = re.sub(r'\s+', ' ', substituted).strip()
    return substituted


# 2 nhóm duy nhất (§1.6): Nguyên vật liệu (giấy + vật tư) · Công đoạn (chế bản/in/gia công).
_COLS = {
    "nvl": [
        {"key": "ten", "label": "Nguyên vật liệu", "align": "left", "kind": "text"},
        {"key": "so_to", "label": "SL tờ", "align": "right", "kind": "number"},
        {"key": "don_gia", "label": "Đơn giá", "align": "right", "kind": "money"},
        {"key": "thanh_tien", "label": "Số tiền", "align": "right", "kind": "money"},
        {"key": "gia_don_sp", "label": "đ/TP", "align": "right", "kind": "money"},
        {"key": "cong_thuc", "label": "Công thức thế số", "align": "left", "kind": "formula"},
    ],
    "cong_doan": [
        {"key": "ten", "label": "Công đoạn", "align": "left", "kind": "text"},
        {"key": "thanh_tien", "label": "Số tiền", "align": "right", "kind": "money"},
        {"key": "gia_don_sp", "label": "đ/TP", "align": "right", "kind": "money"},
        {"key": "cong_thuc", "label": "Công thức thế số", "align": "left", "kind": "formula"},
        {"key": "ghi_chu", "label": "Ghi chú", "align": "left", "kind": "text"},
    ],
}
_NAMES = {"nvl": "Nguyên vật liệu", "cong_doan": "Công đoạn"}


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


def binh_bai_nghich(*, con: int, dai_tp: float, rong_tp: float, chua_mm: float,
                    kho_nguyen_dai: float, kho_nguyen_rong: float,
                    kho_may_dai: float = 0.0, kho_may_rong: float = 0.0) -> dict:
    """Bình bài NGHỊCH: cho số con ĐÚNG N → khổ tờ in ÍT PHẾ nhất khi xả từ tờ giấy nguyên.

    Duyệt mọi phân rã hàng×cột với hàng×cột = N (đúng N) × 2 hướng xoay SP. Khổ tờ in cần:
    Dài = hàng×(cạnh SP dọc theo chiều dài) + chừa; Rộng = cột×(cạnh SP theo chiều rộng) + chừa
    — khớp `binh_bai_layout` (usable = khổ − chừa), nên nạp khổ này trả lại đúng N con.
    Loại khổ vượt tờ giấy nguyên (và vùng in máy nếu có). Chấm ÍT PHẾ = (số tờ in xả được từ
    nguyên × N × dt·rt) / (nguyên_dài·nguyên_rộng); chọn max, hòa → khổ nhỏ hơn.

    Trả {con, kho_in_dai, kho_in_rong, rows, cols, rotated, so_to_in, hieu_suat, util_pct}.
    con=0 khi KHÔNG cách nào đúng N mà lọt nguyên (FE báo đỏ, giữ nguyên khổ). Yêu cầu khổ
    nguyên > 0 — caller PHẢI bỏ qua (không gọi) khi chưa nhập nguyên.
    """
    N = int(con)
    dt, rt, ch = _f(dai_tp), _f(rong_tp), max(_f(chua_mm), 0.0)
    KND, KNR = _f(kho_nguyen_dai), _f(kho_nguyen_rong)
    none = {"con": 0, "kho_in_dai": 0.0, "kho_in_rong": 0.0, "rows": 0, "cols": 0,
            "rotated": False, "so_to_in": 0, "hieu_suat": 0.0, "util_pct": 0.0}
    if N < 1 or dt <= 0 or rt <= 0 or KND <= 0 or KNR <= 0:
        return none
    # Ràng buộc trên: tờ giấy nguyên, và vùng in máy nếu có (lấy min).
    max_d = min(KND, _f(kho_may_dai)) if _f(kho_may_dai) > 0 else KND
    max_r = min(KNR, _f(kho_may_rong)) if _f(kho_may_rong) > 0 else KNR
    dt_tp, dt_ng = dt * rt, KND * KNR
    best = None
    for rows in range(1, N + 1):
        if N % rows:                       # chỉ phân rã ĐÚNG N (hàng×cột = N)
            continue
        cols = N // rows
        for pd, pr, rot in ((dt, rt, False), (rt, dt, True)):   # 2 hướng xoay sản phẩm
            D = rows * pd + ch
            R = cols * pr + ch
            if D > max_d + 1e-6 or R > max_r + 1e-6:
                continue
            sheets = max(floor(KND / D) * floor(KNR / R),       # xả tờ in từ nguyên (± xoay tờ in)
                         floor(KND / R) * floor(KNR / D))
            if sheets < 1:
                continue
            util = sheets * N * dt_tp / dt_ng
            key = (round(util, 6), -round(D * R, 3))            # max phế↓; hòa → khổ nhỏ hơn
            if best is None or key > best[0]:
                best = (key, D, R, rows, cols, rot, sheets, util)
    if best is None:
        return none
    _, D, R, rows, cols, rot, sheets, util = best
    hieu_suat = round(N * dt_tp / (D * R) * 100, 1) if D * R > 0 else 0.0
    return {"con": N, "kho_in_dai": round(D, 1), "kho_in_rong": round(R, 1),
            "rows": rows, "cols": cols, "rotated": rot, "so_to_in": sheets,
            "hieu_suat": hieu_suat, "util_pct": round(util * 100, 1)}


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
    try:
        res = compute_step_cost(cd, ctx)
    except Exception as e:  # noqa: BLE001 — không crash, gom vào warnings
        warnings.append(f"Công đoạn '{ten}': không tính được ({e}) — tính 0đ.")
        return 0.0, "lỗi cấu hình — 0đ"
    rate = res.get("rate_used")
    bq = res.get("basis_qty")
    ghi = f"{_vi(bq)} × {_vi(rate)}đ" if (rate is not None and bq is not None) else ""
    return _f(res.get("total")), ghi


def _compute_one(tp: dict, so_luong_mac_dinh: int, warnings: list[str], flags: dict, bu_hao_rows: list[dict]) -> dict:
    """Tính chi phí 1 SẢN PHẨM → 2 nhóm (nvl · cong_doan). Trả {name, rows, total, meta}."""
    name = tp.get("ten") or ""
    sl = _i(tp.get("so_luong")) or _i(so_luong_mac_dinh)   # SL của sản phẩm này; 0 → SL mặc định phiếu
    so_to_per_sp = max(_i(tp.get("so_to_per_sp"), 1), 1)   # số tờ (tay) trên 1 sản phẩm
    qc = tp.get("quy_cach_in", "mot_mat")
    passes = 1 if qc == "mot_mat" else 2                    # số mặt qua máy (2 mặt / tự trở = 2)

    # --- Khổ (mm) ---
    kho_ng_d = _f(tp.get("kho_dai"))     # giấy nguyên ①
    kho_ng_r = _f(tp.get("kho_rong"))
    kho_in_d = _f(tp.get("kho_in_dai"))  # tờ in ② (= VÙNG IN khi chọn máy) → bình bài con + m²
    kho_in_r = _f(tp.get("kho_in_rong"))
    if kho_in_d <= 0 or kho_in_r <= 0:   # thiếu khổ in → in thẳng khổ giấy nguyên (không xả)
        kho_in_d, kho_in_r = kho_ng_d, kho_ng_r
    # Cảnh báo: khổ tờ in > khổ giấy nguyên (bất khả thi vật lý) → bình bài trên vùng ảo, số con
    # thổi phồng, giá thành thiếu. MÁY CHỈ GHI NHẬN — chỉ nhắc, KHÔNG tự sửa/chặn.
    if kho_ng_d > 0 and kho_ng_r > 0 and (kho_in_d > kho_ng_d or kho_in_r > kho_ng_r):
        warnings.append(
            f"Thành phần '{name}': khổ tờ in {kho_in_d:g}×{kho_in_r:g} lớn hơn khổ giấy "
            f"{kho_ng_d:g}×{kho_ng_r:g} — số con có thể sai (bình bài vượt khổ giấy)."
        )
    # Khổ giấy CHẠY máy (cho XẢ GIẤY): khác khổ tờ in ② (vùng in) khi chọn máy. Thiếu → = khổ tờ in.
    kho_may_d = _f(tp.get("kho_may_dai")) or kho_in_d
    kho_may_r = _f(tp.get("kho_may_rong")) or kho_in_r
    # A: khổ tờ in KHÔNG lọt khổ giấy MÁY nhận (kho_may = kho_max máy) — máy không kẹp/chạy được tờ
    # này (xét cả XOAY qua `_fit`). Chỉ nhắc, không chặn. Không có máy → kho_may = kho_in → luôn lọt.
    if kho_may_d > 0 and kho_may_r > 0 and _fit(kho_may_d, kho_may_r, kho_in_d, kho_in_r) < 1:
        warnings.append(
            f"Thành phần '{name}': khổ tờ in {kho_in_d:g}×{kho_in_r:g} lớn hơn khổ giấy máy nhận "
            f"{kho_may_d:g}×{kho_may_r:g} — máy không chạy được tờ này."
        )
    dai_tp = _f(tp.get("dai_thanh_pham"))    # thành phẩm ③
    rong_tp = _f(tp.get("rong_thanh_pham"))
    chua_mm = (_f(tp.get("chua_xen")) + _f(tp.get("chua_tay_ke")) + _f(tp.get("chua_nhip"))
               + _f(tp.get("chua_duoi")) + _f(tp.get("chua_ca_gay")))

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

    # --- Số mảnh xả (② lên ①): cắt tờ giấy CHẠY MÁY (kho_may) từ giấy nguyên, KHÔNG dùng vùng in ---
    xa = _fit(kho_ng_d, kho_ng_r, kho_may_d, kho_may_r) if (kho_ng_d > 0 and kho_ng_r > 0) else 1
    xa = max(xa, 1)

    # --- Số tờ CẦN in (net) — tính TRƯỚC để tra bù hao THEO SỐ TỜ (không phải số lượng) ---
    to_net = ceil(sl * so_to_per_sp / con) if sl > 0 else 0

    # --- Bù hao mỗi công đoạn: TỰ áp theo mã của công đoạn (kieu_bu_hao != "khong"), tra bậc
    # theo SỐ TỜ CẦN IN (to_net). Toggle `tinh_bu_hao_cd` TẮT → bỏ qua (người dùng tự nhập bù). ---
    finishing_spoilage_sum = 0.0
    if tp.get("tinh_bu_hao_cd", True):
        for row in tp.get("thanh_phams") or []:
            cd = row.get("cong_doan") or {}
            if cd and cd.get("kieu_bu_hao", "khong") != "khong":
                finishing_spoilage_sum += bu_hao_cong_doan(cd, rows=bu_hao_rows, sl=to_net)

    # --- Số tờ: net → gross (tờ in) → tờ nguyên ---
    bu_hao = _i(tp.get("bu_hao_so_to"))         # số bù nhập tay (cộng thêm to_dau_vao)
    hao = _i(tp.get("hao_so_to"))               # số hao nhập tay (trừ bớt to_sau_in)
    to_dau_vao = to_net + finishing_spoilage_sum + bu_hao
    to_sau_in = max(to_dau_vao - hao, 0.0)
    to_nguyen = ceil(to_dau_vao / xa) if to_dau_vao > 0 else 0

    so_mau_a = _i(tp.get("so_mau_a"))
    so_mau_b = _i(tp.get("so_mau_b"))
    so_mau = so_mau_a + so_mau_b
    co_in = bool(tp.get("co_in", True))

    # --- Biến đổi đơn vị cho biến công thức (mm -> m) ---
    dai_tp_m = dai_tp / 1000.0
    rong_tp_m = rong_tp / 1000.0
    dai_nguyen_m = kho_ng_d / 1000.0
    rong_nguyen_m = kho_ng_r / 1000.0
    dai_in_m = kho_in_d / 1000.0
    rong_in_m = kho_in_r / 1000.0
    dinh_luong = _f(tp.get("gsm")) / 1000.0  # gsm / 1000 -> kg/m2 (0.25)

    # --- Số kẽm ---
    # 1 bộ kẽm mang cả 2 mặt (mot_mat / tự trở / trở nhíp) → chỉ màu A; AB (hai_mat) = 2 bộ riêng A+B.
    kem_mau = so_mau_a if qc in ("mot_mat", "tu_tro", "tro_nhip") else (so_mau_a + so_mau_b)
    so_kem = kem_mau * so_to_per_sp
    so_luot = to_dau_vao * passes

    # --- Cấu cảnh biến dùng chung ---
    ctx_vars = {
        "dai_tp": dai_tp_m,
        "rong_tp": rong_tp_m,
        "dai_nguyen": dai_nguyen_m,
        "rong_nguyen": rong_nguyen_m,
        "dai_in": dai_in_m,
        "rong_in": rong_in_m,
        "so_luong": sl,
        "so_tp": con,
        "so_mau": so_mau,
        "so_mat": passes,
        "so_kem": so_kem,
        "to_dau_vao": to_dau_vao,
        "to_sau_in": to_sau_in,
        "to_nguyen": to_nguyen,
        "dinh_luong": dinh_luong,
    }

    # 2 nhóm: nvl (giấy + vật tư) · cong_doan (chế bản/in/gia công theo thứ tự routing).
    rows: dict[str, list[dict]] = {"nvl": [], "cong_doan": []}

    # --- Giấy (Nguyên vật liệu) ---
    nguon = tp.get("nguon_giay", "cong_ty")
    don_gia_giay = _f(tp.get("don_gia_giay"))
    don_vi = tp.get("don_gia_don_vi", "to")
    giay_ten = tp.get("giay_ten") or tp.get("kho_nguyen") or "Giấy"

    if nguon == "khach":
        rows["nvl"].append({
            "ten": _pre(name, giay_ten),
            "so_to": to_nguyen,
            "don_gia": 0.0,
            "thanh_tien": 0.0,
            "gia_don_sp": 0.0,
            "ghi_chu": "Khách cấp giấy",
            "cong_thuc": "Khách cấp giấy — 0đ"
        })
    else:
        formula = tp.get("cong_thuc_gia")
        if not formula or not formula.strip():
            if don_vi in ("kg", "tan"):   # giấy bán theo CÂN → tiền = khối lượng × đ/kg
                formula = "dinh_luong * dai_nguyen * rong_nguyen * don_gia_kg * to_nguyen"
            else:                          # to | ram | cai → tính theo tờ
                formula = "don_gia * to_nguyen"
        
        eval_ctx = dict(ctx_vars)
        eval_ctx["don_gia"] = don_gia_giay
        # don_gia_kg: quy về đ/kg cho công thức theo kg. tan (đ/tấn) → ÷1000; kg/khác → thẳng.
        eval_ctx["don_gia_kg"] = don_gia_giay / 1000.0 if don_vi == "tan" else don_gia_giay

        try:
            gia_giay = safe_eval(formula, eval_ctx)
        except Exception as e:
            warnings.append(f"Thành phần '{name}': lỗi công thức giấy ({e}) — tính 0đ.")
            gia_giay = 0.0

        rows["nvl"].append({
            "ten": _pre(name, giay_ten),
            "so_to": to_nguyen,
            "don_gia": _r(don_gia_giay),
            "thanh_tien": _r(gia_giay),
            "gia_don_sp": _r(gia_giay / sl) if sl > 0 else 0.0,
            "cong_thuc": format_substituted_formula(formula, eval_ctx)
        })

    # --- Vật tư in ấn thêm (mực/màng/keo…) → Nguyên vật liệu: thế biến vào CÔNG THỨC của vật tư
    # (HỆT giấy — công thức nằm ở danh mục vật tư, engine chỉ thế số). don_gia/don_gia_kg/m² phơi sẵn. ---
    for vt in tp.get("vat_tus") or []:
        vt_ten = vt.get("ten") or "Vật tư"
        vt_formula = vt.get("cong_thuc_gia")
        vt_don_gia = _f(vt.get("don_gia"))
        if not vt_formula or not vt_formula.strip():
            warnings.append(f"Vật tư '{vt_ten}' (thành phần '{name}'): chưa có công thức — tính 0đ.")
            tien_vt, dan_vt = 0.0, "thiếu công thức — 0đ"
        else:
            vt_don_vi = vt.get("don_vi_gia", "kg")
            eval_ctx = dict(ctx_vars)
            eval_ctx["don_gia"] = vt_don_gia
            eval_ctx["don_gia_kg"] = vt_don_gia / 1000.0 if vt_don_vi == "tan" else vt_don_gia
            eval_ctx["don_gia_m2"] = vt_don_gia
            try:
                tien_vt = safe_eval(vt_formula, eval_ctx)
                dan_vt = format_substituted_formula(vt_formula, eval_ctx)
            except Exception as e:
                warnings.append(f"Vật tư '{vt_ten}': lỗi công thức ({e}) — tính 0đ.")
                tien_vt, dan_vt = 0.0, "lỗi công thức — 0đ"
        rows["nvl"].append({
            "ten": _pre(name, vt_ten),
            "so_to": to_dau_vao,
            "don_gia": _r(vt_don_gia),
            "thanh_tien": _r(tien_vt),
            "gia_don_sp": _r(tien_vt / sl) if sl > 0 else 0.0,
            "cong_thuc": dan_vt,
        })

    # --- Công đoạn trong chuỗi thuộc print/prepress → In/Kẽm ĐÃ là CÔNG ĐOẠN (không hard-code nữa) ---
    chain_nhoms = {((r.get("cong_doan") or {}).get("nhom")) for r in (tp.get("thanh_phams") or [])}
    has_print_cd = "print" in chain_nhoms
    has_prepress_cd = "prepress" in chain_nhoms

    # --- Công in (FALLBACK field cứng — chỉ khi chuỗi CHƯA có công đoạn 'print') ---
    if co_in and not has_print_cd:
        dg_in = _f(tp.get("don_gia_cong_in"))
        formula = "to_dau_vao * so_mat * don_gia_luot"
        
        eval_ctx = dict(ctx_vars)
        eval_ctx["don_gia"] = dg_in
        eval_ctx["don_gia_luot"] = dg_in

        try:
            tien_in = safe_eval(formula, eval_ctx)
        except Exception as e:
            warnings.append(f"Thành phần '{name}': lỗi công thức công in ({e}) — tính 0đ.")
            tien_in = 0.0

        rows["cong_doan"].append({
            "ten": _pre(name, "Công in"),
            "thanh_tien": _r(tien_in),
            "gia_don_sp": _r(tien_in / sl) if sl > 0 else 0.0,
            "cong_thuc": format_substituted_formula(formula, eval_ctx),
            "ghi_chu": f"{so_luot} lượt ({to_dau_vao} tờ × {passes} mặt)"
        })

    # --- Chế bản/kẽm (FALLBACK field cứng — chỉ khi chuỗi CHƯA có công đoạn 'prepress') ---
    if co_in and so_kem > 0 and not has_prepress_cd:
        che_ban_dg = _f(tp.get("che_ban_don_gia"))
        formula = "so_kem * don_gia_kem"
        
        eval_ctx = dict(ctx_vars)
        eval_ctx["don_gia"] = che_ban_dg
        eval_ctx["don_gia_kem"] = che_ban_dg

        try:
            tien_che_ban = safe_eval(formula, eval_ctx)
        except Exception as e:
            warnings.append(f"Thành phần '{name}': lỗi công thức chế bản ({e}) — tính 0đ.")
            tien_che_ban = 0.0

        rows["cong_doan"].append({
            "ten": _pre(name, "Chế bản / kẽm"),
            "thanh_tien": _r(tien_che_ban),
            "gia_don_sp": _r(tien_che_ban / sl) if sl > 0 else 0.0,
            "cong_thuc": format_substituted_formula(formula, eval_ctx),
            "ghi_chu": "",
        })

    # --- Công đoạn trong chuỗi (chế bản/in/gia công) theo thứ tự routing ---
    ctx_base = {
        "so_to_in_gross": to_net,
        "so_luong_thanh_pham": sl,
        "dt_to_in_cm2": (kho_in_d / 10.0) * (kho_in_r / 10.0),
        "so_con": con,
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
        # so_mat: dòng IN (nhom=print) LUÔN theo số mặt cách in (passes) — KHÔNG để field mặc định=1
        # nuốt (N2: model so_mat default=1 khiến fallback passes thành code chết). Finishing tự set
        # so_mat (cán 1/2 mặt); ≤0 → dùng passes.
        if cd.get("nhom") == "print":
            ctx["so_mat"] = passes
        else:
            _rm = _i(row.get("so_mat"))
            ctx["so_mat"] = _rm if _rm > 0 else passes
        ctx["so_vi_tri"] = _i(row.get("so_vi_tri"))
        ctx["dt_thanh_pham_cm2"] = _f(row.get("dien_tich"))

        formula = cd.get("cong_thuc_gia") if cd else None
        # Mặc định theo nhom khi công đoạn CHƯA khai công thức: print → công in theo lượt; prepress → kẽm.
        if (not formula or not formula.strip()) and cd:
            _nhom_cd = cd.get("nhom")
            if _nhom_cd == "print":
                formula = "to_dau_vao * so_mat * don_gia"
            elif _nhom_cd == "prepress":
                formula = "so_kem * don_gia"
        if formula and formula.strip():
            final_don_gia = don_gia_r
            if not final_don_gia and cd:
                try:
                    res_cost = compute_step_cost(cd, ctx)
                    final_don_gia = res_cost.get("rate_used") or 0.0
                except Exception:
                    final_don_gia = cd.get("run_rate") or 0.0

            eval_ctx = dict(ctx_vars)
            eval_ctx["don_gia"] = final_don_gia
            eval_ctx["don_gia_m2"] = final_don_gia
            eval_ctx["so_mat"] = ctx["so_mat"]
            eval_ctx["so_vi_tri"] = ctx["so_vi_tri"]
            eval_ctx["dien_tich"] = ctx["dt_thanh_pham_cm2"]

            try:
                tien = safe_eval(formula, eval_ctx)
                dan_d = format_substituted_formula(formula, eval_ctx)
                ghi_chu = ""
            except Exception as e:
                warnings.append(f"Dòng '{ten_r}': lỗi công thức ({e}) — tính 0đ.")
                tien = 0.0
                dan_d = "lỗi công thức — 0đ"
                ghi_chu = str(e)
        else:
            # Formula-only (chốt 2026-07-22): công đoạn finishing/gia công CHƯA khai công thức
            # → 0đ + cảnh báo. KHÔNG dùng fallback đơn giá routing / rate cũ (tránh "×400đ ma"
            # không ai chủ ý nhập). In/kẽm (print/prepress) vẫn có công thức mặc định ở trên.
            warnings.append(f"Công đoạn '{ten_r}': chưa khai công thức tính giá — tính 0đ.")
            tien = 0.0
            dan_d = "thiếu công thức — 0đ"
            ghi_chu = ""

        cong_thuc = _ct(dan_d, tien, sl) if ("÷" not in dan_d and "đ/sp" not in dan_d and "thiếu" not in dan_d) else dan_d
        if row.get("nha_cung_cap"):
            suffix = f"(thuê ngoài: {row['nha_cung_cap']})"
            ghi_chu = f"{ghi_chu} {suffix}".strip() if ghi_chu else suffix

        # MỌI công đoạn (chế bản/in/gia công) vào chung nhóm "Công đoạn", giữ thứ tự routing.
        rows["cong_doan"].append({
            "ten": _pre(name, ten_r),
            "thanh_tien": _r(tien),
            "gia_don_sp": _r(tien / sl) if sl > 0 else 0.0,
            "cong_thuc": cong_thuc,
            "ghi_chu": ghi_chu,
        })

    total = sum(_f(r.get("thanh_tien")) for grp in rows.values() for r in grp)
    return {
        "name": name,
        "rows": rows,
        "total": _r(total),
        "meta": {
            "so_luong": sl, "gia_von_don": _r(total / sl) if sl > 0 else 0.0,
            "con": con, "con_auto": bool(con_auto), "so_manh_xa": xa,
            "to_net": to_net, "to_gross": to_dau_vao, "to_nguyen": to_nguyen,
            "so_kem": so_kem, "so_luot": so_luot,
            "to_dau_vao": to_dau_vao, "to_sau_in": to_sau_in,
            "bu_hao_auto": _r(finishing_spoilage_sum),  # Σ bù hao công đoạn tự tra (theo số tờ)
            "bu_hao_tay": bu_hao, "hao_tay": hao,        # số bù / hao nhập tay
        },
    }


def compute_phieu(*, so_luong: int, thanh_phans: list[dict], bu_hao_rows: list[dict] | None = None, warnings: list[str] | None = None) -> dict:
    """Tính giá vốn 1 phiếu theo thành phần → 2 nhóm (nvl · cong_doan).

    Returns:
        {meta:{so_luong, so_thanh_phan, gia_von_don, components:[{idx,name,gia_von_tp,...}]},
         groups:[{idx,name,columns,rows,subtotal}], grand_total, warnings}.
    """
    warns = warnings if warnings is not None else []
    so_luong = _i(so_luong)
    flags: dict = {}

    grouped: dict[str, list[dict]] = {"nvl": [], "cong_doan": []}
    components: list[dict] = []

    bu_hao_list = bu_hao_rows or []

    for i, tp in enumerate(thanh_phans or []):
        one = _compute_one(tp, so_luong, warns, flags, bu_hao_list)
        for idx in ("nvl", "cong_doan"):
            grouped[idx].extend(one["rows"][idx])
        components.append({"idx": i, "name": one["name"], "gia_von_tp": one["total"], **one["meta"]})

    if not thanh_phans:
        warns.append("Phiếu chưa có thành phần nào — giá vốn = 0.")

    groups = []
    grand_total = 0.0
    for idx in ("nvl", "cong_doan"):
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
