"""Lương khoán (module `luong`, nhịp 2) — nghiệp vụ.

Không còn tầng "sổ khoán" (quỹ tổ + bù lỗ + thưởng + chia hệ số). Chỉ còn:
  - Đơn giá khoán (piece_rates): bảng giá tra khi ghi Phiếu sản lượng.
  - khoan_map / defect_map: tổng hợp tiền khoán mỗi NV từ Phiếu sản lượng THEO NGƯỜI của kỳ,
    cộng thẳng vào cột `khoan` của payroll_lines lúc tính lương.

Cổng chốt = Chốt kỳ lương (payroll_lines đóng băng số khoán khi kỳ chốt). Không có chốt riêng.
"""
from __future__ import annotations

import re

from ..models.piece_work import DEFAULT_PIECE_UNITS, UNIT_KHAC


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

    def unit_suggestions(self) -> list[str]:
        """Gợi ý cho ô "Đơn vị" = mồi mặc định ∪ đơn vị nhà máy ĐÃ dùng. Không phải whitelist —
        người dùng gõ đơn vị ngoài danh sách này vẫn lưu bình thường."""
        return sorted(set(DEFAULT_PIECE_UNITS) | set(self.piece.distinct_units()))

    def _normalize_unit(self, raw) -> str:
        """Chuẩn hoá đơn vị TRƯỚC KHI LƯU. Gõ tự do thì phải có chỗ này, không thì cùng một đơn
        vị đẻ ra "kg", "Kg", " KG " — gợi ý phình lên, thống kê không gom được.

        Hai bước: (1) cắt khoảng trắng thừa; (2) khớp KHÔNG PHÂN BIỆT HOA/THƯỜNG với đơn vị đã
        dùng ⇒ lấy ĐÚNG cách viết đã dùng.

        CỐ Ý không gộp theo DẤU: "to" và "tô" là hai đơn vị khác nhau, bỏ dấu để gộp là sai
        nghĩa. Và cố ý KHÔNG chặn đơn vị mới — chốt của chủ là gõ gì cũng được."""
        s = re.sub(r"\s+", " ", str(raw or "").strip())
        if not s:
            return UNIT_KHAC
        for known in self.unit_suggestions():
            if known.lower() == s.lower():
                return known
        return s

    def create_rate(self, **f):
        if not f.get("group_name"):
            raise PieceWorkValidationError("Thiếu tổ khoán.")
        if not f.get("name"):
            raise PieceWorkValidationError("Thiếu tên công việc.")
        if f.get("unit_price") is None:
            raise PieceWorkValidationError("Thiếu đơn giá.")
        f["unit"] = self._normalize_unit(f.get("unit"))
        return self.piece.create_rate(**f)

    def update_rate(self, rate_id, **f):
        r = self.piece.get_rate(rate_id)
        if r is None:
            raise PieceWorkNotFound("Không tìm thấy đơn giá.")
        patch = {k: v for k, v in f.items() if v is not None}
        if "unit" in patch:
            patch["unit"] = self._normalize_unit(patch["unit"])
        return self.piece.update_rate(r, **patch)

    def delete_rate(self, rate_id):
        r = self.piece.get_rate(rate_id)
        if r is None:
            raise PieceWorkNotFound("Không tìm thấy đơn giá.")
        self.piece.delete_rate(r)

    # --- Bậc thưởng/phạt tổ trưởng theo tỷ lệ hàng lỗi (chủ 29/07/2026) ------

    def leader_brackets(self, department_id: int):
        return self.piece.list_leader_brackets(department_id)

    def set_leader_brackets(self, *, department_id: int, rows: list[dict]):
        """Thay CẢ BỘ mốc của một tổ, sau khi kiểm bảng có hợp lệ không.

        Validate không phải để làm khó: bảng mốc có lỗ hoặc không tăng dần thì hàm tra rơi vào
        bậc SAI ⇒ ra sai tiền thưởng/phạt, mà đây là tiền thật của tổ trưởng."""
        clean: list[dict] = []
        for i, r in enumerate(rows or [], start=1):
            up = r.get("up_to_defect_pct")
            rate = r.get("rate_pct")
            if rate is None:
                raise PieceWorkValidationError(f"Bậc {i}: thiếu % thưởng/phạt.")
            if not (-100 <= float(rate) <= 100):
                raise PieceWorkValidationError(
                    f"Bậc {i}: % thưởng/phạt phải trong khoảng −100 đến 100."
                )
            if up is not None and float(up) < 0:
                raise PieceWorkValidationError(f"Bậc {i}: tỷ lệ lỗi không được âm.")
            clean.append({
                "seq": i,
                "up_to_defect_pct": None if up is None else float(up),
                "rate_pct": float(rate),
                "note": (r.get("note") or None),
            })

        if not clean:
            # Bộ RỖNG là hợp lệ = "tổ này không áp thưởng/phạt tổ trưởng". Cho xoá sạch.
            self.piece.replace_leader_brackets(department_id, [])
            return self.leader_brackets(department_id)

        vo_cuc = [i for i, r in enumerate(clean, start=1) if r["up_to_defect_pct"] is None]
        if len(vo_cuc) != 1:
            raise PieceWorkValidationError(
                "Phải có ĐÚNG MỘT bậc cuối để trống ô 'tỷ lệ lỗi tới' — đó là bậc 'trở lên', "
                "hứng mọi tỷ lệ cao hơn. Thiếu nó thì lỗi vượt mốc cuối sẽ không rơi vào bậc nào."
            )
        if vo_cuc[0] != len(clean):
            raise PieceWorkValidationError("Bậc để trống ('trở lên') phải nằm CUỐI bảng.")

        moc = [r["up_to_defect_pct"] for r in clean[:-1]]
        for a, b in zip(moc, moc[1:]):
            if b <= a:
                raise PieceWorkValidationError(
                    f"Tỷ lệ lỗi phải TĂNG DẦN theo bậc ({a:g}% rồi tới {b:g}% là sai thứ tự)."
                )

        self.piece.replace_leader_brackets(department_id, clean)
        return self.leader_brackets(department_id)

    @staticmethod
    def leader_bonus_pct(defect_pct, brackets) -> float:
        """% thưởng/phạt của tổ trưởng ứng với tỷ lệ hàng lỗi `defect_pct`.

        Bậc ĐẦU TIÊN có `defect_pct <= up_to_defect_pct` thắng; `up_to` None = bậc ∞. Mirror
        `_late_penalty_amount` của payroll — MỘT khuôn tra bậc, không sáng tác kiểu thứ hai.

        Trả DƯƠNG = thưởng, ÂM = phạt, 0 = không thưởng không phạt."""
        if not brackets:
            return 0.0
        d = float(defect_pct or 0)
        for b in brackets:
            if b.up_to_defect_pct is None or d <= float(b.up_to_defect_pct):
                return float(b.rate_pct)
        return float(brackets[-1].rate_pct)

    @classmethod
    def leader_bonus_amount(cls, *, tong_khoan_to, defect_pct, brackets) -> float:
        """Tiền thưởng/phạt tổ trưởng = tổng khoán của tổ × % của bậc trúng. Âm = trừ.

        ⚠️ CHƯA CÓ AI GỌI. Chờ nối vào `PayrollService.generate` cùng lúc dựng lại nguồn sản
        lượng — hiện `khoan_map` luôn rỗng nên `tong_khoan_to` sẽ là 0 và hàm này trả 0.
        Đã có test riêng (`test_khoan_api.py`) để nó không thành hàm chết như `_lookup_rule`."""
        return _r(float(tong_khoan_to or 0) * cls.leader_bonus_pct(defect_pct, brackets) / 100.0)

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
