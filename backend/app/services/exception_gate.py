"""Máy soi "ĐẶC THÙ cần Giám đốc duyệt" — logic THUẦN, dùng CHUNG cho Đơn hàng (A2) và Báo giá (BG-2).

MỘT nguồn định nghĩa (chống trôi lệch giữa 2 nơi — phản biện kiến trúc):
- 3 điều kiện: **giá trị cao** (subtotal trước VAT ≥ ngưỡng) · **biên thấp** (0 ≤ biên < ngưỡng) ·
  **bán dưới giá vốn** (biên < 0).
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
    EXC_HIGH_VALUE,
    EXC_LOW_MARGIN,
)

DECISIONS = (DECISION_APPROVED, DECISION_REJECTED)

# Ngưỡng mặc định (cấu hình versioned sau) — dùng CHUNG order + quote (cùng một giá trị đơn).
DEFAULT_MIN_MARGIN_PCT = 15                       # 0 ≤ biên < 15% → "biên thấp"
DEFAULT_HIGH_VALUE_THRESHOLD = 1_000_000_000      # subtotal (trước VAT) ≥ 1 tỷ → "giá trị cao" (SVN chốt)

_LABELS = {
    EXC_HIGH_VALUE: "Giá trị đơn cao",
    EXC_LOW_MARGIN: "Biên lợi nhuận thấp",
    EXC_BELOW_COST: "Bán dưới giá vốn",
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


def covers(exc: dict, *, appr_total, appr_subtotal, appr_cost) -> bool:
    """Bản duyệt 'approved' (đã ghim appr_*) có BAO PHỦ tình trạng hiện tại (`exc`) không: hiện tại KHÔNG
    rủi ro hơn mức đã ký. Cap quy mô tuyệt đối cho MỌI trục (tổng ≤ tổng đã ký). Trục biên: nhân chéo số
    nguyên (mẫu dương giữ chiều bất đẳng thức, đúng cả khi lỗ). Thiếu giá vốn để so → fail-đóng."""
    keys = {t["key"] for t in exc["triggers"]}
    if exc["total_gross"] > (appr_total or 0):
        return False
    if EXC_LOW_MARGIN in keys or EXC_BELOW_COST in keys:
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
