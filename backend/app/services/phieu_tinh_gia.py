"""Phiếu tính giá — gom kết quả tính giá (Estimate) thành 4 nhóm để in phiếu.

Nguồn dữ liệu THẬT là các dòng chi phí `EstimateCostLine` mà `PricingEngine.calculate_option`
sinh ra và được lưu vào từng `EstimateOption` (theo mức số lượng). Mỗi dòng có `category` trong:
    material · ink · click_ink · plate_die · machine · operation · packing · outsource · delivery · other

Hàm thuần `estimate_to_phieu` KHÔNG chạm DB, KHÔNG tính lại — chỉ ánh xạ các dòng đã có sang 4 nhóm:
    A Giấy            ← category = material
    B Công in         ← category ∈ {machine, ink, click_ink}
    C Chế bản         ← category = plate_die
    D Gia công sau in ← category ∈ {operation, packing, outsource, delivery, other}
"""
from __future__ import annotations

from ..models.estimate import Estimate, EstimateOption


# category → nhóm (idx) của phiếu.
_CATEGORY_TO_GROUP = {
    "material": "A",
    "machine": "B",
    "ink": "B",
    "click_ink": "B",
    "plate_die": "C",
    "operation": "D",
    "packing": "D",
    "outsource": "D",
    "delivery": "D",
    "other": "D",
}


def _num(v) -> float:
    """Numeric (Decimal/None) → float cho JSON."""
    if v is None:
        return 0.0
    return float(v)


def _pick_option(est: Estimate, qty: int | None) -> EstimateOption | None:
    """Lấy đúng phương án (option) theo số lượng; fallback option đầu tiên."""
    opts = list(est.options or [])
    if not opts:
        return None
    if qty is not None:
        for o in opts:
            if o.quantity == qty:
                return o
    return opts[0]


def _row_from_line(line) -> dict:
    """Chuẩn hóa 1 dòng chi phí thành ô hiển thị (giữ nguyên field ĐÃ CÓ)."""
    snap = line.source_snapshot_json or {}
    # Tên hiển thị: ưu tiên tên vật tư/nguồn trong snapshot, fallback mô tả dòng.
    name = snap.get("name") or line.description
    return {
        "name": name,
        "description": line.description,
        "quantity": _num(line.quantity),
        "unit": line.unit,
        "unit_cost": _num(line.unit_cost),
        "setup_cost": _num(line.setup_cost),
        "amount": _num(line.total_cost),
        "min_charge_applied": bool(line.min_charge_applied),
        "note": line.note or "",
    }


# Định nghĩa cột cho từng nhóm (chỉ các field THẬT sự có trong dòng chi phí).
_GROUP_COLUMNS = {
    "A": [
        {"key": "name", "label": "Loại giấy"},
        {"key": "quantity", "label": "SL tờ mua"},
        {"key": "unit_cost", "label": "Đơn giá"},
        {"key": "amount", "label": "Số tiền"},
    ],
    "B": [
        {"key": "description", "label": "Mô tả"},
        {"key": "unit_cost", "label": "Đơn giá"},
        {"key": "amount", "label": "Số tiền"},
    ],
    "C": [
        {"key": "description", "label": "Mô tả"},
        {"key": "quantity", "label": "SL bản"},
        {"key": "unit_cost", "label": "Đơn giá"},
        {"key": "amount", "label": "Số tiền"},
    ],
    "D": [
        {"key": "name", "label": "Tên công đoạn"},
        {"key": "quantity", "label": "SL"},
        {"key": "unit_cost", "label": "Đơn giá"},
        {"key": "amount", "label": "Số tiền"},
        {"key": "note", "label": "Ghi chú"},
    ],
}

_GROUP_NAMES = {
    "A": "Giấy",
    "B": "Công in",
    "C": "Chế bản",
    "D": "Gia công sau in",
}


def _build_header(est: Estimate, opt: EstimateOption | None, qty: int | None) -> dict:
    spec = est.input_spec_json or {}
    fw = spec.get("finished_width") or spec.get("finished_w")
    fh = spec.get("finished_height") or spec.get("finished_h")
    kho = ""
    if fw and fh:
        kho = f"{fw}×{fh} cm"
    return {
        "so_phieu": est.estimate_number,
        "ngay_lap": est.created_at.isoformat() if est.created_at else None,
        "ten_an_pham": est.product_name,
        "so_luong": qty if qty is not None else (opt.quantity if opt else None),
        "kho_thanh_pham": kho,
        # Đơn vị tính thành phẩm chưa có field riêng trong spec → để rỗng nếu không khai.
        "dvt": spec.get("dvt") or "",
    }


def _build_noi_dung(est: Estimate) -> list[dict]:
    """Thông số kỹ thuật tối thiểu lấy TRỰC TIẾP từ input_spec (bỏ qua field chưa khai)."""
    spec = est.input_spec_json or {}
    out: list[dict] = []

    def add(label: str, value) -> None:
        if value not in (None, "", 0):
            out.append({"label": label, "text": str(value)})

    add("Loại sản phẩm", est.product_type)
    sw = spec.get("sheet_w")
    sh = spec.get("sheet_h")
    if sw and sh:
        out.append({"label": "Khổ tờ in", "text": f"{sw}×{sh} cm"})
    add("Số màu", spec.get("colors"))
    add("Số mặt", spec.get("sides"))
    add("Số con/tờ", spec.get("pieces_per_sheet"))
    return out


def estimate_to_phieu(est: Estimate, qty: int | None = None) -> dict:
    """Ánh xạ kết quả tính giá của 1 phiếu (Estimate) sang cấu trúc 4 nhóm để in Phiếu tính giá.

    Hàm thuần: chỉ đọc `est.options[*].cost_lines` đã lưu, KHÔNG tính lại, KHÔNG chạm DB.

    Args:
        est: bản ghi Estimate (đã eager-load options + cost_lines).
        qty: mức số lượng muốn in; None ⇒ lấy phương án đầu tiên.
    """
    opt = _pick_option(est, qty)
    lines = list(opt.cost_lines) if opt else []

    # Gom dòng theo nhóm (giữ thứ tự xuất hiện).
    grouped: dict[str, list] = {"A": [], "B": [], "C": [], "D": []}
    for line in lines:
        g = _CATEGORY_TO_GROUP.get(line.category, "D")  # category lạ → xếp vào Gia công
        grouped[g].append(line)

    groups = []
    grand_total = 0.0
    for idx in ("A", "B", "C", "D"):
        rows = [_row_from_line(l) for l in grouped[idx]]
        subtotal = sum(r["amount"] for r in rows)
        grand_total += subtotal
        groups.append({
            "idx": idx,
            "name": _GROUP_NAMES[idx],
            "columns": _GROUP_COLUMNS[idx],
            "rows": rows,
            "subtotal": subtotal,
        })

    return {
        "header": _build_header(est, opt, qty),
        "noi_dung": _build_noi_dung(est),
        "groups": groups,
        "grand_total": grand_total,
    }
