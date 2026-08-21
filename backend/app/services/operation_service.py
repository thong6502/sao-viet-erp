"""Operation Service — spec-20/21 + spec §A–§G (Công đoạn & Đơn giá gia công).
"""
from __future__ import annotations

from datetime import date
from sqlalchemy import func, select
from ..models.operation import Operation, OperationRate
from ..repositories.audit_repo import AuditLogRepository
from ..repositories.operation_repo import OperationRepository

VALID_OPERATION_TYPES = {
    "in",
    "can_mang",
    "be",
    "boi",
    "ep_kim",
    "dap_noi",
    "uv",
    "gap",
    "dong_cuon",
    "dan_hop",
    "xen",
    "dong_goi",
    "other",
}

# §2.2 — cơ sở tính lượng (engine nhân run_rate) và hình thức tính công (mục 14 / spec §D).
VALID_BASIS_QUANTITIES = {"m2", "to", "luot", "cm2", "cuon", "cai", "thung", "kg"}
VALID_PRICING_METHODS = {"none", "theo_gio", "theo_ca", "theo_sp", "khoan"}
# spec §A / §B / §C / §F
VALID_PROCESS_GROUPS = {"sau_in", "dong_goi", "dac_biet"}
VALID_PROCESS_TYPES = {"internal", "outsource", "both"}
VALID_INTERNAL_PRICING = {"per_qty", "per_hour", "combined"}
VALID_QTY_FORMULA = {
    "print_sheet_qty",
    "finished_qty",
    "area_m2",
    "linear_meter",
    "book_qty",
    "box_qty",
    "pack_qty",
    "manual",
}
VALID_TOOLING_TYPES = {"khuon_be", "khuon_ep_kim", "khuon_dap_noi", "other"}

class OperationError(Exception):
    pass

class OperationValidationError(OperationError):
    pass

class OperationDuplicate(OperationError):
    pass

class OperationNotFound(OperationError):
    pass

class OperationInUse(OperationError):
    pass

class OperationService:
    def __init__(
        self,
        repo: OperationRepository,
        audit: AuditLogRepository,
    ) -> None:
        self.repo = repo
        self.audit = audit

    def _validate(
        self,
        *,
        name: str,
        operation_type: str,
        unit: str,
        basis_quantity: str,
        pricing_method: str,
        process_group: str = "sau_in",
        process_type: str = "internal",
        internal_pricing_method: str = "per_qty",
        quantity_formula_type: str = "print_sheet_qty",
        has_tooling: bool = False,
        tooling_type: str | None = None,
    ) -> None:
        if not name.strip():
            raise OperationValidationError("Tên công đoạn không được trống.")

        if operation_type not in VALID_OPERATION_TYPES:
            raise OperationValidationError("Loại công đoạn không hợp lệ.")

        if not unit.strip():
            raise OperationValidationError("Đơn vị tính không được trống.")

        if basis_quantity not in VALID_BASIS_QUANTITIES:
            raise OperationValidationError("Cơ sở tính lượng (basis) không hợp lệ.")

        if pricing_method not in VALID_PRICING_METHODS:
            raise OperationValidationError("Hình thức tính công (pricing method) không hợp lệ.")

        if process_group not in VALID_PROCESS_GROUPS:
            raise OperationValidationError("Nhóm công đoạn không hợp lệ.")

        if process_type not in VALID_PROCESS_TYPES:
            raise OperationValidationError("Loại xử lý (nội bộ/thuê ngoài/cả hai) không hợp lệ.")

        if internal_pricing_method not in VALID_INTERNAL_PRICING:
            raise OperationValidationError("Cách tính nội bộ không hợp lệ.")

        if quantity_formula_type not in VALID_QTY_FORMULA:
            raise OperationValidationError("Công thức lượng tính không hợp lệ.")

        # spec §7 — có khuôn thì phải chọn loại khuôn (Error).
        if has_tooling:
            if not tooling_type:
                raise OperationValidationError("Công đoạn có phát sinh khuôn thì phải chọn loại khuôn.")
            if tooling_type not in VALID_TOOLING_TYPES:
                raise OperationValidationError("Loại khuôn không hợp lệ.")

    @staticmethod
    def _resolve_outsource(process_type: str, allow_outsource: bool) -> tuple[str, bool]:
        """Hòa hợp process_type (mới) với cờ allow_outsource (cũ, backward-compat).

        Caller cũ chỉ gửi allow_outsource → suy ra 'both'. Caller mới gửi process_type →
        allow_outsource được dẫn xuất lại cho nhất quán.
        """
        pt = process_type
        if pt == "internal" and allow_outsource:
            pt = "both"
        return pt, pt in ("outsource", "both")

    def list_operations(
        self,
        *,
        q: str | None = None,
        operation_type: str | None = None,
        is_active: bool | None = None,
        sort: str = "code",
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[Operation], int]:
        return self.repo.list(
            q=q, operation_type=operation_type, is_active=is_active, sort=sort, page=page, size=size
        )

    def get_operation(self, operation_id: int) -> Operation:
        operation = self.repo.get_by_id(operation_id)
        if operation is None:
            raise OperationNotFound("Không tìm thấy công đoạn.")
        return operation

    def create_operation(
        self,
        *,
        name: str,
        operation_type: str,
        unit: str,
        basis_quantity: str = "to",
        pricing_method: str = "theo_sp",
        process_group: str = "sau_in",
        process_type: str = "internal",
        default_sequence: int = 0,
        quantity_formula_type: str = "print_sheet_qty",
        allow_manual_quantity: bool = False,
        internal_pricing_method: str = "per_qty",
        labor_people_count: float = 1.0,
        has_tooling: bool = False,
        tooling_type: str | None = None,
        tooling_rate_id: int | None = None,
        has_yield_loss: bool = False,
        default_yield_rate: float | None = None,
        default_yield_rule: str | None = None,
        allow_outsource: bool = False,
        is_active: bool = True,
        actor,
    ) -> Operation:
        self._validate(
            name=name,
            operation_type=operation_type,
            unit=unit,
            basis_quantity=basis_quantity,
            pricing_method=pricing_method,
            process_group=process_group,
            process_type=process_type,
            internal_pricing_method=internal_pricing_method,
            quantity_formula_type=quantity_formula_type,
            has_tooling=has_tooling,
            tooling_type=tooling_type,
        )
        if self.repo.find_by_name(name) is not None:
            raise OperationDuplicate("Tên công đoạn đã tồn tại.")

        process_type, allow_outsource = self._resolve_outsource(process_type, allow_outsource)

        operation = self.repo.create(
            name=name.strip(),
            operation_type=operation_type,
            unit=unit.strip(),
            basis_quantity=basis_quantity,
            pricing_method=pricing_method,
            process_group=process_group,
            process_type=process_type,
            default_sequence=default_sequence,
            quantity_formula_type=quantity_formula_type,
            allow_manual_quantity=allow_manual_quantity,
            internal_pricing_method=internal_pricing_method,
            labor_people_count=labor_people_count,
            has_tooling=has_tooling,
            tooling_type=tooling_type if has_tooling else None,
            tooling_rate_id=tooling_rate_id if has_tooling else None,
            has_yield_loss=has_yield_loss,
            default_yield_rate=default_yield_rate if has_yield_loss else None,
            default_yield_rule=(default_yield_rule if has_yield_loss else None),
            allow_outsource=allow_outsource,
            is_active=is_active,
        )
        self.audit.create(
            actor_user_id=actor.id,
            action="create_operation",
            target=f"operation:{operation.id}",
            detail=f"{operation.code} - {operation.name} ({operation_type})",
        )
        return operation

    def update_operation(
        self,
        *,
        operation_id: int,
        name: str,
        operation_type: str,
        unit: str,
        basis_quantity: str = "to",
        pricing_method: str = "theo_sp",
        process_group: str = "sau_in",
        process_type: str = "internal",
        default_sequence: int = 0,
        quantity_formula_type: str = "print_sheet_qty",
        allow_manual_quantity: bool = False,
        internal_pricing_method: str = "per_qty",
        labor_people_count: float = 1.0,
        has_tooling: bool = False,
        tooling_type: str | None = None,
        tooling_rate_id: int | None = None,
        has_yield_loss: bool = False,
        default_yield_rate: float | None = None,
        default_yield_rule: str | None = None,
        allow_outsource: bool = False,
        is_active: bool | None = None,
        actor,
    ) -> Operation:
        operation = self.get_operation(operation_id)
        self._validate(
            name=name,
            operation_type=operation_type,
            unit=unit,
            basis_quantity=basis_quantity,
            pricing_method=pricing_method,
            process_group=process_group,
            process_type=process_type,
            internal_pricing_method=internal_pricing_method,
            quantity_formula_type=quantity_formula_type,
            has_tooling=has_tooling,
            tooling_type=tooling_type,
        )
        dup = self.repo.find_by_name(name)
        if dup is not None and dup.id != operation.id:
            raise OperationDuplicate("Tên công đoạn đã tồn tại.")

        process_type, allow_outsource = self._resolve_outsource(process_type, allow_outsource)

        operation = self.repo.update(
            operation,
            name=name.strip(),
            operation_type=operation_type,
            unit=unit.strip(),
            basis_quantity=basis_quantity,
            pricing_method=pricing_method,
            process_group=process_group,
            process_type=process_type,
            default_sequence=default_sequence,
            quantity_formula_type=quantity_formula_type,
            allow_manual_quantity=allow_manual_quantity,
            internal_pricing_method=internal_pricing_method,
            labor_people_count=labor_people_count,
            has_tooling=has_tooling,
            tooling_type=tooling_type if has_tooling else None,
            tooling_rate_id=tooling_rate_id if has_tooling else None,
            has_yield_loss=has_yield_loss,
            default_yield_rate=default_yield_rate if has_yield_loss else None,
            default_yield_rule=(default_yield_rule if has_yield_loss else None),
            allow_outsource=allow_outsource,
            is_active=is_active,
        )
        self.audit.create(
            actor_user_id=actor.id,
            action="update_operation",
            target=f"operation:{operation.id}",
            detail=f"{operation.code} - {operation.name}",
        )
        return operation

    def delete_operation(self, *, operation_id: int, actor) -> None:
        # spec §7 (guard "đã dùng trong snapshot báo giá") ĐÃ GỠ 2026-08-08 — Đợt 5: nguồn dữ liệu
        # duy nhất của guard là `EstimateCostLine.source_type='operation_rates'`, mà cụm tính giá
        # đời cũ đã xoá hẳn. Engine đang chạy (thanh_phan_engine) KHÔNG ghi tham chiếu ngược tới
        # `operation_rates`, nên không có gì để kiểm. Dựng lại guard khi engine mới có vết dùng.
        operation = self.get_operation(operation_id)

        code, name = operation.code, operation.name
        self.repo.delete(operation)
        self.audit.create(
            actor_user_id=actor.id,
            action="delete_operation",
            target=f"operation:{operation_id}",
            detail=f"{code} {name}",
        )

    def add_operation_rate(
        self,
        *,
        operation_id: int,
        effective_from: date,
        actor,
        **prices,
    ) -> OperationRate:
        operation = self.get_operation(operation_id)
        for key, val in prices.items():
            if isinstance(val, (int, float)) and val < 0:
                raise OperationValidationError(f"Giá trị '{key}' không được âm.")

        # spec §7 — tính theo giờ máy thì tốc độ chuẩn phải > 0.
        if operation.internal_pricing_method in ("per_hour", "combined"):
            if float(prices.get("speed", 0) or 0) <= 0:
                raise OperationValidationError(
                    "Cách tính nội bộ theo giờ máy yêu cầu Tốc độ chuẩn > 0."
                )

        current = self.repo.get_current_rate(operation_id)
        if current and effective_from <= current.effective_from:
            raise OperationValidationError(
                f"Ngày hiệu lực mới phải sau ngày hiệu lực của bảng giá hiện hành ({current.effective_from})."
            )

        for rate in operation.rates:
            if rate.effective_to is not None:
                if rate.effective_from <= effective_from <= rate.effective_to:
                    raise OperationValidationError(
                        f"Ngày hiệu lực bị chồng lấn với bảng giá cũ từ {rate.effective_from} đến {rate.effective_to}."
                    )

        rate = self.repo.add_operation_rate(
            operation_id=operation_id,
            effective_from=effective_from,
            **prices,
        )
        self.audit.create(
            actor_user_id=actor.id,
            action="add_operation_rate",
            target=f"operation:{operation.id}",
            detail=f"Cấu hình bảng giá công đoạn mới từ {effective_from}",
        )
        return rate

    # --- Test nhanh công thức (spec §4.7) --------------------------------
    def preview_cost(self, *, operation_id: int, preview) -> dict:
        """Mô phỏng chi phí 1 công đoạn theo lượng nhập & cách làm — cùng công thức với engine."""
        operation = self.get_operation(operation_id)
        rate = self.repo.get_current_rate(operation_id)
        warnings: list[str] = []
        components: list[dict] = []

        qty = self._resolve_preview_qty(operation, preview)

        if preview.execution_mode == "outsourced":
            if rate is None or (rate.outsource_unit_price == 0 and rate.outsource_min_charge == 0):
                warnings.append("Chưa cấu hình bảng giá thuê ngoài cho công đoạn này.")
            up = float(rate.outsource_unit_price) if rate else 0.0
            setup = float(rate.outsource_setup_fee) if rate else 0.0
            minc = float(rate.outsource_min_charge) if rate else 0.0
            transport = float(rate.outsource_transport_fee) if rate else 0.0
            base = qty * up
            base_after_min = max(base, minc)
            components.append({
                "label": "Đơn giá NCC",
                "formula": f"max({qty:g} × {up:,.0f}, {minc:,.0f} min charge)",
                "amount": base_after_min,
            })
            if setup:
                components.append({"label": "Phí setup NCC", "formula": f"{setup:,.0f}", "amount": setup})
            if transport:
                components.append({"label": "Phí vận chuyển", "formula": f"{transport:,.0f}", "amount": transport})
            total = base_after_min + setup + transport
        else:
            total, components, warnings2 = self._preview_internal(operation, rate, qty)
            warnings.extend(warnings2)

        return {
            "operation_name": operation.name,
            "execution_mode": preview.execution_mode,
            "quantity": qty,
            "unit": operation.unit,
            "components": components,
            "total": total,
            "warnings": warnings,
        }

    @staticmethod
    def _resolve_preview_qty(operation: Operation, preview) -> float:
        f = operation.quantity_formula_type
        if operation.allow_manual_quantity and float(preview.manual_qty or 0) > 0:
            return float(preview.manual_qty)
        if f == "print_sheet_qty":
            return float(preview.sheet_qty)
        if f == "finished_qty":
            return float(preview.finished_qty)
        if f == "area_m2":
            return float(preview.sheet_qty) * float(preview.area_m2)
        if f == "book_qty":
            return float(preview.book_qty)
        if f in ("box_qty", "pack_qty"):
            return float(preview.finished_qty)
        return float(preview.manual_qty)

    @staticmethod
    def _preview_internal(operation: Operation, rate, qty: float) -> tuple[float, list[dict], list[str]]:
        warnings: list[str] = []
        components: list[dict] = []
        if rate is None:
            warnings.append("Chưa cấu hình biểu giá nội bộ cho công đoạn này.")
            return 0.0, components, warnings

        run_rate = float(rate.run_rate)
        hourly_rate = float(rate.hourly_rate or 0)
        setup_fee = float(rate.setup_fee or 0)
        speed = float(rate.speed or 0)
        setup_h = float(rate.setup_time_mins or 0) / 60.0
        run_h = (qty / speed) if speed > 0 else 0.0
        machine_h = setup_h + run_h

        method = operation.internal_pricing_method or "per_qty"
        run_cost = 0.0
        setup_component = 0.0
        if method == "per_hour":
            run_cost = machine_h * hourly_rate
            components.append({
                "label": "Giờ máy",
                "formula": f"({setup_h:g} + {qty:g}/{speed:g}) × {hourly_rate:,.0f}",
                "amount": run_cost,
            })
        elif method == "combined":
            m_cost = machine_h * hourly_rate
            q_cost = qty * run_rate
            run_cost = m_cost + q_cost
            setup_component = setup_fee
            components.append({"label": "Phí setup", "formula": f"{setup_fee:,.0f}", "amount": setup_fee})
            components.append({
                "label": "Giờ máy",
                "formula": f"({setup_h:g} + {qty:g}/{speed:g}) × {hourly_rate:,.0f}",
                "amount": m_cost,
            })
            components.append({"label": "Sản lượng", "formula": f"{qty:g} × {run_rate:,.0f}", "amount": q_cost})
        else:  # per_qty
            run_cost = qty * run_rate
            setup_component = setup_fee
            if setup_fee:
                components.append({"label": "Phí setup", "formula": f"{setup_fee:,.0f}", "amount": setup_fee})
            components.append({"label": "Sản lượng", "formula": f"{qty:g} × {run_rate:,.0f}", "amount": run_cost})

        # Nhân công đa hình thức — spec §D
        labor_cost = OperationService._labor_cost(operation, rate, qty, machine_h)
        if labor_cost > 0:
            components.append({"label": "Nhân công", "formula": OperationService._labor_formula(operation, rate, qty, machine_h), "amount": labor_cost})

        # Khuôn — spec §F
        tooling_cost = 0.0
        if operation.has_tooling and rate.tooling_unit_price:
            tooling_cost = float(rate.tooling_unit_price)
            components.append({"label": "Khuôn", "formula": f"{tooling_cost:,.0f}", "amount": tooling_cost})

        total = run_cost + setup_component + labor_cost + tooling_cost

        min_charge = float(rate.min_charge or 0)
        if total < min_charge:
            components.append({"label": "Áp phí tối thiểu", "formula": f"min charge {min_charge:,.0f}", "amount": min_charge - total})
            total = min_charge

        return total, components, warnings

    @staticmethod
    def _labor_cost(operation: Operation, rate, qty: float, machine_h: float) -> float:
        lp = operation.pricing_method or "theo_sp"
        people = float(operation.labor_people_count or 1)
        labor_rate = float(rate.labor_rate or 0)
        if lp == "none":
            return 0.0
        if lp == "theo_gio":
            cost = people * machine_h * labor_rate
        elif lp == "theo_ca":
            cost = float(rate.labor_shift_rate or 0)
        elif lp == "khoan":
            cost = float(rate.labor_fixed or 0)
        else:  # theo_sp
            cost = qty * labor_rate
        labor_min = float(rate.labor_min or 0)
        return max(cost, labor_min)

    @staticmethod
    def _labor_formula(operation: Operation, rate, qty: float, machine_h: float) -> str:
        lp = operation.pricing_method or "theo_sp"
        people = float(operation.labor_people_count or 1)
        labor_rate = float(rate.labor_rate or 0)
        if lp == "theo_gio":
            return f"{people:g} người × {machine_h:.3f} giờ × {labor_rate:,.0f}"
        if lp == "theo_ca":
            return f"1 ca × {float(rate.labor_shift_rate or 0):,.0f}"
        if lp == "khoan":
            return f"khoán {float(rate.labor_fixed or 0):,.0f}"
        return f"{qty:g} × {labor_rate:,.0f}"
