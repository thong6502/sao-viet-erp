"""Routing engine — hàm THUẦN cho chuỗi công đoạn, spec `docs/spec-cong-doan.md` §4–§5.

Không I/O, không ORM: nhận dict/list cấu hình → trả số. Engine tính giá (Phase D) gọi các hàm
này cho từng component. 4 việc: cascade hao NGƯỢC (§4.2) · quy đổi basis_qty (§4.3) · tiền 1
bước (§4.1) · dòng kẽm (§5.1).
"""
from __future__ import annotations

from decimal import Decimal
from math import ceil


def _f(v, d: float = 0.0) -> float:
    if v is None:
        return d
    return float(v) if isinstance(v, Decimal) else float(v)


# --- §4.3 quy đổi số lượng hình học → basis_qty (dùng SL GROSS) ---
def basis_qty(pricing_basis: str, ctx: dict) -> float:
    """Quy đổi 1 đơn vị tính giá công đoạn → số lượng tính tiền, từ ctx job.

    ctx: {
      so_to_in_gross,        # số tờ in (gross, đã cộng bù hao)
      so_mat,                # số mặt in (mặc định 1)
      dt_to_in_cm2,          # diện tích 1 tờ in (cm²)
      dt_thanh_pham_cm2,     # diện tích 1 thành phẩm (cm²)
      so_luong_thanh_pham,   # SL thành phẩm (đơn đặt)
      so_trang,              # số trang sách
      so_cuon,               # số cuốn
      so_vi_tri,             # số vị trí (ép kim/bế… mỗi thành phẩm)
      so_bao, so_thung,      # số bao / số thùng theo quy cách đóng gói
    }
    """
    g = _f(ctx.get("so_to_in_gross"))
    sl = _f(ctx.get("so_luong_thanh_pham"))
    trang = _f(ctx.get("so_trang"))
    cuon = _f(ctx.get("so_cuon"))
    dt_to = _f(ctx.get("dt_to_in_cm2"))
    if pricing_basis == "per_sheet":                    # Theo số tờ in
        return g
    if pricing_basis == "per_finished_area":            # Theo diện tích thành phẩm (cm²)
        return _f(ctx.get("dt_thanh_pham_cm2")) * sl
    if pricing_basis == "per_finished_qty":             # Theo số lượng thành phẩm
        return sl
    if pricing_basis == "per_book_page":                # Theo số trang sách
        return trang * cuon
    if pricing_basis == "per_position":                 # Theo số vị trí
        return _f(ctx.get("so_vi_tri")) * sl
    if pricing_basis == "per_bag":                      # Theo bao
        return _f(ctx.get("so_bao"))
    if pricing_basis == "per_carton":                   # Theo thùng
        return _f(ctx.get("so_thung"))
    if pricing_basis == "per_area_sides":               # Theo diện tích (cm²) và số mặt
        return dt_to * _f(ctx.get("so_mat"), 1) * g
    if pricing_basis == "per_sheet_area":               # Theo diện tích tờ in (cm²)
        return dt_to * g
    if pricing_basis == "per_book_page_q4":             # Theo số trang sách chia 4
        return (trang * cuon) / 4.0
    if pricing_basis == "per_job":                      # Trọn gói một lần (cả đơn) — 1 lần cho đơn
        return 1.0
    if pricing_basis == "per_other":                    # Khác (nhập tay, giá phẳng)
        return 1.0
    raise ValueError(f"pricing_basis không hợp lệ: {pricing_basis}")


# --- Bậc đơn giá theo KÍCH THƯỚC (cạnh dài thành phẩm, cm) ---
def pick_size_rate(size_tiers: list | None, size_cm: float) -> float:
    """Chọn đơn giá theo cỡ. `size_tiers` = [{den_cm, don_gia}] nghĩa "≤ den_cm → don_gia".

    Sắp xếp tăng theo `den_cm` (den_cm None/0 = bậc cuối "trên các mức"). Trả đơn giá của bậc ĐẦU
    có `size_cm ≤ den_cm`; vượt hết → bậc cuối (đơn giá cao nhất). Rỗng → 0. size_cm ≤ 0 (chưa biết
    cỡ) → bậc đầu (nhỏ nhất) làm sàn.
    """
    tiers = [t for t in (size_tiers or []) if isinstance(t, dict)]
    if not tiers:
        return 0.0

    def cap(t) -> float:
        v = _f(t.get("den_cm"))
        return v if v > 0 else float("inf")

    tiers = sorted(tiers, key=cap)
    s = _f(size_cm)
    if s <= 0:
        return _f(tiers[0].get("don_gia"))
    for t in tiers:
        if s <= cap(t):
            return _f(t.get("don_gia"))
    return _f(tiers[-1].get("don_gia"))


# --- §5.2 bậc thang rate_tiers ---
def apply_tiers(run_rate, basis: float, tiers: list | None, first_unit_floor=None) -> float:
    """rate_tier = {from_qty, rate, kieu(marginal|cumulative), driver}. Không tiers → run_rate×basis."""
    if not tiers:
        cost = _f(run_rate) * basis
    else:
        ts = sorted(tiers, key=lambda t: _f(t.get("from_qty")))
        # cumulative: rate của bậc chứa `basis` áp cho TOÀN bộ. marginal: cộng từng khoảng.
        if ts[0].get("kieu") == "cumulative":
            rate = _f(ts[0].get("rate"), _f(run_rate))
            for t in ts:
                if basis >= _f(t.get("from_qty")):
                    rate = _f(t.get("rate"))
            cost = rate * basis
        else:  # marginal
            cost = 0.0
            for i, t in enumerate(ts):
                lo = _f(t.get("from_qty"))
                hi = _f(ts[i + 1].get("from_qty")) if i + 1 < len(ts) else float("inf")
                if basis <= lo:
                    break
                seg = min(basis, hi) - lo
                cost += seg * _f(t.get("rate"))
    if first_unit_floor is not None:
        cost = max(cost, _f(first_unit_floor))
    return cost


# --- §4.1 tiền 1 công đoạn ---
def compute_step_cost(cd: dict, ctx: dict, *,
                      reuse_tooling: bool = False, tooling_one_time: float = 0.0) -> dict:
    """cd = cấu hình công đoạn (pricing_basis, setup_*, run_rate, rate_tiers,
    first_unit_floor, min_charge). ctx = ngữ cảnh SL (§4.3). Công đoạn tính theo công thức/sản lượng."""
    rate_used: float | None = None  # đơn giá đơn vị thực dùng (cho diễn giải phiếu)
    basis_used: float | None = None  # số lượng tính tiền (cho diễn giải phiếu)
    if not cd.get("pricing_basis"):
        raise ValueError("theo_san_luong cần pricing_basis. [E-CD-BASIS]")
    b = basis_qty(cd["pricing_basis"], ctx)
    basis_used = b
    size_tiers = cd.get("size_tiers")
    if size_tiers:
        # Bậc theo KÍCH THƯỚC: đơn giá chọn theo cạnh dài thành phẩm (ctx["size_cm"]), thay run_rate.
        rate_used = pick_size_rate(size_tiers, _f(ctx.get("size_cm")))
        run_cost = apply_tiers(rate_used, b, None, cd.get("first_unit_floor"))
    else:
        rate_used = _f(cd.get("run_rate"))
        run_cost = apply_tiers(cd.get("run_rate"), b, cd.get("rate_tiers"), cd.get("first_unit_floor"))

    tooling_cost = 0.0 if reuse_tooling else _f(tooling_one_time)
    total = _f(cd.get("setup_cost")) + run_cost + tooling_cost
    if cd.get("min_charge") is not None:
        total = max(total, _f(cd["min_charge"]))
    return {"setup_cost": round(_f(cd.get("setup_cost")), 2), "run_cost": round(run_cost, 2),
            "tooling_cost": round(tooling_cost, 2), "total": round(total, 2),
            "rate_used": round(_f(rate_used), 4) if rate_used is not None else None,
            "basis_qty": round(_f(basis_used), 3) if basis_used is not None else None}


# --- §4.2 lan truyền hao NGƯỢC (bước cuối → đầu) ---
def cascade_waste_backward(steps: list[dict], so_luong_final: float) -> list[dict]:
    """steps theo THỨ TỰ chạy (đầu→cuối). Trả bản sao có output_qty/input_qty.
       output(cuối)=so_luong; input(i)=output(i)/(1−spoilage_i); output(i−1)=input(i).
       Bước in (nhom=print): spoilage ép 0 (bù hao lấy từ máy — §4.4).
    """
    out = [dict(s) for s in steps]
    downstream_output = float(so_luong_final)
    for s in reversed(out):
        sp = 0.0 if s.get("nhom") == "print" else _f(s.get("spoilage_pct")) / 100.0
        sp = min(max(sp, 0.0), 0.95)
        s["output_qty"] = round(downstream_output, 3)
        s["input_qty"] = round(downstream_output / (1.0 - sp), 3)
        downstream_output = s["input_qty"]
    return out


# --- §5.1 dòng kẽm (kem_line) ---
def compute_kem_line(*, so_forms: int, so_kem_truoc: int, so_kem_sau: int,
                     tu_tro: bool, don_gia_kem: float, is_digital: bool = False) -> dict:
    """so_kem = so_forms × (tự_trở ? max(2 mặt) : trước+sau). digital → 0 (in click, không bản).
       so_kem_mặt = số màu process + số màu pha mặt đó (tính ở caller)."""
    if is_digital:
        return {"so_kem": 0, "tien_kem": 0.0}
    per_form = max(so_kem_truoc, so_kem_sau) if tu_tro else (so_kem_truoc + so_kem_sau)
    so_kem = int(so_forms) * int(per_form)
    return {"so_kem": so_kem, "tien_kem": round(so_kem * _f(don_gia_kem), 2)}


def so_to_in_gross(so_to_in_net: float, *, so_mau: int, bu_hao_canh_may_per_mau: float,
                   bu_hao_chay_pct: float) -> float:
    """§4.4/spec-tinh-gia ③: tờ in gross = net + canh máy(theo số màu) + %chạy. Bù hao chỉ từ MÁY."""
    canh_may = _f(bu_hao_canh_may_per_mau) * max(int(so_mau), 1)
    return ceil((_f(so_to_in_net) + canh_may) * (1.0 + _f(bu_hao_chay_pct) / 100.0))
