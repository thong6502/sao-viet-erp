"""Machine Service — Máy móc & Đơn giá giờ máy (full spec A–G).

Giá giờ máy được versioned qua MachineRate (effective-date). Thông số máy (khổ/tốc độ/setup)
là dữ kiện vật lý — sửa tại chỗ, NHƯNG nếu máy đã dùng trong báo giá snapshot (used_count>0)
thì KHÓA sửa các thông số ẢNH HƯỞNG TÍNH GIÁ (đổi giá phải qua bản ghi đơn giá mới). Không
xóa vật lý máy đã dùng.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from ..models.machine import MACHINE_GROUPS, MACHINE_STATUSES, ROUNDING_POLICIES
from ..repositories.audit_repo import AuditLogRepository
from ..repositories.machine_repo import MachineRepository

VALID_MACHINE_TYPES = {"offset", "digital", "large_format", "flexo", "other"}
VALID_PROCESS_TYPES = {"in", "can_mang", "be", "gap", "dong_cuon", "dong_goi", "xen", "other"}

# Thông số ảnh hưởng tính giá — khóa sửa khi used_count>0.
_CALC_FIELDS = (
    "speed", "setup_time_mins", "changeover_time_mins",
    "setup_time_base_hour", "setup_time_per_color_hour", "setup_time_per_side_hour",
    "cleaning_time_hour", "color_change_time_hour", "plate_change_time_per_plate_hour",
    "color_check_time_hour", "min_setup_time_hour", "max_setup_time_hour",
    "max_width_cm", "max_height_cm", "min_width_cm", "min_height_cm",
    "max_print_width_cm", "max_print_height_cm", "gripper_cm",
    "side_margin_cm", "top_bottom_margin_cm", "rounding_hour_policy",
)
_ASSIGNABLE = (
    "name", "machine_type", "process_type", "machine_group", "status", "note",
    "speed", "speed_unit", "min_speed", "max_speed",
    "max_width_cm", "max_height_cm", "min_width_cm", "min_height_cm",
    "max_print_width_cm", "max_print_height_cm", "gripper_cm", "side_margin_cm",
    "top_bottom_margin_cm",
    "setup_time_mins", "changeover_time_mins", "setup_waste_sheets",
    "setup_time_base_hour", "setup_time_per_color_hour", "setup_time_per_side_hour",
    "cleaning_time_hour", "color_change_time_hour", "plate_change_time_per_plate_hour",
    "color_check_time_hour", "min_setup_time_hour", "max_setup_time_hour",
    "rounding_hour_policy", "overhead_included", "operator_included",
    "num_ink_units", "supports_perfecting", "supported_materials", "is_active",
)


class MachineError(Exception):
    pass


class MachineValidationError(MachineError):
    pass


class MachineDuplicate(MachineError):
    pass


class MachineNotFound(MachineError):
    pass


def _norm(v):
    if isinstance(v, Decimal):
        return float(v)
    if isinstance(v, list):
        return tuple(v)
    return v


class MachineService:
    def __init__(self, repo: MachineRepository, audit: AuditLogRepository) -> None:
        self.repo = repo
        self.audit = audit

    # -- validation --------------------------------------------------------
    def _validate(self, data: dict, *, require_code: bool = False) -> None:
        if not (data.get("name") or "").strip():
            raise MachineValidationError("Tên máy không được trống.")
        if data.get("machine_type") not in VALID_MACHINE_TYPES:
            raise MachineValidationError("Loại máy không hợp lệ.")
        if data.get("process_type") not in VALID_PROCESS_TYPES:
            raise MachineValidationError("Phương thức gia công không hợp lệ.")
        if data.get("machine_group") not in MACHINE_GROUPS:
            raise MachineValidationError("Nhóm máy không hợp lệ.")
        if data.get("status") not in MACHINE_STATUSES:
            raise MachineValidationError("Trạng thái máy không hợp lệ.")
        if data.get("rounding_hour_policy", "none") not in ROUNDING_POLICIES:
            raise MachineValidationError("Chính sách làm tròn giờ không hợp lệ.")
        if not (data.get("speed") or 0) > 0:
            raise MachineValidationError("Tốc độ chuẩn phải lớn hơn 0.")
        if not (data.get("speed_unit") or "").strip():
            raise MachineValidationError("Đơn vị tốc độ không được trống.")

        # khổ giấy min ≤ max
        mnw, mxw = data.get("min_width_cm"), data.get("max_width_cm")
        mnh, mxh = data.get("min_height_cm"), data.get("max_height_cm")
        if mnw is not None and mxw is not None and mnw > mxw:
            raise MachineValidationError("Khổ rộng tối thiểu không được lớn hơn khổ rộng tối đa.")
        if mnh is not None and mxh is not None and mnh > mxh:
            raise MachineValidationError("Khổ cao tối thiểu không được lớn hơn khổ cao tối đa.")
        # khổ IN không vượt khổ giấy tối đa
        pw, ph = data.get("max_print_width_cm"), data.get("max_print_height_cm")
        if pw is not None and mxw is not None and pw > mxw:
            raise MachineValidationError("Khổ in tối đa không được lớn hơn khổ giấy tối đa.")
        if ph is not None and mxh is not None and ph > mxh:
            raise MachineValidationError("Khổ in tối đa không được lớn hơn khổ giấy tối đa.")
        # tốc độ dải
        smn, smx = data.get("min_speed"), data.get("max_speed")
        if smn is not None and smx is not None and smn > smx:
            raise MachineValidationError("Tốc độ tối thiểu không được lớn hơn tốc độ tối đa.")
        # setup min ≤ max
        stmn, stmx = data.get("min_setup_time_hour"), data.get("max_setup_time_hour")
        if stmn is not None and stmx is not None and stmn > stmx:
            raise MachineValidationError("Min setup time không được lớn hơn max setup time.")
        # không âm
        for f in ("gripper_cm", "side_margin_cm", "top_bottom_margin_cm", "setup_waste_sheets",
                  "setup_time_mins", "changeover_time_mins", *[c for c in _CALC_FIELDS if c.endswith("_hour")]):
            v = data.get(f)
            if v is not None and v < 0:
                raise MachineValidationError(f"Giá trị '{f}' không được âm.")

    def _assignable(self, data: dict) -> dict:
        out = {}
        for k in _ASSIGNABLE:
            if k in data:
                v = data[k]
                if k == "note":
                    v = v.strip() if isinstance(v, str) and v.strip() else None
                out[k] = v
        # is_active suy từ status (maintenance/inactive ⇒ không chọn được ở phiếu mới).
        if "status" in data:
            out["is_active"] = data["status"] == "active"
        return out

    def _calc_signature(self, get) -> tuple:
        return tuple(_norm(get(f)) for f in _CALC_FIELDS)

    # -- reads -------------------------------------------------------------
    def list_machines(self, *, q=None, machine_type=None, machine_group=None,
                      is_active=None, sort="code", page=1, size=20):
        return self.repo.list(
            q=q, machine_type=machine_type, machine_group=machine_group,
            is_active=is_active, sort=sort, page=page, size=size,
        )

    def get_machine(self, machine_id: int):
        machine = self.repo.get_by_id(machine_id)
        if machine is None:
            raise MachineNotFound("Không tìm thấy máy.")
        return machine

    # -- writes ------------------------------------------------------------
    def create_machine(self, data: dict, *, actor):
        self._validate(data)
        if self.repo.find_by_name(data["name"].strip()) is not None:
            raise MachineDuplicate("Tên máy đã tồn tại.")
        code = (data.get("code") or "").strip().upper()
        if code and self.repo.get_by_code(code) is not None:
            raise MachineDuplicate("Mã máy đã tồn tại.")
        fields = self._assignable(data)
        if code:
            fields["code"] = code
        fields["name"] = data["name"].strip()
        fields["speed_unit"] = data["speed_unit"].strip()
        fields["created_by"] = getattr(actor, "id", None)
        fields["updated_by"] = getattr(actor, "id", None)
        machine = self.repo.create(**fields)
        self.audit.create(
            actor_user_id=actor.id, action="create_machine",
            target=f"machine:{machine.id}",
            detail=f"{machine.code} - {machine.name} ({machine.machine_type})",
        )
        return machine

    def update_machine(self, machine_id: int, data: dict, *, actor):
        machine = self.get_machine(machine_id)
        self._validate(data)
        dup = self.repo.find_by_name(data["name"].strip())
        if dup is not None and dup.id != machine.id:
            raise MachineDuplicate("Tên máy đã tồn tại.")

        # Khóa sửa thông số ảnh hưởng tính giá khi máy đã dùng trong báo giá.
        if int(getattr(machine, "used_count", 0) or 0) > 0:
            if self._calc_signature(machine.__getattribute__) != self._calc_signature(
                lambda f: data.get(f)
            ):
                raise MachineValidationError(
                    "Máy đã dùng trong báo giá — không sửa trực tiếp tốc độ / khổ / thời gian setup. "
                    "Đổi đơn giá qua bản ghi đơn giá mới; thông số khác chỉ chỉnh khi máy chưa dùng."
                )

        fields = self._assignable(data)
        fields["name"] = data["name"].strip()
        fields["speed_unit"] = data["speed_unit"].strip()
        fields["updated_by"] = getattr(actor, "id", None)
        machine = self.repo.update(machine, **fields)
        self.audit.create(
            actor_user_id=actor.id, action="update_machine",
            target=f"machine:{machine.id}", detail=f"{machine.code} - {machine.name}",
        )
        return machine

    def delete_machine(self, *, machine_id: int, actor) -> None:
        machine = self.get_machine(machine_id)
        if int(getattr(machine, "used_count", 0) or 0) > 0:
            raise MachineValidationError(
                "Không thể xóa máy đã dùng trong báo giá — hãy đặt trạng thái Ngưng/ Bảo trì thay vì xóa."
            )
        code, name = machine.code, machine.name
        self.repo.delete(machine)
        self.audit.create(
            actor_user_id=actor.id, action="delete_machine",
            target=f"machine:{machine_id}", detail=f"{code} {name}",
        )

    def add_machine_rate(self, *, machine_id: int, hourly_rate: int, min_charge: int = 0,
                        min_run_time_mins: int = 0, rate_depreciation: int = 0, rate_energy: int = 0,
                        rate_maintenance: int = 0, rate_labor: int = 0, rate_overhead: int = 0,
                        effective_from: date, actor):
        machine = self.get_machine(machine_id)
        if hourly_rate < 0:
            raise MachineValidationError("Đơn giá giờ máy không được âm.")
        if min_charge < 0:
            raise MachineValidationError("Phí tối thiểu không được âm.")
        if min_run_time_mins < 0:
            raise MachineValidationError("Thời gian chạy tối thiểu không được âm.")

        current = self.repo.get_current_rate(machine_id)
        if current and effective_from <= current.effective_from:
            raise MachineValidationError(
                f"Ngày hiệu lực mới phải sau ngày hiệu lực của bảng giá hiện hành ({current.effective_from})."
            )
        for rate in machine.rates:
            if rate.effective_to is not None and rate.effective_from <= effective_from <= rate.effective_to:
                raise MachineValidationError(
                    f"Ngày hiệu lực bị chồng lấn với bảng giá cũ từ {rate.effective_from} đến {rate.effective_to}."
                )

        rate = self.repo.add_machine_rate(
            machine_id=machine_id, hourly_rate=hourly_rate, min_charge=min_charge,
            min_run_time_mins=min_run_time_mins, rate_depreciation=rate_depreciation,
            rate_energy=rate_energy, rate_maintenance=rate_maintenance, rate_labor=rate_labor,
            rate_overhead=rate_overhead, effective_from=effective_from,
        )
        self.audit.create(
            actor_user_id=actor.id, action="add_machine_rate", target=f"machine:{machine.id}",
            detail=f"Đơn giá giờ máy mới: {hourly_rate} VND/h từ {effective_from}",
        )
        return rate
