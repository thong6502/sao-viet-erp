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
from ..models.lsx import DV_CAI, DV_TO, DV_TO_NGUYEN
from .bu_hao_engine import chuoi_nguoc_dv


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


def _suc_chua(usable: float, canh: float, khe: float) -> int:
    """Số ô xếp trên 1 chiều: k×cạnh + (k−1)×khe ≤ usable ⟺ k ≤ (usable+khe)/(cạnh+khe). >= 0."""
    buoc = canh + khe
    if buoc <= 0 or usable <= 0:
        return 0
    return max(floor((usable + khe) / buoc), 0)


def chua_theo_chieu(tp: dict) -> tuple[float, float]:
    """Chừa của một thành phần → (chừa chiều DÀI, chừa chiều RỘNG), mm.

    NGUỒN LÀ DANH MỤC MÁY. Chừa tờ in là đặc tính của máy in, không phải của bài — khai một lần ở
    máy thì mọi phiếu chọn máy đó ăn theo:
      · DÀI  ← nhíp GIẤY (1 đầu, cạnh nạp) + đuôi/thanh màu (`nhip_giay_mm` + `duoi_thang_mau_mm`).
      · RỘNG ← lề hông ×2 (`le_hong_mm`, trừ mỗi bên).

    KHÔNG gộp một số trừ đều hai chiều — nhíp là mép máy kẹp ở CẠNH NẠP, không ăn chiều rộng.
    `gripper_mm` là nhíp KẼM (~44mm), KHÔNG được dùng ở đây: dùng nhầm là hụt 14-19% số con.

    Đè duy nhất còn lại: `chua_nhip` trên phiếu — khoản đổi theo job (hướng bài, cạnh nạp). Lề hông
    · đuôi · xén · cả gáy đã bỏ khỏi phiếu (mig 0139): chúng chưa từng có chỗ nhập, mà xén/gáy còn
    bị cộng đều cả hai chiều nên chỉ làm số con sai lệch âm thầm.

    ĐÂY LÀ BẢN DUY NHẤT của phép cộng này. Màn lệnh sản xuất từng tự cộng năm khoản thành một số
    rồi trừ đều hai chiều nên vẽ sơ đồ ra 105 con trong khi phiếu tính giá ra 99 — cùng một tờ,
    hai hình khác nhau.
    """
    nhip = _f(tp.get("chua_nhip")) or _f(tp.get("nhip_giay_mm"))
    duoi = _f(tp.get("duoi_thang_mau_mm"))
    le_hong = _f(tp.get("le_hong_mm"))
    return nhip + duoi, le_hong * 2


def binh_bai_layout(*, kho_in_dai: float, kho_in_rong: float, dai_tp: float, rong_tp: float,
                    chua_mm: float = 0.0, chua_dai_mm: float | None = None,
                    chua_rong_mm: float | None = None,
                    bleed_mm: float = 0.0, khe_cat_mm: float = 0.0) -> dict:
    """Bình bài ③ lên ② (trừ chừa) — trả LAYOUT đầy đủ để FE vẽ sơ đồ ĐÚNG engine.

    CHỪA TÁCH THEO CHIỀU: `chua_dai_mm` (nhíp giấy + đuôi/thanh màu — cạnh nạp, ăn chiều DÀI) và
    `chua_rong_mm` (lề hông 2 bên — ăn chiều RỘNG). Bỏ trống CẢ HAI thì lùi về `chua_mm` trừ đều
    mỗi chiều như bản cũ — caller cũ giữ nguyên hành vi.

    Con để bình = ③ + 2×`bleed_mm` mỗi chiều (tràn lề); giữa 2 con kề nhau chừa `khe_cat_mm`
    (n con chỉ có n−1 khe, không phải n).

    Trả {con, cols, rows, rotated, usable_dai, usable_rong, chua_dai, chua_rong, piece_dai,
    piece_rong, kho_in_dai, kho_in_rong, dai_tp, rong_tp}. cols = theo chiều RỘNG, rows = chiều DÀI.
    """
    chua_d = _f(chua_mm) if chua_dai_mm is None else _f(chua_dai_mm)
    chua_r = _f(chua_mm) if chua_rong_mm is None else _f(chua_rong_mm)
    bleed, khe = max(_f(bleed_mm), 0.0), max(_f(khe_cat_mm), 0.0)
    piece_d = dai_tp + 2 * bleed if dai_tp > 0 else dai_tp
    piece_r = rong_tp + 2 * bleed if rong_tp > 0 else rong_tp
    usable_d = max(kho_in_dai - chua_d, 0.0)
    usable_r = max(kho_in_rong - chua_r, 0.0)
    base = {"kho_in_dai": kho_in_dai, "kho_in_rong": kho_in_rong,
            "dai_tp": dai_tp, "rong_tp": rong_tp,
            "usable_dai": usable_d, "usable_rong": usable_r,
            "chua_dai": chua_d, "chua_rong": chua_r,
            "piece_dai": piece_d, "piece_rong": piece_r}
    if piece_d <= 0 or piece_r <= 0 or usable_d <= 0 or usable_r <= 0:
        return {**base, "con": 0, "cols": 0, "rows": 0, "rotated": False}
    s_rows = _suc_chua(usable_d, piece_d, khe)      # thẳng
    s_cols = _suc_chua(usable_r, piece_r, khe)
    r_rows = _suc_chua(usable_d, piece_r, khe)      # xoay 90°
    r_cols = _suc_chua(usable_r, piece_d, khe)
    if r_rows * r_cols > s_rows * s_cols:
        rows, cols, rot = r_rows, r_cols, True
    else:
        rows, cols, rot = s_rows, s_cols, False
    con = rows * cols
    if con == 0:                      # không vừa → không vẽ lưới lệch (1 chiều lọt vẫn = 0 con)
        rows = cols = 0
    return {**base, "con": con, "cols": cols, "rows": rows, "rotated": rot}


def binh_bai_con(*, kho_in_dai: float, kho_in_rong: float, dai_tp: float, rong_tp: float,
                 chua_mm: float = 0.0, chua_dai_mm: float | None = None,
                 chua_rong_mm: float | None = None,
                 bleed_mm: float = 0.0, khe_cat_mm: float = 0.0) -> int:
    """Số con/tờ in (chỉ số) — bọc `binh_bai_layout`. mm. >= 0."""
    return binh_bai_layout(kho_in_dai=kho_in_dai, kho_in_rong=kho_in_rong,
                           dai_tp=dai_tp, rong_tp=rong_tp, chua_mm=chua_mm,
                           chua_dai_mm=chua_dai_mm, chua_rong_mm=chua_rong_mm,
                           bleed_mm=bleed_mm, khe_cat_mm=khe_cat_mm)["con"]


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
    # Số TRANG nội dung của 1 sản phẩm + số trang mỗi tay gấp — người dùng khai, engine LƯU.
    # Số tờ in đi thẳng từ đây (`sl × so_trang / con`), không qua "số bài in" nữa: chia số TAY cho
    # số CON là chia hai đại lượng khác đơn vị, sách bình tay vì thế ra sai.
    so_trang = max(_i(tp.get("so_trang"), 1), 1)
    trang_moi_tay = max(_i(tp.get("trang_moi_tay"), 1), 1)
    # Số TAY = số bài in (khuôn) — DẪN XUẤT, mỗi tay 1 bộ kẽm. Sách 160 trang tay 16 → 10 tay.
    # Tờ rời 1/1 → 1 tay, y như trước.
    so_tay = max(ceil(so_trang / trang_moi_tay), 1)
    so_to_per_sp = so_tay
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
    chua_dai, chua_rong = chua_theo_chieu(tp)
    bleed = _f(tp.get("bleed_mm"))
    khe_cat = _f(tp.get("khe_cat_mm"))

    # --- ④ con/tờ: auto bình bài, override được ---
    con_auto = tp.get("con_auto", True)
    con = 0
    if con_auto and dai_tp > 0 and rong_tp > 0 and kho_in_d > 0 and kho_in_r > 0:
        lay = binh_bai_layout(kho_in_dai=kho_in_d, kho_in_rong=kho_in_r,
                              dai_tp=dai_tp, rong_tp=rong_tp,
                              chua_dai_mm=chua_dai, chua_rong_mm=chua_rong,
                              bleed_mm=bleed, khe_cat_mm=khe_cat)
        con = lay["con"]
        # Bài (phần đặt con, chưa kể chừa) phải lọt VÙNG IN máy — chỉ nhắc, KHÔNG chặn/tự sửa.
        vung_d, vung_r = _f(tp.get("vung_in_dai")), _f(tp.get("vung_in_rong"))
        if con > 0 and vung_d > 0 and vung_r > 0:
            bai_d = lay["rows"] * (lay["piece_rong"] if lay["rotated"] else lay["piece_dai"])
            bai_r = lay["cols"] * (lay["piece_dai"] if lay["rotated"] else lay["piece_rong"])
            bai_d += max(lay["rows"] - 1, 0) * khe_cat
            bai_r += max(lay["cols"] - 1, 0) * khe_cat
            if bai_d > vung_d + 1e-6 or bai_r > vung_r + 1e-6:
                warnings.append(
                    f"Thành phần '{name}': bài bình {bai_d:g}×{bai_r:g} vượt vùng in máy "
                    f"{vung_d:g}×{vung_r:g} — máy không in hết bài."
                )
        if con < 1:
            warnings.append(f"Thành phần '{name}': khổ thành phẩm lớn hơn khổ tờ in — bình bài = 0, tạm 1 con/tờ.")
            con = 1
    if con < 1:
        con = max(_i(tp.get("so_con"), 1), 1)   # fallback: nhập tay

    # --- Số mảnh xả (② lên ①): cắt tờ giấy CHẠY MÁY (kho_may) từ giấy nguyên, KHÔNG dùng vùng in ---
    xa = _fit(kho_ng_d, kho_ng_r, kho_may_d, kho_may_r) if (kho_ng_d > 0 and kho_ng_r > 0) else 1
    xa = max(xa, 1)

    # --- Số tờ CẦN in (net) — tính TRƯỚC để tra bù hao THEO SỐ TỜ (không phải số lượng) ---
    # HAI KIỂU LÀM khác hẳn nhau, `trang_moi_tay` là thứ phân biệt (không cần thêm cờ nào):
    #  · GẤP TAY (sách, trang mỗi tay > 1): tờ in gấp NGUYÊN VẸN thành một tay → 1 tờ = 1 tay, một
    #    cuốn cần `so_tay` tờ. Tờ không bị cắt rời nên `con` KHÔNG vào công thức — nó chỉ để vẽ sơ
    #    đồ bình bài và kiểm khổ có vừa tờ. Bật/tắt `con_auto` vì thế không làm sai số giấy.
    #  · CẮT RỜI (tờ rơi, danh thiếp, hộp): một tờ cắt ra `con` cái.
    # `cai_moi_to` dùng lại làm HỆ SỐ quy đổi tờ↔cái cho chuỗi bù hao ngược ở dưới — một nguồn duy
    # nhất, khỏi hai chỗ tính lệch nhau.
    cai_moi_to = (1.0 / so_tay) if trang_moi_tay > 1 else float(con)
    to_net = ceil(sl / cai_moi_to) if sl > 0 and cai_moi_to > 0 else 0

    # --- Bù hao NGƯỢC theo công đoạn: đi từ CUỐI chuỗi lên, mỗi bước tra bậc theo số đi qua CHÍNH
    # NÓ, ở ĐÚNG đơn vị của nó (bước in rơi bậc cao hơn bước xén cuối — cộng xuôi phẳng theo
    # `to_net` thì mọi bước tra cùng một bậc). LUÔN tính: cột `tinh_bu_hao_cd` không còn được đọc,
    # tắt bù hao tự là mở đường cho báo giá hụt giấy mà không ai biết. Muốn cộng thêm thì có ô
    # "+ Bù thêm"; muốn bớt thì đi sửa định mức của công đoạn. ---
    chain = tp.get("thanh_phams") or []
    # Bước ở trên DÒNG GIẤY = bước có KHAI đơn vị. Chế bản để trống đơn vị (nó nhả kẽm, không nhả
    # tờ) nên tự rơi ra khỏi đây — không cần luật riêng theo `nhom`.
    idx_giay = [i for i, r in enumerate(chain)
                if (r.get("cong_doan") or {}).get("don_vi_vao")
                and (r.get("cong_doan") or {}).get("don_vi_ra")]
    # Bước KHÔNG PHẢI chế bản mà bỏ trống đơn vị = nhiều khả năng quên khai. Nó rơi thẳng ra khỏi
    # dòng giấy nên bù hao của nó biến mất KHÔNG kèn không trống — phải kêu, đừng để số 0 im lặng.
    for i, r in enumerate(chain):
        cd = r.get("cong_doan") or {}
        if i not in idx_giay and cd.get("nhom") != "prepress":
            warnings.append(
                f"Thành phần '{name}': công đoạn '{r.get('ten') or cd.get('ten') or '?'}' chưa khai "
                f"đơn vị vào/ra — không được tính vào dòng giấy (bù hao của nó bỏ qua)."
            )
    # Đơn vị vào/ra KHAI ở danh mục công đoạn. HỆ SỐ thì phiếu cấp — `con` (bình bài) và `xa`
    # (số mảnh xả) đã tính ở trên, khai lại vào danh mục là đẻ nguồn sự thật thứ hai.
    # Ranh giới tờ in → cái: cắt rời thì 1 tờ ra `con` cái; GẤP TAY thì ngược chiều — phải gom
    # `so_tay` tờ mới ra 1 cuốn (hệ số 1/so_tay). Không có nó, chuỗi ngược chạy 1:1 và mỗi cuốn
    # hỏng ở bước xén chỉ đòi bù 1 tờ thay vì `so_tay` tờ.
    he_so_dv = {(DV_TO, DV_CAI): cai_moi_to, (DV_TO_NGUYEN, DV_TO): float(xa)}
    buoc_in = []
    for i in idx_giay:
        cd = chain[i].get("cong_doan") or {}
        buoc_in.append({
            "cd": cd,
            "ten": chain[i].get("ten") or cd.get("ten") or "Công đoạn",
            "dv_vao": cd.get("don_vi_vao"),
            "dv_ra": cd.get("don_vi_ra"),
        })
    # Chuỗi bắt đầu ở ĐƠN VỊ RA của bước cuối: routing có bế/xén thì đích là SỐ KHÁCH ĐẶT (con),
    # không có thì đích là số tờ in cần. Đây là chỗ "đi ngược từ 5.000 đổ lại" thành thật.
    dv_cuoi = buoc_in[-1]["dv_ra"] if buoc_in else DV_TO
    to_can = float(sl) if dv_cuoi == DV_CAI else float(to_net)
    buoc_giay, canh_bao_dv = chuoi_nguoc_dv(
        buoc_in, rows=bu_hao_rows, to_can=to_can, he_so=he_so_dv)
    for _c in canh_bao_dv:
        warnings.append(f"Thành phần '{name}': {_c}")

    # --- Số tờ: đọc RA KHỎI CHUỖI tại đúng ranh giới đơn vị, không tính riêng bên ngoài ---
    bu_hao = _i(tp.get("bu_hao_so_to"))         # "+ Bù thêm" — ô nhập tay DUY NHẤT còn lại

    def _vao_tai(dv: str) -> float | None:
        """Số lượng VÀO của bước đầu tiên ăn đơn vị `dv` — chính là mốc cần ở ranh giới đó."""
        return next((b["vao"] for b in buoc_giay if b["dv_vao"] == dv), None)

    to_can_vao = _vao_tai(DV_TO)
    if to_can_vao is None:      # chuỗi rỗng, hoặc toàn bước không chạm tờ in
        to_can_vao = float(to_net)
    finishing_spoilage_sum = ceil(to_can_vao) - to_net       # Σ bù hao công đoạn (hiện trên panel)
    # Bù thêm tay là tờ nạp ở đầu chuỗi → chảy qua MỌI bước, cộng vào cả vào lẫn ra.
    if bu_hao:
        for b in buoc_giay:
            b["vao"] += bu_hao
            b["ra"] += bu_hao
    to_dau_vao = ceil(to_can_vao) + bu_hao
    # Chuỗi CÓ bước xả giấy → tờ nguyên đọc thẳng từ bước đó; không có thì quy đổi ở đây như cũ.
    _vao_nguyen = _vao_tai(DV_TO_NGUYEN)
    if _vao_nguyen is not None:
        to_nguyen = ceil(_vao_nguyen)
    else:
        to_nguyen = ceil(to_dau_vao / xa) if to_dau_vao > 0 else 0
    # Tờ TỐT còn lại sau in = `ra` của bước IN (bước in cuối nếu chuỗi có nhiều) — nuôi công thức
    # tiền của công đoạn sau in. Chuỗi không có bước in → giữ nguyên tờ vào máy (tương thích cũ).
    to_sau_in = float(to_dau_vao)
    for _i_row, _b in zip(idx_giay, buoc_giay):
        if (chain[_i_row].get("cong_doan") or {}).get("nhom") == "print":
            to_sau_in = float(ceil(_b["ra"]))
    # Phân rã từng bước cho UI: bước nào ăn bao nhiêu tờ. Chế bản KHÔNG có mặt (không chạm tờ).
    buoc = {i: b for i, b in zip(idx_giay, buoc_giay)}   # tra theo chỉ số dòng GỐC
    bu_hao_chi_tiet = [
        {
            "ten": (chain[i].get("ten") or (chain[i].get("cong_doan") or {}).get("ten")
                    or "Công đoạn"),
            "nhom": (chain[i].get("cong_doan") or {}).get("nhom"),   # UI neo "Tờ sau in" vào bước in
            "dv_vao": b["dv_vao"], "dv_ra": b["dv_ra"],   # UI hiện chỗ ĐỔI đơn vị
            "vao": ceil(b["vao"]),
            "ra": ceil(b["ra"]),
            # `ra` QUY về đơn vị vào + hệ số đã dùng. Không có hai số này thì dòng đổi đơn vị đọc
            # lên vô lý: "55 tờ in → 5.070 con" mà 55 × 210 = 11.550, người xem không kiểm được.
            # Ràng buộc: ra_quy + hao == vao (đúng theo cách `hao` tính ngay dưới).
            "ra_quy": ceil(b["ra"] / (he_so_dv.get((b["dv_vao"], b["dv_ra"])) or 1.0)),
            "he_so": he_so_dv.get((b["dv_vao"], b["dv_ra"])) or 1.0,
            # Hao đo bằng ĐƠN VỊ VÀO: bước bế vào 74 tờ ra 15.540 con thì hao là 50 TỜ, không phải
            # hiệu hai con số khác đơn vị.
            "hao": ceil(b["vao"]) - ceil(b["ra"] / (he_so_dv.get((b["dv_vao"], b["dv_ra"])) or 1.0)),
        }
        for i, b in zip(idx_giay, buoc_giay)
    ]
    # Khép mạch về ĐƠN VỊ KHÁCH ĐẶT: tờ ra khỏi bước cuối × con/tờ = số thành phẩm thật sự có.
    # Không có dòng này thì panel nhảy thẳng từ "5.000 cái" sang "24 tờ" mà giấu chỗ quy đổi.
    # Chuỗi KẾT THÚC Ở CON (có bước bế/xén) thì `to_ra_cuoi` đã là con — nhân `con` lần nữa là
    # đếm hai lần. Chỉ quy đổi khi bước cuối còn đang đếm tờ in.
    to_ra_cuoi = ceil(buoc_giay[-1]["ra"]) if buoc_giay else to_dau_vao
    if dv_cuoi == DV_CAI:
        so_tp_ra = to_ra_cuoi          # chuỗi đã kết thúc Ở THÀNH PHẨM — không quy đổi thêm lần nữa
    else:
        so_tp_ra = floor(to_ra_cuoi * cai_moi_to)   # còn đang đếm tờ in → × số cái mỗi tờ

    so_mau_a = _i(tp.get("so_mau_a"))     # màu PROCESS mặt A (CMYK…)
    so_mau_b = _i(tp.get("so_mau_b"))     # màu PROCESS mặt B
    # Màu pha (Pantone) CỘNG THÊM — mỗi màu mực chạy 1 đơn vị máy là 1 bản kẽm, màu pha cũng vậy.
    # 4 màu CMYK + 1 Pantone = 5 kẽm. Ô "Số màu mặt A/B" là màu process, KHÔNG gồm màu pha.
    so_mau_pha = max(_i(tp.get("so_mau_pha")), 0)
    so_mau = so_mau_a + so_mau_b + so_mau_pha
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
    kem_mau += so_mau_pha        # màu pha = mực riêng, chạy đơn vị riêng → bản kẽm riêng
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
        "so_mau_pha": so_mau_pha,
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

    # Chuỗi công đoạn là NGUỒN DUY NHẤT: In / Chế bản phải nằm trong routing như mọi công đoạn
    # khác. KHÔNG tự đẻ dòng thay thế khi chuỗi thiếu — chỉ NHẮC để người dùng tự thêm.
    chain_nhoms = {((r.get("cong_doan") or {}).get("nhom")) for r in (tp.get("thanh_phams") or [])}
    if co_in and "print" not in chain_nhoms:
        warnings.append(f"Thành phần '{name}': chuỗi chưa có công đoạn IN — chưa tính tiền in.")
    if co_in and so_kem > 0 and "prepress" not in chain_nhoms:
        warnings.append(f"Thành phần '{name}': chuỗi chưa có công đoạn CHẾ BẢN/KẼM — chưa tính tiền kẽm.")

    # --- Công đoạn trong chuỗi (chế bản/in/gia công) theo thứ tự routing ---
    ctx_base = {
        "so_to_in_gross": to_net,
        "so_luong_thanh_pham": sl,
        "dt_to_in_cm2": (kho_in_d / 10.0) * (kho_in_r / 10.0),
        "so_con": con,
        "size_cm": max(dai_tp, rong_tp) / 10.0,
        "so_trang": 0, "so_cuon": 0, "so_bao": 0, "so_thung": 0,
    }

    for idx_buoc, row in enumerate(chain):
        cd = row.get("cong_doan") or {}
        ten_r = row.get("ten") or cd.get("ten") or "Công đoạn"
        row_sl = _i(row.get("so_luong"))
        don_gia_r = _f(row.get("don_gia"))
        basis = cd.get("pricing_basis") if cd else None

        ctx = dict(ctx_base)
        # Số tờ ĐI QUA chính bước này (từ chuỗi ngược) — công thức của công đoạn dùng biến này
        # là tính tiền trên đúng lượng tờ nó chạm, thay vì một con số chung cho cả chuỗi.
        # Bước chế bản không nằm trong dòng giấy → rơi về tờ vào máy (kẽm phục vụ cả lượt in).
        ctx["to_qua_buoc"] = ceil(buoc[idx_buoc]["vao"]) if idx_buoc in buoc else to_dau_vao
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
            "bu_hao_auto": _r(finishing_spoilage_sum),   # Σ bù hao công đoạn (chuỗi ngược)
            "bu_hao_chi_tiet": bu_hao_chi_tiet,          # phân rã: bước nào ăn bao nhiêu tờ
            "so_trang": so_trang, "trang_moi_tay": trang_moi_tay,   # người dùng khai
            "so_to_per_sp": so_to_per_sp,                # số bài in — DẪN XUẤT: so_trang / trang_moi_tay
            "to_ra_cuoi": to_ra_cuoi, "so_tp_ra": so_tp_ra,  # khép mạch tờ → thành phẩm
            "bu_hao_tay": bu_hao, "hao_tay": 0,          # ô "− Hao" đã bỏ → luôn 0
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
