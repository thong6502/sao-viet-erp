"""Kiểm KHẢ NĂNG máy cho 1 công đoạn — soft-check "máy đề xuất, người quyết".

Tách phần xoay-90° từ `lsx_service._may_khong_hop_kho` để xếp lịch dùng chung. Mọi tiêu chí ĐỘC LẬP,
gate theo dữ liệu: thiếu khổ/số màu/định lượng hoặc máy chưa khai spec tương ứng → BỎ tiêu chí đó
(không đoán, không dựng cảnh báo giả). KHÔNG chặn thao tác — chỉ trả cờ để UI cảnh báo.

Nguồn: `lsx.quy_cach_json` (khổ in · số màu · định lượng) × spec máy (`may_thiet_bi`). Tiêu chí
"vật liệu không hỗ trợ" HOÃN: `quy_cach_json` chưa mang lớp vật liệu (`vat_lieu_ho_tro_class` bên máy
chưa có đối ứng) → thêm khi có field, đừng đoán từ giấy.
"""
from __future__ import annotations

# Lý do "cần xác nhận" khi gán máy (khớp nhãn UI).
LY_DO_KHO = "kho_vuot_may"          # khổ tờ in vượt khổ máy (xoay 90° vẫn không lọt)
LY_DO_SO_MAU = "so_mau_vuot_units"  # số màu 1 mặt vượt số đầu mực (units) → cần 2 lượt/đổi máy
LY_DO_GSM = "gsm_ngoai_khoang"      # định lượng giấy ngoài khoảng chạy được của máy


def _f(v) -> float:
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        return 0.0


def kho_khong_lot(dai: float, rong: float, max_dai: float, max_rong: float) -> bool:
    """Khổ (dai×rong) KHÔNG lọt máy dù xoay 90°. Thiếu số (≤0) → coi như lọt (bỏ tiêu chí)."""
    if dai <= 0 or rong <= 0 or max_dai <= 0 or max_rong <= 0:
        return False
    lot = (dai <= max_dai and rong <= max_rong) or (rong <= max_dai and dai <= max_rong)
    return not lot


def kiem_kha_nang(quy_cach: dict | None, may) -> list[str]:
    """DS lý do 'cần xác nhận' khi đưa công đoạn lên `may`. Rỗng = hợp / chưa đủ dữ liệu để nghi ngờ.
    `may=None` → rỗng (chưa gán máy thì không kiểm)."""
    if may is None:
        return []
    qc = quy_cach or {}
    ly_do: list[str] = []
    if kho_khong_lot(_f(qc.get("kho_in_dai")), _f(qc.get("kho_in_rong")),
                     _f(may.kho_max_dai), _f(may.kho_max_rong)):
        ly_do.append(LY_DO_KHO)
    so_units = _f(may.so_units)
    so_mau = max(_f(qc.get("so_mau_a")), _f(qc.get("so_mau_b")))
    if so_units > 0 and so_mau > so_units:
        ly_do.append(LY_DO_SO_MAU)
    gsm = _f(qc.get("gsm"))
    lo, hi = _f(may.min_stock_gsm), _f(may.max_stock_gsm)
    if gsm > 0 and ((lo > 0 and gsm < lo) or (hi > 0 and gsm > hi)):
        ly_do.append(LY_DO_GSM)
    return ly_do
