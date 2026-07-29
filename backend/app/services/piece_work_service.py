"""Lương khoán (module `luong`, nhịp 2) — nghiệp vụ.

Không còn tầng "sổ khoán" (quỹ tổ + bù lỗ + thưởng + chia hệ số). Chỉ còn:
  - Đơn giá khoán (piece_rates): bảng giá tra khi ghi Phiếu sản lượng.
  - khoan_map / defect_map: tổng hợp tiền khoán mỗi NV từ Phiếu sản lượng THEO NGƯỜI của kỳ,
    cộng thẳng vào cột `khoan` của payroll_lines lúc tính lương.

Cổng chốt = Chốt kỳ lương (payroll_lines đóng băng số khoán khi kỳ chốt). Không có chốt riêng.
"""
from __future__ import annotations


class PieceWorkError(Exception):
    pass


class PieceWorkValidationError(PieceWorkError):
    pass


class PieceWorkNotFound(PieceWorkError):
    pass


def _r(x) -> float:
    return float(round(float(x or 0)))


class PieceWorkService:
    def __init__(self, piece, outputs=None) -> None:
        self.piece = piece          # PieceWorkRepository (đơn giá khoán)
        self.outputs = outputs      # ProductionOutputRepository — nguồn tiền khoán theo người. None → bỏ.

    # --- đơn giá khoán ------------------------------------------------------

    def list_rates(self, department_id: int | None = None):
        return self.piece.list_rates(department_id=department_id)

    def create_rate(self, **f):
        if not f.get("group_name"):
            raise PieceWorkValidationError("Thiếu tổ khoán.")
        if not f.get("name"):
            raise PieceWorkValidationError("Thiếu tên công việc.")
        if f.get("unit_price") is None:
            raise PieceWorkValidationError("Thiếu đơn giá.")
        return self.piece.create_rate(**f)

    def update_rate(self, rate_id, **f):
        r = self.piece.get_rate(rate_id)
        if r is None:
            raise PieceWorkNotFound("Không tìm thấy đơn giá.")
        return self.piece.update_rate(r, **{k: v for k, v in f.items() if v is not None})

    def delete_rate(self, rate_id):
        r = self.piece.get_rate(rate_id)
        if r is None:
            raise PieceWorkNotFound("Không tìm thấy đơn giá.")
        self.piece.delete_rate(r)

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
