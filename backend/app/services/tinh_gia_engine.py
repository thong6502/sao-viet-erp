"""Engine tính giá MỚI — dựng trên bộ danh mục rebuild (Công đoạn / Bù hao / Giấy / Vật tư).

Hàm THUẦN (không I/O, không ORM): nhận cấu hình đã load sẵn (dict/list) → trả `dict`
JSON-serializable đúng cấu trúc 4 nhóm của `phieu_tinh_gia.estimate_to_phieu` để FE tái dùng
component in phiếu.

Tận dụng 2 engine thuần đã có:
  - `routing_engine.compute_step_cost(cd, ctx)` — tiền 1 công đoạn (§4.1).
  - `bu_hao_engine.tong_bu_hao(cong_doans, rows=…, sl)` — Σ tờ bù hao (công đoạn trỏ mã bù hao).

Gom nhóm (khớp estimate_to_phieu):
  A Giấy            ← to_gross × đơn giá giấy.
  C Chế bản         ← dòng kẽm (so_mau × so_mat × giá kẽm) + công đoạn nhom='prepress'.
  B Công in         ← công đoạn nhom='print'.
  D Gia công sau in ← công đoạn nhom='finishing'.

Hạn chế v1 (ghi vào `warnings`): công đoạn `che_do_tinh='theo_gio'` bỏ qua (cần BHR + tốc độ máy);
MỰC chưa tính (chưa có đầu vào coverage/định lượng mực); giá giấy nhân THẲNG theo tờ (nếu
`don_vi_gia` ≠ 'to' — kg/ram — có thể lệch).
"""
from __future__ import annotations

from math import ceil

from .bu_hao_engine import tong_bu_hao
from .routing_engine import compute_step_cost


def _f(v, d: float = 0.0) -> float:
    if v is None:
        return d
    try:
        return float(v)
    except (TypeError, ValueError):
        return d


def _r(v: float) -> float:
    """Làm tròn 2 số lẻ, trả number (JSON)."""
    return round(_f(v), 2)


# --- Cột từng nhóm (kind = gợi ý format cho FE; align = canh cột) ---
_COLS = {
    "A": [
        {"key": "ten", "label": "Loại giấy", "align": "left", "kind": "text"},
        {"key": "so_to", "label": "SL tờ", "align": "right", "kind": "number"},
        {"key": "don_gia", "label": "Đơn giá", "align": "right", "kind": "money"},
        {"key": "thanh_tien", "label": "Số tiền", "align": "right", "kind": "money"},
    ],
    "B": [
        {"key": "ten", "label": "Tên công đoạn", "align": "left", "kind": "text"},
        {"key": "thanh_tien", "label": "Số tiền", "align": "right", "kind": "money"},
        {"key": "ghi_chu", "label": "Ghi chú", "align": "left", "kind": "text"},
    ],
    "C": [
        {"key": "ten", "label": "Nội dung", "align": "left", "kind": "text"},
        {"key": "sl", "label": "SL", "align": "right", "kind": "number"},
        {"key": "don_gia", "label": "Đơn giá", "align": "right", "kind": "money"},
        {"key": "thanh_tien", "label": "Số tiền", "align": "right", "kind": "money"},
    ],
    "D": [
        {"key": "ten", "label": "Tên công đoạn", "align": "left", "kind": "text"},
        {"key": "thanh_tien", "label": "Số tiền", "align": "right", "kind": "money"},
        {"key": "ghi_chu", "label": "Ghi chú", "align": "left", "kind": "text"},
    ],
}
_NAMES = {"A": "Giấy", "B": "Công in", "C": "Chế bản", "D": "Gia công sau in"}
# nhom công đoạn → nhóm phiếu.
_NHOM_TO_GROUP = {"prepress": "C", "print": "B", "finishing": "D"}


def _step_cost(cd: dict, ctx: dict, warnings: list[str]) -> tuple[float, str]:
    """Tiền 1 công đoạn theo `compute_step_cost`, an toàn (KHÔNG crash) cho v1.

    Trả (tiền, ghi_chú). theo_gio → 0đ + cảnh báo (cần BHR + tốc độ máy). Lỗi cấu hình
    (thiếu pricing_basis…) → 0đ + cảnh báo.
    """
    ten = cd.get("ten") or cd.get("ma") or "Công đoạn"
    if cd.get("che_do_tinh", "theo_san_luong") == "theo_gio":
        warnings.append(f"Công đoạn '{ten}': tính theo giờ (cần BHR + tốc độ máy) — v1 bỏ qua, tính 0đ.")
        return 0.0, "theo giờ — chưa tính (v1)"
    try:
        res = compute_step_cost(cd, ctx)
    except Exception as e:  # noqa: BLE001 — v1 không được crash, gom vào warnings
        warnings.append(f"Công đoạn '{ten}': không tính được ({e}) — tính 0đ.")
        return 0.0, "lỗi cấu hình — 0đ"
    return _f(res.get("total")), ""


def tinh_gia(*, qty: int, pieces_per_sheet: int, so_mau: int, so_mat: int,
             giay: dict | None, kem_don_gia: float, cong_doans: list[dict],
             bu_hao_rows: list[dict], so_con: int = 1,
             dt_to_in_cm2: float = 0, dt_thanh_pham_cm2: float = 0) -> dict:
    """Tính giá 1 đơn → cấu trúc 4 nhóm (A Giấy · B Công in · C Chế bản · D Gia công sau in).

    Args:
        qty: số lượng thành phẩm (đơn đặt).
        pieces_per_sheet: số con/tờ in (để ra số tờ net).
        so_mau: số màu in (trục bù hao + số kẽm).
        so_mat: số mặt in (số kẽm = so_mau × so_mat).
        giay: dict giấy {ten, don_gia, don_vi_gia, …} hoặc None (bỏ nhóm Giấy).
        kem_don_gia: đơn giá 1 bản kẽm.
        cong_doans: list dict công đoạn ĐÃ sort theo routing; mỗi cái có nhom / pricing_basis /
            kieu_bu_hao / bu_hao_id / so_to_bu_hao / run_rate / rate_tiers / first_unit_floor /
            min_charge / setup_cost / che_do_tinh / ten.
        bu_hao_rows: toàn bộ dòng bù hao (danh mục) để tra bảng theo bu_hao_id.
        so_con: số con (cho ctx routing).
        dt_to_in_cm2: diện tích 1 tờ in (cm²) — cho basis theo diện tích.
        dt_thanh_pham_cm2: diện tích 1 thành phẩm (cm²).

    Returns:
        dict JSON-serializable: {meta, groups:[{idx,name,columns,rows,subtotal}], grand_total, warnings}.
    """
    warnings: list[str] = []
    qty = int(qty or 0)
    pieces = max(int(pieces_per_sheet or 1), 1)
    so_mau = max(int(so_mau or 0), 0)
    so_mat = max(int(so_mat or 1), 1)

    # --- Số tờ (net → +bù hao → gross) ---
    to_net = ceil(qty / pieces) if qty > 0 else 0
    bu_hao_to = tong_bu_hao(cong_doans, rows=bu_hao_rows, sl=qty)
    to_gross = to_net + bu_hao_to

    # --- ctx cho routing_engine (dùng SL GROSS) ---
    ctx = {
        "so_to_in_gross": to_gross,
        "so_mat": so_mat,
        "dt_to_in_cm2": _f(dt_to_in_cm2),
        "dt_thanh_pham_cm2": _f(dt_thanh_pham_cm2),
        "so_luong_thanh_pham": qty,
        "so_con": so_con,
        "so_trang": 0,
        "so_cuon": 0,
        "so_vi_tri": 0,
        "so_bao": 0,
        "so_thung": 0,
    }

    grouped: dict[str, list[dict]] = {"A": [], "B": [], "C": [], "D": []}

    # --- A Giấy: 1 dòng = to_gross × đơn giá giấy ---
    if giay:
        don_gia_giay = _f(giay.get("don_gia"))
        if giay.get("don_vi_gia") and giay.get("don_vi_gia") != "to":
            warnings.append(
                f"Giấy tính theo đơn vị '{giay.get('don_vi_gia')}' — v1 nhân thẳng theo tờ, "
                "số tiền giấy có thể lệch."
            )
        grouped["A"].append({
            "ten": giay.get("ten") or "Giấy",
            "so_to": _r(to_gross),
            "don_gia": _r(don_gia_giay),
            "thanh_tien": _r(to_gross * don_gia_giay),
        })
    else:
        warnings.append("Chưa chọn giấy — bỏ nhóm Giấy.")

    # --- C Chế bản: dòng kẽm ---
    so_kem = so_mau * so_mat
    if kem_don_gia and kem_don_gia > 0 and so_kem > 0:
        grouped["C"].append({
            "ten": f"Kẽm ({so_mau} màu × {so_mat} mặt)",
            "sl": so_kem,
            "don_gia": _r(kem_don_gia),
            "thanh_tien": _r(so_kem * _f(kem_don_gia)),
        })
    elif so_kem > 0:
        warnings.append("Thiếu đơn giá kẽm — dòng kẽm tính 0đ.")
        grouped["C"].append({"ten": f"Kẽm ({so_mau} màu × {so_mat} mặt)", "sl": so_kem,
                             "don_gia": 0.0, "thanh_tien": 0.0})

    # --- Công đoạn → B / C / D theo nhom ---
    for cd in cong_doans:
        nhom = cd.get("nhom")
        grp = _NHOM_TO_GROUP.get(nhom)
        if grp is None:
            warnings.append(f"Công đoạn '{cd.get('ten') or cd.get('ma')}': nhom='{nhom}' lạ — bỏ qua.")
            continue
        tien, ghi_chu = _step_cost(cd, ctx, warnings)
        ten = cd.get("ten") or cd.get("ma") or "Công đoạn"
        if grp == "C":
            grouped["C"].append({"ten": ten, "sl": None, "don_gia": None, "thanh_tien": _r(tien)})
        else:  # B | D
            grouped[grp].append({"ten": ten, "thanh_tien": _r(tien), "ghi_chu": ghi_chu})

    # --- Đóng gói nhóm + tổng ---
    groups = []
    grand_total = 0.0
    for idx in ("A", "B", "C", "D"):
        rows = grouped[idx]
        subtotal = sum(_f(r.get("thanh_tien")) for r in rows)
        grand_total += subtotal
        groups.append({
            "idx": idx,
            "name": _NAMES[idx],
            "columns": _COLS[idx],
            "rows": rows,
            "subtotal": _r(subtotal),
        })

    return {
        "meta": {
            "qty": qty,
            "pieces_per_sheet": pieces,
            "so_mau": so_mau,
            "so_mat": so_mat,
            "so_con": so_con,
            "to_net": to_net,
            "bu_hao_to": _r(bu_hao_to),
            "to_gross": _r(to_gross),
            "so_kem": so_kem,
        },
        "groups": groups,
        "grand_total": _r(grand_total),
        "warnings": warnings,
    }
