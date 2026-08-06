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


def dau_muc_can(quy_cach: dict | None) -> float:
    """Số ĐẦU MỰC máy phải có để chạy được một lượt — đếm theo TẬP MỰC, không theo số màu process.

    `so_mau_a/b` chỉ đếm CMYK nên job "CMYK + 1 Pantone" ra 4, máy 4 đơn vị lọt cửa trong khi thợ
    ra máy mới biết thiếu một đầu mực. Đếm tập là hết đoán.

    Rẽ nhánh theo quy cách in, ĐÚNG cái hợp tập của công thức kẽm:
      · AB / 1 mặt        → `max(|A|, |B|)` — mỗi lượt chạy MỘT mặt, gá được từng mặt một.
      · Tự trở / trở nhíp → `|A ∪ B|` — một lượt chạy CẢ HAI mặt trên chung bản, nên mọi mực của
        hai mặt phải lên máy cùng lúc.

    Lệnh cũ chưa có tập mực trong `quy_cach_json` → rơi về `max(so_mau_a, so_mau_b)` như trước,
    không đẻ cảnh báo giả.
    """
    qc = quy_cach or {}
    a = [m for m in (qc.get("muc_a") or []) if str(m or "").strip()]
    b = [m for m in (qc.get("muc_b") or []) if str(m or "").strip()]
    if not a and not b:
        return max(_f(qc.get("so_mau_a")), _f(qc.get("so_mau_b")))
    if qc.get("quy_cach_in") in ("tu_tro", "tro_nhip"):
        return float(len({str(m).strip().upper() for m in a + b}))
    return float(max(len(a), len(b)))


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
    so_mau = dau_muc_can(qc)
    if so_units > 0 and so_mau > so_units:
        ly_do.append(LY_DO_SO_MAU)
    gsm = _f(qc.get("gsm"))
    lo, hi = _f(may.min_stock_gsm), _f(may.max_stock_gsm)
    if gsm > 0 and ((lo > 0 and gsm < lo) or (hi > 0 and gsm > hi)):
        ly_do.append(LY_DO_GSM)
    return ly_do
