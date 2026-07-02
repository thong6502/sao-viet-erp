"""Operation Service — spec-20/21.
"""
from __future__ import annotations

from datetime import date, datetime
from sqlalchemy import select
from ..models.operation import Operation, OperationRate
from ..models.costing import CostingOperation
from ..repositories.audit_repo import AuditLogRepository
from ..repositories.operation_repo import OperationRepository

VALID_OPERATION_TYPES = {
    "in",
    "can_mang",
    "be",
    "gap",
    "dong_cuon",
    "dong_goi",
    "other",
}

class OperationError(Exception):
    pass

class OperationValidationError(OperationError):
    pass

class OperationDuplicate(OperationError):
    pass

class OperationNotFound(OperationError):
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
    ) -> None:
        if not name.strip():
            raise OperationValidationError("Tên công đoạn không được trống.")
        
        if operation_type not in VALID_OPERATION_TYPES:
            raise OperationValidationError("Loại công đoạn không hợp lệ.")

        if not unit.strip():
            raise OperationValidationError("Đơn vị tính không được trống.")

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
        allow_outsource: bool = False,
        is_active: bool = True,
        actor,
    ) -> Operation:
        self._validate(
            name=name,
            operation_type=operation_type,
            unit=unit,
        )
        if self.repo.find_by_name(name) is not None:
            raise OperationDuplicate("Tên công đoạn đã tồn tại.")

        operation = self.repo.create(
            name=name.strip(),
            operation_type=operation_type,
            unit=unit.strip(),
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
        allow_outsource: bool,
        is_active: bool | None = None,
        actor,
    ) -> Operation:
        operation = self.get_operation(operation_id)
        self._validate(
            name=name,
            operation_type=operation_type,
            unit=unit,
        )
        dup = self.repo.find_by_name(name)
        if dup is not None and dup.id != operation.id:
            raise OperationDuplicate("Tên công đoạn đã tồn tại.")

        operation = self.repo.update(
            operation,
            name=name.strip(),
            operation_type=operation_type,
            unit=unit.strip(),
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
        operation = self.get_operation(operation_id)
        
        # Check if used in costing operation
        # Note: CostingOperation at P0 does not store operation_id yet; keep this hook for pricing engine phase.
        pass

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
        setup_fee: int = 0,
        run_rate: int = 0,
        labor_rate: int = 0,
        min_charge: int = 0,
        speed: float = 0.0,
        effective_from: date,
        actor,
    ) -> OperationRate:
        operation = self.get_operation(operation_id)
        if setup_fee < 0:
            raise OperationValidationError("Phí setup không được âm.")
        if run_rate < 0:
            raise OperationValidationError("Đơn giá chạy máy không được âm.")
        if labor_rate < 0:
            raise OperationValidationError("Đơn giá nhân công không được âm.")
        if min_charge < 0:
            raise OperationValidationError("Phí tối thiểu không được âm.")
        if speed < 0:
            raise OperationValidationError("Tốc độ chạy không được âm.")

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
            setup_fee=setup_fee,
            run_rate=run_rate,
            labor_rate=labor_rate,
            min_charge=min_charge,
            speed=speed,
            effective_from=effective_from,
        )
        self.audit.create(
            actor_user_id=actor.id,
            action="add_operation_rate",
            target=f"operation:{operation.id}",
            detail=f"Cấu hình bảng giá công đoạn mới từ {effective_from}",
        )
        return rate
