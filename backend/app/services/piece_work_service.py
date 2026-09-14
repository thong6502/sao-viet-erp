"""Lương khoán (module `luong`, nhịp 2) — nghiệp vụ.

Không còn tầng "sổ khoán" (quỹ tổ + bù lỗ + thưởng + chia hệ số). Chỉ còn:
  - khoan_map / defect_map: tổng hợp tiền khoán mỗi NV từ Phiếu sản lượng THEO NGƯỜI của kỳ,
    cộng thẳng vào cột `khoan` của payroll_lines lúc tính lương.

Thưởng/phạt tổ trưởng theo khoảng sản lượng × tỷ lệ hàng lỗi GỠ 13/09/2026 (mg `0300`).

CRUD bảng đơn giá (`piece_rates`) KHÔNG còn ở đây — từ 17/08/2026 nó là danh mục "Công việc khoán"
(`services/cong_viec_khoan_service.py`). Hai hàm THUẦN còn lại (`dau_viec_khop`, `khoan_snapshot`)
chỉ ĐỌC một dòng đơn giá, Kế hoạch SX gọi khi bung lệnh — không ghi gì nên vẫn thuộc về đây.

Cổng chốt = Chốt kỳ lương (payroll_lines đóng băng số khoán khi kỳ chốt). Không có chốt riêng.
"""
from __future__ import annotations


def _r(x) -> float:
    return float(round(float(x or 0)))


def dau_viec_khop(rates, *, department_id: int | None) -> list:
    """Các đầu việc khoán của một TỔ — HÀM THUẦN (Kế hoạch SX gọi khi bung lệnh).

    Luật khớp chỉ còn một dòng: cùng tổ. Bảng đơn giá là bảng KHAI BÁO thuần — nó không biết và
    không cần biết việc nào của tổ dùng dòng nào; gốc là bên sản xuất, người lập lệnh nhìn các
    đơn giá của tổ rồi chọn. Bản trước cho khai "áp cho công đoạn nào" ngay trên dòng giá, thành
    ra một luật khớp ngầm (dòng khai riêng thắng dòng khai chung) mà mở form ra không ai đoán được.

    Trả list (0 = tổ không ăn khoán / chưa khai · 1 = tự điền được · >1 = để người chọn).
    """
    return [
        r for r in (rates or [])
        if (getattr(r, "active", None) if hasattr(r, "active") else getattr(r, "is_active", True))
        and (department_id is None or r.department_id == department_id)
    ]


def khoan_snapshot(rate, dm=None) -> dict:
    """Ảnh chụp ĐẦU VIỆC để ghim vào bước lệnh — tên việc + đơn vị, không có giá.

    Từ 11/09/2026 sản xuất và kế hoạch không ôm tiền khoán nữa (chủ xưởng chốt: *"bên sản xuất chỉ
    ghi nhận số lượng thôi"*). Nên ảnh chụp bỏ `don_gia` và `cong_thuc` (công thức RA TIỀN): ghim
    giá lúc phát hành là ghim một con số mà máy nào chạy, kíp mấy người, mấy màu mực, khuôn cũ hay
    mới đều làm nó đổi — những chiều engine không suy được.

    `rate_id` + `ten` thì GIỮ, và giữ vì lý do ngược lại: đó là CÁI TÊN của việc. Kế toán lương đọc
    tên đó rồi tra bảng giá tại thời điểm tính lương.

    `don_vi` cũng GIỮ, nhưng nay CHỈ còn một việc: làm ĐÍCH quy đổi mặc định khi đo GIỜ bước Tổ —
    `dich_gio_cua_khoan` lùi về nó khi đầu việc chưa khai `don_vi_nang_suat`. Bỏ nó ra khỏi ảnh chụp
    thì mọi bước Tổ chưa khai đơn vị năng suất tịt đích, `sl_tinh_cua_buoc` trả None và bước hiện 0
    phút — xếp lịch chặn đặt lịch mà không nói vì sao. Nó là ĐƠN VỊ, không phải tiền; đi một mình,
    không còn `don_gia` nào kèm.

    `cong_thuc_gio` (cách đo GIỜ, tách hẳn khỏi cách đo tiền) vẫn chụp: thời lượng bước và Xếp lịch
    sống bằng nó. Khoá này CÓ MẶT kể cả khi rỗng — chính SỰ CÓ MẶT của nó là dấu "ảnh chụp biết đầu
    việc có ô đo giờ riêng", `dich_gio_cua_khoan` gác luật theo đúng dấu đó; ảnh chụp trước
    07/09/2026 vắng khoá nên lùi về `cong_thuc` như cũ, lệnh đã phát không xê dịch một phút nào.

    Ảnh chụp CŨ trong DB vẫn còn các khoá tiền; không migrate (JSON không có schema, khoá mồ côi vô
    hại) — code thôi đọc chúng là đủ. Xem
    `docs/superpowers/specs/2026-09-11-san-xuat-chi-ghi-so-luong-design.md`.
    """
    snap = {
        "rate_id": rate.id,
        "ten": getattr(rate, "ten", getattr(rate, "name", "")),
        "don_vi": getattr(rate, "unit", None) or None,
    }
    if dm is not None:
        snap["cong_thuc_gio"] = (getattr(dm, "cong_thuc_gio", None) or "").strip()
    return snap



class PieceWorkService:
    def __init__(self, outputs=None) -> None:
        self.outputs = outputs      # ProductionOutputRepository — nguồn tiền khoán theo người. None → bỏ.

    # CRUD đơn giá khoán (`piece_rates`) ở `CongViecKhoanService` (danh mục "Công việc khoán").

    # --- tiền khoán vào bảng lương ------------------------------------------

    def khoan_map(self, year: int, month: int) -> dict[int, float]:
        """{employee_id → tổng tiền khoán} = Σ Phiếu sản lượng theo NGƯỜI (có tính khoán) của kỳ.

        Tiền mỗi phiếu = max(0, SL × đơn giá − trừ lỗi). Sàn 0 (không đẩy lương âm — Điều 102 BLLĐ).
        Không còn cổng "chốt sổ": phiếu tính khoán chảy vào lương khi HCNS tính lương; đóng băng khi
        Chốt kỳ lương.
        """
        out: dict[int, float] = {}
        if self.outputs is None:
            return out
        for o in self.outputs.list_nguoi_by_period(year, month):
            if not o.tinh_khoan or not o.employee_id:
                continue
            amt = max(0.0, float(o.unit_price) * float(o.quantity) - float(o.defect_deduction or 0))
            out[o.employee_id] = out.get(o.employee_id, 0.0) + _r(amt)
        return out

    def defect_map(self, year: int, month: int) -> dict[int, float]:
        """{employee_id → tổng TRỪ LỖI khoán theo NGƯỜI} của kỳ — Lương gộp vào trần khấu trừ 30%
        (Điều 102). Cùng nguồn Phiếu sản lượng theo người + tính khoán như khoan_map."""
        out: dict[int, float] = {}
        if self.outputs is None:
            return out
        for o in self.outputs.list_nguoi_by_period(year, month):
            if not o.tinh_khoan or not o.employee_id:
                continue
            out[o.employee_id] = out.get(o.employee_id, 0.0) + _r(float(o.defect_deduction or 0))
        return out
