"""Máy soi "ĐẶC THÙ cần Giám đốc duyệt" — logic THUẦN, dùng CHUNG cho Đơn hàng (A2) và Báo giá (BG-2).

MỘT nguồn định nghĩa (chống trôi lệch giữa 2 nơi — phản biện kiến trúc):
- 3 điều kiện: **giá trị cao** (subtotal trước VAT ≥ ngưỡng) · **biên thấp** (0 ≤ biên < ngưỡng) ·
  **bán dưới giá vốn** (biên < 0). Riêng BÁO GIÁ (`evaluate_quote`) soi trục **MARKUP** (trên giá vốn)
  theo rào của từng khách, KHÔNG dùng biên — xem docstring hàm đó.
- Cơ chế **"bao phủ"**: bản GĐ-duyệt còn hiệu lực nếu tình trạng hiện tại KHÔNG rủi ro hơn mức đã ký
  (tổng ≤ tổng-đã-ký AND biên ≥ biên-đã-ký, nhân chéo số nguyên).

KHÔNG chạm DB/ORM — mỗi service tự bơm số vào: `subtotal` (TRƯỚC VAT, base biên) · `total_gross`
(GỒM VAT, mốc quy mô) · `cost` (giá vốn, None = không soi được biên). Ngưỡng ghim vào bản duyệt để audit.
"""
from __future__ import annotations

from ..models.order import (
    APPROVAL_DECISION_APPROVED as DECISION_APPROVED,
    APPROVAL_DECISION_REJECTED as DECISION_REJECTED,
    EXC_BELOW_COST,
    EXC_DISCOUNT_OUT,
    EXC_HIGH_VALUE,
    EXC_LOW_MARGIN,
    EXC_MARKUP_OUT,
)

DECISIONS = (DECISION_APPROVED, DECISION_REJECTED)

# Ngưỡng mặc định (cấu hình versioned sau) — dùng CHUNG order + quote (cùng một giá trị đơn).
DEFAULT_MIN_MARGIN_PCT = 15                       # 0 ≤ biên < 15% → "biên thấp"
DEFAULT_HIGH_VALUE_THRESHOLD = 1_000_000_000      # subtotal (trước VAT) ≥ 1 tỷ → "giá trị cao" (SVN chốt)

_LABELS = {
    EXC_HIGH_VALUE: "Giá trị đơn cao",
    EXC_LOW_MARGIN: "Biên lợi nhuận thấp",
    EXC_BELOW_COST: "Bán dưới giá vốn",
    EXC_DISCOUNT_OUT: "Chiết khấu ngoài mức cho phép của khách",
    EXC_MARKUP_OUT: "Markup ngoài mức cho phép của khách",
}


def evaluate(
    *, subtotal, total_gross, cost,
    min_margin_pct: int = DEFAULT_MIN_MARGIN_PCT,
    high_value_threshold: int = DEFAULT_HIGH_VALUE_THRESHOLD,
) -> dict:
    """Soi 3 điều kiện đặc thù. `high_value` soi trên subtotal TRƯỚC VAT (thuế suất không làm cùng giá
    trị thật kích khác nhau). Biên phân loại bằng phép so KHÔNG chia (chính xác). Trả dict số + `triggers`
    [{key,label}] + `margin_pct` (hiển thị, có thể âm)."""
    triggers: list[dict] = []
    if subtotal > 0 and subtotal >= high_value_threshold:
        triggers.append({"key": EXC_HIGH_VALUE, "label": _LABELS[EXC_HIGH_VALUE]})

    margin_pct = None
    if cost is not None and subtotal > 0:
        margin_pct = round((subtotal - cost) * 100 / subtotal)
        if cost > subtotal:
            triggers.append({"key": EXC_BELOW_COST, "label": _LABELS[EXC_BELOW_COST]})
        elif (subtotal - cost) * 100 < min_margin_pct * subtotal:
            triggers.append({"key": EXC_LOW_MARGIN, "label": _LABELS[EXC_LOW_MARGIN]})

    return {
        "subtotal": subtotal,
        "total_gross": total_gross,
        "cost": cost,
        "margin_pct": margin_pct,
        "min_margin_pct": min_margin_pct,
        "high_value_threshold": high_value_threshold,
        "triggers": triggers,
    }


def evaluate_quote(
    *, subtotal, total_gross, cost,
    discount_amount: float = 0.0,
    subtotal_gross: float = 0.0,
    discount_min_pct: float | None = None,
    discount_max_pct: float | None = None,
    markup_min_pct: float | None = None,
    markup_max_pct: float | None = None,
    high_value_threshold: int = DEFAULT_HIGH_VALUE_THRESHOLD,
) -> dict:
    """Cổng đặc thù cho **BÁO GIÁ** — rào theo TỪNG KHÁCH HÀNG (Đơn hàng vẫn dùng `evaluate` ngưỡng chung).

    Trục lợi nhuận ở đây là **MARKUP** (lợi nhuận / GIÁ VỐN) — CÙNG con số Sale gõ ở ô "Markup %"
    trên màn Báo giá, KHÔNG phải biên (lợi nhuận / giá bán). Hai số này khác mẫu: markup 10% ⇔
    biên 9,1%; soi bằng biên thì Sale gõ đúng rào vẫn bị bắt trình duyệt (chủ đầu tư chốt 29/08/2026).

    Trigger (dính bất kỳ → gửi duyệt):
    - **Giá trị cao** (subtotal TRƯỚC VAT ≥ ngưỡng) và **Bán dưới vốn**: LUÔN áp (chung, không đổi).
    - **Chiết khấu NGOÀI khoảng [min,max] của KH** (dưới min HOẶC vượt max).
    - **Markup NGOÀI khoảng [min,max] của KH** (dưới min HOẶC vượt max).
    Rào nào KH để None → KHÔNG soi chiều đó (chỉ chặn phía đã đặt). So sánh nhân chéo (không chia).

    `subtotal` = NET (sau CK, trước VAT); `subtotal_gross` = tổng giá bán TRƯỚC CK (base %CK);
    `discount_amount` = tổng chiết khấu; `total_gross` = gồm VAT (mốc quy mô); `cost` = giá vốn
    (base markup — cost ≤ 0 thì KHÔNG soi được markup, bỏ qua cổng đó)."""
    triggers: list[dict] = []
    if subtotal > 0 and subtotal >= high_value_threshold:
        triggers.append({"key": EXC_HIGH_VALUE, "label": _LABELS[EXC_HIGH_VALUE]})

    markup_pct = None
    if cost is not None and subtotal > 0:
        profit = subtotal - cost
        if cost > 0:
            markup_pct = round(profit * 100 / cost)                      # % TRÊN GIÁ VỐN
        if cost > subtotal:                                              # dưới vốn — LUÔN áp
            triggers.append({"key": EXC_BELOW_COST, "label": _LABELS[EXC_BELOW_COST]})
        elif cost > 0:                                                   # giá vốn 0 → markup vô định
            below = markup_min_pct is not None and profit * 100 < markup_min_pct * cost
            above = markup_max_pct is not None and profit * 100 > markup_max_pct * cost
            if below or above:
                triggers.append({"key": EXC_MARKUP_OUT, "label": _LABELS[EXC_MARKUP_OUT]})

    disc_pct = None
    if subtotal_gross and subtotal_gross > 0:
        d100 = float(discount_amount) * 100
        disc_pct = round(d100 / subtotal_gross)
        below = discount_min_pct is not None and d100 < discount_min_pct * subtotal_gross
        above = discount_max_pct is not None and d100 > discount_max_pct * subtotal_gross
        if below or above:
            triggers.append({"key": EXC_DISCOUNT_OUT, "label": _LABELS[EXC_DISCOUNT_OUT]})

    return {
        "subtotal": subtotal,
        "total_gross": total_gross,
        "cost": cost,
        "markup_pct": markup_pct,
        "markup_min_pct": int(round(markup_min_pct)) if markup_min_pct is not None else None,
        "markup_max_pct": markup_max_pct,
        "high_value_threshold": high_value_threshold,
        "disc_pct": disc_pct,
        "discount_min_pct": discount_min_pct,
        "discount_max_pct": discount_max_pct,
        "triggers": triggers,
    }


def covers(exc: dict, *, appr_total, appr_subtotal, appr_cost) -> bool:
    """Bản duyệt 'approved' (đã ghim appr_*) có BAO PHỦ tình trạng hiện tại (`exc`) không: hiện tại KHÔNG
    rủi ro hơn mức đã ký. Cap quy mô tuyệt đối cho MỌI trục (tổng ≤ tổng đã ký). Trục lợi nhuận: nhân chéo
    số nguyên (mẫu dương giữ chiều bất đẳng thức, đúng cả khi lỗ). Thiếu giá vốn để so → fail-đóng.

    `markup_out` (cổng BÁO GIÁ) cũng phải soi trục lợi nhuận: thiếu nó thì báo giá mở lại (đồng bộ từ
    phiếu tính giá → về Nháp) rồi HẠ markup vẫn báo "đã bao phủ" chỉ vì tổng tiền giảm. Phép so viết
    theo BIÊN nhưng dùng chung được cho markup: cả hai đơn điệu theo giá bán/giá vốn
    (biên = markup / (1+markup)), nên "biên ≥ biên đã ký" ⇔ "markup ≥ markup đã ký"."""
    keys = {t["key"] for t in exc["triggers"]}
    if exc["total_gross"] > (appr_total or 0):
        return False
    if keys & {EXC_LOW_MARGIN, EXC_BELOW_COST, EXC_MARKUP_OUT}:
        cur_sub, cur_cost = exc["subtotal"], exc["cost"]
        if cur_cost is None or appr_cost is None or cur_sub <= 0 or (appr_subtotal or 0) <= 0:
            return False
        # biên_cur ≥ biên_appr  ⇔  (cur_sub−cur_cost)·appr_sub ≥ (appr_sub−appr_cost)·cur_sub
        if (cur_sub - cur_cost) * appr_subtotal < (appr_subtotal - appr_cost) * cur_sub:
            return False
    return True


def approval_status(exc: dict, latest: dict | None) -> dict:
    """Tình trạng duyệt. `latest` = None HOẶC dict {decision, total, subtotal, cost, note, decided_at}
    (bản GẦN NHẤT). Không trigger → không cần duyệt (cleared). Có trigger: chưa có=pending · từ chối=
    rejected · duyệt+bao phủ=approved · duyệt nhưng xấu đi=stale. Chỉ approved/none mới `cleared`."""
    if not exc["triggers"]:
        return {"required": False, "status": "none", "cleared": True, "note": None, "decided_at": None}
    if latest is None:
        return {"required": True, "status": "pending", "cleared": False, "note": None, "decided_at": None}
    if latest["decision"] == DECISION_REJECTED:
        return {"required": True, "status": "rejected", "cleared": False,
                "note": latest.get("note"), "decided_at": latest.get("decided_at")}
    covered = covers(exc, appr_total=latest["total"], appr_subtotal=latest["subtotal"],
                     appr_cost=latest["cost"])
    return {
        "required": True,
        "status": DECISION_APPROVED if covered else "stale",
        "cleared": covered,
        "note": latest.get("note"),
        "decided_at": latest.get("decided_at"),
    }
