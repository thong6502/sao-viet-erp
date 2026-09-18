"""Lương khoán (module `luong`, nhịp 2) — nghiệp vụ.

Không còn tầng "sổ khoán" (quỹ tổ + bù lỗ + thưởng + chia hệ số). Chỉ còn:
  - khoan_map / defect_map: tổng hợp tiền khoán mỗi NV từ Phiếu sản lượng THEO NGƯỜI của kỳ,
    cộng thẳng vào cột `khoan` của payroll_lines lúc tính lương.

Thưởng/phạt tổ trưởng theo khoảng sản lượng × tỷ lệ hàng lỗi GỠ 13/09/2026 (mg `0300`).

CRUD bảng đơn giá (`piece_rates`) KHÔNG còn ở đây — từ 17/08/2026 nó là danh mục "Công việc khoán"
(`services/cong_viec_khoan_service.py`); danh sách việc khoán của MỘT tổ cho bàn tổ nằm ở
`services/san_xuat/viec_khoan.py` (18/09/2026).

Cổng chốt = Chốt kỳ lương (payroll_lines đóng băng số khoán khi kỳ chốt). Không có chốt riêng.
"""
from __future__ import annotations


def _r(x) -> float:
    return float(round(float(x or 0)))


# ⚠️ `dau_viec_khop()` GỠ 18/09/2026 cùng `khoan_snapshot()`: hàm thuần lọc rổ đơn giá theo tổ,
#    phục vụ ô chọn đầu việc ở bước lệnh. Ô đó gỡ; bàn tổ lọc ở SQL qua bảng nối
#    (`CongViecKhoanRepository.theo_to`), và cổng lập kế hoạch đọc thẳng `department_ids`.
# ⚠️ `khoan_snapshot()` GỠ 18/09/2026 (mg `0320`): nó chụp tên · đơn vị · cách đo giờ của một đầu
#    việc để GHIM vào bước lệnh / bước bài ghép. Bước thôi chọn đầu việc, nên không còn chỗ nào
#    ghim. Ảnh chụp nay nằm ở MẺ SẢN XUẤT (`san_xuat_batch.ten_khoan_snapshot` ·
#    `don_vi_khoan_snapshot` · `don_gia_khoan_snapshot`) — chụp LÚC THỢ GHI, đúng lúc biết việc gì,
#    và có ĐƠN GIÁ (mẻ là chứng từ lương, khác bước lệnh vốn chỉ là kế hoạch).



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
