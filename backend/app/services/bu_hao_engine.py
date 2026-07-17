"""Bù hao engine — hàm THUẦN tra số tờ bù hao. Không I/O, không ORM.

Nối Công đoạn ↔ module Bù hao. Mỗi công đoạn khai `kieu_bu_hao`:
  - `tra_bang` → TRỎ 1 mã bù hao (`bu_hao_id`) ở module Bù hao; engine tra bậc số lượng:
      chọn bậc [sl_tu..sl_den] chứa SL → giá trị (tờ | %).
  - `co_dinh` → cộng thẳng `so_to_bu_hao` tờ (ép kim, UV… — không theo bảng).
  - `khong` → 0.

Bậc số lượng theo quy ước "X trở xuống / X–Y" ⇒ chặn trên bao gồm: dòng chứa SL khi
`sl_tu < SL ≤ sl_den` (bậc cuối `sl_den = None` ⇒ SL > sl_tu). `don_vi='pct'` ⇒ giá trị %×SL.
"""
from __future__ import annotations


def _f(v, d: float = 0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return d


def tra_bac(bac: list[dict], sl: float) -> float:
    """Tra giá trị bù hao từ danh sách bậc số lượng của 1 dòng bù hao. Trả 0.0 nếu không khớp."""
    sl = _f(sl)
    for b in (bac or []):
        lo = _f(b.get("sl_tu"))
        hi = b.get("sl_den")
        in_band = sl > lo if hi in (None, "") else (lo < sl <= _f(hi))
        if in_band:
            gt = _f(b.get("gia_tri"))
            return gt * sl / 100.0 if b.get("don_vi") == "pct" else gt
    return 0.0


def bu_hao_cong_doan(cd: dict, *, rows: list[dict], sl: float) -> float:
    """Số tờ bù hao của 1 công đoạn theo `kieu_bu_hao`.

    rows = danh sách dòng bù hao [{id, ma, bac:[…]}] (toàn bộ danh mục Bù hao).
    """
    kieu = cd.get("kieu_bu_hao", "khong")
    if kieu == "co_dinh":
        return _f(cd.get("so_to_bu_hao"))
    if kieu == "tra_bang":
        bid = cd.get("bu_hao_id")
        if bid is None:
            return 0.0
        row = next((r for r in rows if r.get("id") == bid), None)
        return tra_bac(row.get("bac") or [], sl) if row else 0.0
    return 0.0


def tong_bu_hao(cong_doans: list[dict], *, rows: list[dict], sl: float,
                pct_yeu_cau: float = 0.0) -> float:
    """Tổng số tờ bù hao 1 đơn = Σ bù hao mỗi công đoạn + %_yêu_cầu × SL (nếu đơn yêu cầu)."""
    total = sum(bu_hao_cong_doan(cd, rows=rows, sl=sl) for cd in cong_doans)
    return total + _f(sl) * _f(pct_yeu_cau) / 100.0
