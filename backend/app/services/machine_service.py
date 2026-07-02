"""Machine Service — spec-20/21.
"""
from __future__ import annotations

from datetime import date, datetime
from sqlalchemy import select
from ..models.machine import Machine, MachineRate
from ..models.costing import CostingOperation
from ..repositories.audit_repo import AuditLogRepository
from ..repositories.machine_repo import MachineRepository

VALID_MACHINE_TYPES = {"offset", "digital", "large_format", "flexo", "other"}
VALID_PROCESS_TYPES = {"in", "can_mang", "be", "gap", "dong_cuon", "dong_goi", "other"}

class MachineError(Exception):
    pass

class MachineValidationError(MachineError):
    pass

class MachineDuplicate(MachineError):
    pass

class MachineNotFound(MachineError):
    pass

class MachineService:
    def __init__(
        self,
        repo: MachineRepository,
        audit: AuditLogRepository,
    ) -> None:
        self.repo = repo
        self.audit = audit

    def _validate(
        self,
        *,
        name: str,
        machine_type: str,
        process_type: str,
        speed: float,
        speed_unit: str,
        max_width_cm: float | None,
        max_height_cm: float | None,
        min_width_cm: float | None,
        min_height_cm: float | None,
        setup_time_mins: int,
        changeover_time_mins: int,
        setup_waste_sheets: float,
    ) -> None:
        if not name.strip():
            raise MachineValidationError("Tên máy không được trống.")
        
        if machine_type not in VALID_MACHINE_TYPES:
            raise MachineValidationError("Loại máy không hợp lệ.")

        if process_type not in VALID_PROCESS_TYPES:
            raise MachineValidationError("Phương thức gia công không hợp lệ.")

        if speed <= 0:
            raise MachineValidationError("Tốc độ máy phải lớn hơn 0.")

        if not speed_unit.strip():
            raise MachineValidationError("Đơn vị tốc độ không được trống.")

        # Range checks
        if max_width_cm is not None and max_width_cm < 0:
            raise MachineValidationError("Khổ rộng tối đa không được âm.")
        if max_height_cm is not None and max_height_cm < 0:
            raise MachineValidationError("Khổ cao tối đa không được âm.")
        if min_width_cm is not None and min_width_cm < 0:
            raise MachineValidationError("Khổ rộng tối thiểu không được âm.")
        if min_height_cm is not None and min_height_cm < 0:
            raise MachineValidationError("Khổ cao tối thiểu không được âm.")

        # Logic checks
        if max_width_cm is not None and min_width_cm is not None and min_width_cm > max_width_cm:
            raise MachineValidationError("Khổ rộng tối thiểu không được lớn hơn khổ rộng tối đa.")
        if max_height_cm is not None and min_height_cm is not None and min_height_cm > max_height_cm:
            raise MachineValidationError("Khổ cao tối thiểu không được lớn hơn khổ cao tối đa.")

        if setup_time_mins < 0:
            raise MachineValidationError("Thời gian setup không được âm.")
        if changeover_time_mins < 0:
            raise MachineValidationError("Thời gian chuyển đổi không được âm.")
        if setup_waste_sheets < 0:
            raise MachineValidationError("Hao hụt setup không được âm.")

    def list_machines(
        self,
        *,
        q: str | None = None,
        machine_type: str | None = None,
        is_active: bool | None = None,
        sort: str = "code",
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[Machine], int]:
        return self.repo.list(
            q=q, machine_type=machine_type, is_active=is_active, sort=sort, page=page, size=size
        )

    def get_machine(self, machine_id: int) -> Machine:
        machine = self.repo.get_by_id(machine_id)
        if machine is None:
            raise MachineNotFound("Không tìm thấy máy.")
        return machine

    def create_machine(
        self,
        *,
        name: str,
        machine_type: str,
        process_type: str,
        speed: float,
        speed_unit: str,
        max_width_cm: float | None = None,
        max_height_cm: float | None = None,
        min_width_cm: float | None = None,
        min_height_cm: float | None = None,
        setup_time_mins: int = 0,
        changeover_time_mins: int = 0,
        setup_waste_sheets: float = 0.0,
        num_ink_units: int | None = None,
        supports_perfecting: bool = False,
        supported_materials: list[str] | None = None,
        is_active: bool = True,
        actor,
    ) -> Machine:
        self._validate(
            name=name,
            machine_type=machine_type,
            process_type=process_type,
            speed=speed,
            speed_unit=speed_unit,
            max_width_cm=max_width_cm,
            max_height_cm=max_height_cm,
            min_width_cm=min_width_cm,
            min_height_cm=min_height_cm,
            setup_time_mins=setup_time_mins,
            changeover_time_mins=changeover_time_mins,
            setup_waste_sheets=setup_waste_sheets,
        )
        if self.repo.find_by_name(name) is not None:
            raise MachineDuplicate("Tên máy đã tồn tại.")

        machine = self.repo.create(
            name=name.strip(),
            machine_type=machine_type,
            process_type=process_type,
            speed=speed,
            speed_unit=speed_unit.strip(),
            max_width_cm=max_width_cm,
            max_height_cm=max_height_cm,
            min_width_cm=min_width_cm,
            min_height_cm=min_height_cm,
            setup_time_mins=setup_time_mins,
            changeover_time_mins=changeover_time_mins,
            setup_waste_sheets=setup_waste_sheets,
            num_ink_units=num_ink_units,
            supports_perfecting=supports_perfecting,
            supported_materials=supported_materials,
            is_active=is_active,
        )
        self.audit.create(
            actor_user_id=actor.id,
            action="create_machine",
            target=f"machine:{machine.id}",
            detail=f"{machine.code} - {machine.name} ({machine_type})",
        )
        return machine

    def update_machine(
        self,
        *,
        machine_id: int,
        name: str,
        machine_type: str,
        process_type: str,
        speed: float,
        speed_unit: str,
        max_width_cm: float | None = None,
        max_height_cm: float | None = None,
        min_width_cm: float | None = None,
        min_height_cm: float | None = None,
        setup_time_mins: int = 0,
        changeover_time_mins: int = 0,
        setup_waste_sheets: float = 0.0,
        num_ink_units: int | None = None,
        supports_perfecting: bool = False,
        supported_materials: list[str] | None = None,
        is_active: bool | None = None,
        actor,
    ) -> Machine:
        machine = self.get_machine(machine_id)
        self._validate(
            name=name,
            machine_type=machine_type,
            process_type=process_type,
            speed=speed,
            speed_unit=speed_unit,
            max_width_cm=max_width_cm,
            max_height_cm=max_height_cm,
            min_width_cm=min_width_cm,
            min_height_cm=min_height_cm,
            setup_time_mins=setup_time_mins,
            changeover_time_mins=changeover_time_mins,
            setup_waste_sheets=setup_waste_sheets,
        )
        dup = self.repo.find_by_name(name)
        if dup is not None and dup.id != machine.id:
            raise MachineDuplicate("Tên máy đã tồn tại.")

        machine = self.repo.update(
            machine,
            name=name.strip(),
            machine_type=machine_type,
            process_type=process_type,
            speed=speed,
            speed_unit=speed_unit.strip(),
            max_width_cm=max_width_cm,
            max_height_cm=max_height_cm,
            min_width_cm=min_width_cm,
            min_height_cm=min_height_cm,
            setup_time_mins=setup_time_mins,
            changeover_time_mins=changeover_time_mins,
            setup_waste_sheets=setup_waste_sheets,
            num_ink_units=num_ink_units,
            supports_perfecting=supports_perfecting,
            supported_materials=supported_materials,
            is_active=is_active,
        )
        self.audit.create(
            actor_user_id=actor.id,
            action="update_machine",
            target=f"machine:{machine.id}",
            detail=f"{machine.code} - {machine.name}",
        )
        return machine

    def delete_machine(self, *, machine_id: int, actor) -> None:
        machine = self.get_machine(machine_id)
        
        # Check if used in costing operation
        # Note: CostingOperation at P0 does not store machine_id yet; keep this hook for pricing engine phase.
        pass

        code, name = machine.code, machine.name
        self.repo.delete(machine)
        self.audit.create(
            actor_user_id=actor.id,
            action="delete_machine",
            target=f"machine:{machine_id}",
            detail=f"{code} {name}",
        )

    def add_machine_rate(
        self,
        *,
        machine_id: int,
        hourly_rate: int,
        min_charge: int = 0,
        min_run_time_mins: int = 0,
        effective_from: date,
        actor,
    ) -> MachineRate:
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
            if rate.effective_to is not None:
                if rate.effective_from <= effective_from <= rate.effective_to:
                    raise MachineValidationError(
                        f"Ngày hiệu lực bị chồng lấn với bảng giá cũ từ {rate.effective_from} đến {rate.effective_to}."
                    )

        rate = self.repo.add_machine_rate(
            machine_id=machine_id,
            hourly_rate=hourly_rate,
            min_charge=min_charge,
            min_run_time_mins=min_run_time_mins,
            effective_from=effective_from,
        )
        self.audit.create(
            actor_user_id=actor.id,
            action="add_machine_rate",
            target=f"machine:{machine.id}",
            detail=f"Cấu hình giá giờ máy mới: {hourly_rate} VND/h từ {effective_from}",
        )
        return rate
