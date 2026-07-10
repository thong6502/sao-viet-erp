"""Bù hao engine — hàm THUẦN tra số tờ bù hao. Không I/O, không ORM.

Nối Công đoạn ↔ module Bù hao. Mỗi công đoạn khai `kieu_bu_hao`:
  - `theo_so_mau` / `theo_so_con` → tra bảng module Bù hao theo 2 bước:
      B1 (trục+key): chọn dòng có dải [key_tu..key_den] chứa số màu / số con.
      B2 (số lượng): chọn bậc [sl_tu..sl_den] chứa SL → giá trị (tờ | %).
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


def tra_bang(rows: list[dict], truc: str, key: float, sl: float) -> float:
    """Tra số TỜ bù hao từ các dòng bù hao cùng `truc`.

    rows = [{truc, key_tu, key_den, bac:[{sl_tu, sl_den, gia_tri, don_vi}]}].
    Trả 0.0 nếu không khớp dòng hoặc bậc.
    """
    key = _f(key)
    sl = _f(sl)
    row = None
    for r in rows:                                        # B1: dòng có dải chứa key
        if r.get("truc") != truc:
            continue
        if _f(r.get("key_tu")) <= key <= _f(r.get("key_den")):
            row = r
            break
    if row is None:
        return 0.0
    for b in (row.get("bac") or []):                      # B2: bậc chứa SL
        lo = _f(b.get("sl_tu"))
        hi = b.get("sl_den")
        in_band = sl > lo if hi in (None, "") else (lo < sl <= _f(hi))
        if in_band:
            gt = _f(b.get("gia_tri"))
            return gt * sl / 100.0 if b.get("don_vi") == "pct" else gt
    return 0.0


def bu_hao_cong_doan(cd: dict, *, rows: list[dict], so_mau: float, so_con: float, sl: float) -> float:
    """Số tờ bù hao của 1 công đoạn theo `kieu_bu_hao`."""
    kieu = cd.get("kieu_bu_hao", "khong")
    if kieu == "co_dinh":
        return _f(cd.get("so_to_bu_hao"))
    if kieu == "theo_so_mau":
        return tra_bang(rows, "so_mau", so_mau, sl)
    if kieu == "theo_so_con":
        return tra_bang(rows, "so_con", so_con, sl)
    return 0.0


def tong_bu_hao(cong_doans: list[dict], *, rows: list[dict], so_mau: float, so_con: float,
                sl: float, pct_yeu_cau: float = 0.0) -> float:
    """Tổng số tờ bù hao 1 đơn = Σ bù hao mỗi công đoạn + %_yêu_cầu × SL (nếu đơn yêu cầu)."""
    total = sum(
        bu_hao_cong_doan(cd, rows=rows, so_mau=so_mau, so_con=so_con, sl=sl)
        for cd in cong_doans
    )
    return total + _f(sl) * _f(pct_yeu_cau) / 100.0
