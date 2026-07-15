"""Phiếu sản lượng công đoạn (Pha 5b-1) — nghiệp vụ.

Ghi sản lượng thực mỗi công đoạn của một LSX. 5b-1 CHỈ hỗ trợ ghi theo TỔ (chia hệ số ở sổ khoán).
Phiếu vào `production_outputs` (luôn cho ghi nếu có quyền `san_luong`); tiền chỉ chảy vào lương khi
HCNS Chốt sổ khoán tổ (materialize — xem PieceWorkService.sync_outputs). Trừ lỗi + ghi theo NGƯỜI = 5b-2.
"""
from __future__ import annotations

from ..models.production_output import DEFECT_CAUSES, DEFECT_LOI_THO


class OutputError(Exception):
    pass


class OutputValidationError(OutputError):
    pass


class OutputNotFound(OutputError):
    pass


def _r(x) -> float:
    return float(round(float(x or 0)))


class ProductionOutputService:
    def __init__(self, outputs, cong_doan, piece) -> None:
        self.outputs = outputs        # ProductionOutputRepository
        self.cong_doan = cong_doan    # CongDoanRepository
        self.piece = piece            # PieceWorkRepository (tra đơn giá)

    def list_by_order(self, order_id):
        return self.outputs.list_by_order(order_id)

    def _resolve_rate(self, group_name, cong_doan, piece_rate_id):
        if piece_rate_id:
            return self.piece.get_rate(piece_rate_id)
        # Tra đơn giá theo (tổ + công đoạn), ưu tiên đang dùng, mới nhất. Theo-người (không tổ) →
        # tra theo công đoạn thôi.
        cand = [r for r in self.piece.list_rates(active_only=True)
                if r.cong_doan == cong_doan and (group_name is None or r.group_name == group_name)]
        return cand[-1] if cand else None

    @staticmethod
    def _deduction(cd, quantity, defect_qty, defect_cause, unit_price) -> float:
        """Tiền trừ lỗi (5b-2): chỉ khi lỗi DO THỢ và vượt ngưỡng công đoạn. Ngưỡng = max(SL_chạy×%, abs)."""
        if defect_cause != DEFECT_LOI_THO or float(defect_qty or 0) <= 0:
            return 0.0
        total_run = float(quantity or 0) + float(defect_qty or 0)
        allowance = max(total_run * float(cd.allowed_defect_pct or 0), float(cd.allowed_defect_abs or 0))
        excess = max(0.0, float(defect_qty) - allowance)
        return _r(excess * float(unit_price or 0))

    def create(self, *, actor=None, can_set_tinh_khoan=False, **f):
        cd = self.cong_doan.find_by_ma(f.get("cong_doan"))
        if cd is None:
            raise OutputNotFound("Không tìm thấy công đoạn.")
        mode = cd.khoan_ghi_theo
        if mode == "khong":
            raise OutputValidationError(f"Công đoạn '{cd.ten}' không tính khoán (khai 'theo tổ/người' ở danh mục Công đoạn).")
        group = f.get("group_name")
        emp = f.get("employee_id")
        if mode == "to" and not group:
            raise OutputValidationError("Thiếu tổ khoán.")
        if mode == "nguoi" and not emp:
            raise OutputValidationError("Công đoạn ghi theo NGƯỜI — thiếu nhân viên.")
        if mode == "nguoi" and not group:
            raise OutputValidationError("Thiếu tổ (để chốt sổ khoán tổ tương ứng).")
        cause = f.get("defect_cause")
        if float(f.get("defect_qty") or 0) > 0 and cause and cause not in DEFECT_CAUSES:
            raise OutputValidationError("Nguyên nhân hỏng không hợp lệ.")
        order = self.outputs.get_order(f["production_order_id"])
        if order is None:
            raise OutputNotFound("Không tìm thấy lệnh sản xuất.")

        rate = self._resolve_rate(group, f["cong_doan"], f.get("piece_rate_id"))
        work_name = f.get("work_name") or (rate.name if rate else cd.ten)
        unit = f.get("unit") or (rate.unit if rate else "khac")
        unit_price = f.get("unit_price")
        if unit_price is None:
            unit_price = float(rate.unit_price) if rate else None
        if unit_price is None:
            raise OutputValidationError("Chưa có đơn giá cho công đoạn này — chọn đơn giá hoặc nhập tay.")

        is_bu = getattr(order, "order_kind", "thuong") == "bu"
        req = f.get("tinh_khoan")
        if req is None:
            tinh = not is_bu
        else:
            if is_bu and req and not can_set_tinh_khoan:
                raise OutputValidationError("Chỉ HCNS được bật 'tính khoán' cho lệnh sản xuất bù.")
            tinh = bool(req)

        ded = self._deduction(cd, f.get("quantity") or 0, f.get("defect_qty") or 0, cause, unit_price)
        return self.outputs.create(
            production_order_id=f["production_order_id"], cong_doan=f["cong_doan"], ghi_theo=mode,
            year=f["year"], month=f["month"], group_name=group,
            employee_id=(emp if mode == "nguoi" else None),
            may_id=f.get("may_id"), piece_rate_id=(rate.id if rate else None),
            work_name=work_name, unit=unit, unit_price=unit_price, quantity=f.get("quantity") or 0,
            defect_qty=f.get("defect_qty") or 0, defect_cause=cause, defect_deduction=ded,
            tinh_khoan=tinh, work_date=f.get("work_date"),
            recorded_by=getattr(actor, "id", None), note=f.get("note"),
        )

    def update(self, output_id, *, can_set_tinh_khoan=False, **f):
        o = self.outputs.get(output_id)
        if o is None:
            raise OutputNotFound("Không tìm thấy phiếu sản lượng.")
        data = {k: v for k, v in f.items() if v is not None}
        if "tinh_khoan" in data:
            order = self.outputs.get_order(o.production_order_id)
            is_bu = getattr(order, "order_kind", "thuong") == "bu" if order else False
            if is_bu and data["tinh_khoan"] and not can_set_tinh_khoan:
                raise OutputValidationError("Chỉ HCNS được bật 'tính khoán' cho lệnh sản xuất bù.")
        cause = data.get("defect_cause", o.defect_cause)
        if cause and cause not in DEFECT_CAUSES:
            raise OutputValidationError("Nguyên nhân hỏng không hợp lệ.")
        # Tính lại trừ lỗi khi đổi SL/hỏng/nguyên nhân/đơn giá.
        cd = self.cong_doan.find_by_ma(o.cong_doan)
        qty = data.get("quantity", o.quantity)
        dqty = data.get("defect_qty", o.defect_qty)
        price = data.get("unit_price", o.unit_price)
        if cd is not None:
            data["defect_deduction"] = self._deduction(cd, qty, dqty, cause, price)
        return self.outputs.update(o, **data)

    def delete(self, output_id):
        o = self.outputs.get(output_id)
        if o is None:
            raise OutputNotFound("Không tìm thấy phiếu sản lượng.")
        self.outputs.delete(o)

    def defect_report(self, year, month) -> list[dict]:
        """Tổng hợp tỉ lệ hỏng theo NGƯỜI (ghi_theo=nguoi) / TỔ (ghi_theo=to) của 1 kỳ — chống nhờn."""
        agg: dict[tuple, dict] = {}
        for o in self.outputs.list_by_period(year, month):
            if o.ghi_theo == "nguoi":
                key = ("nguoi", o.employee_id)
            else:
                key = ("to", o.group_name)
            a = agg.setdefault(key, {
                "scope": key[0], "employee_id": o.employee_id if key[0] == "nguoi" else None,
                "group_name": o.group_name, "quantity": 0.0, "defect_qty": 0.0, "deduction": 0.0,
            })
            a["quantity"] += float(o.quantity or 0)
            a["defect_qty"] += float(o.defect_qty or 0)
            a["deduction"] += float(o.defect_deduction or 0)
        rows = []
        for a in agg.values():
            total = a["quantity"] + a["defect_qty"]
            a["defect_rate"] = round(a["defect_qty"] / total, 4) if total > 0 else 0.0
            rows.append(a)
        rows.sort(key=lambda r: r["defect_rate"], reverse=True)
        return rows
