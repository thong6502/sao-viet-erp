"""Warehouse Service — cấu hình kho hàng (admin master data)."""
from __future__ import annotations

from ..models.warehouse import Warehouse
from ..repositories.audit_repo import AuditLogRepository
from ..repositories.warehouse_repo import WarehouseRepository


class WarehouseError(Exception):
    pass


class WarehouseValidationError(WarehouseError):
    pass


class WarehouseDuplicate(WarehouseError):
    pass


class WarehouseNotFound(WarehouseError):
    pass


class WarehouseService:
    def __init__(self, repo: WarehouseRepository, audit: AuditLogRepository) -> None:
        self.repo = repo
        self.audit = audit

    def _validate(self, *, name: str) -> None:
        if not name.strip():
            raise WarehouseValidationError("Tên kho không được trống.")

    def list_warehouses(
        self,
        *,
        q: str | None = None,
        is_active: bool | None = None,
        sort: str = "code",
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[Warehouse], int]:
        return self.repo.list(q=q, is_active=is_active, sort=sort, page=page, size=size)

    def get_warehouse(self, warehouse_id: int) -> Warehouse:
        warehouse = self.repo.get_by_id(warehouse_id)
        if warehouse is None:
            raise WarehouseNotFound("Không tìm thấy kho.")
        return warehouse

    def create_warehouse(
        self,
        *,
        name: str,
        description: str | None = None,
        notes: str | None = None,
        is_active: bool = True,
        actor,
    ) -> Warehouse:
        self._validate(name=name)
        if self.repo.find_by_name(name) is not None:
            raise WarehouseDuplicate("Tên kho đã tồn tại.")

        warehouse = self.repo.create(
            name=name.strip(),
            description=(description or "").strip() or None,
            notes=(notes or "").strip() or None,
            is_active=is_active,
        )
        self.audit.create(
            actor_user_id=actor.id,
            action="create_warehouse",
            target=f"warehouse:{warehouse.id}",
            detail=f"{warehouse.code} - {warehouse.name}",
        )
        return warehouse

    def update_warehouse(
        self,
        *,
        warehouse_id: int,
        name: str,
        description: str | None = None,
        notes: str | None = None,
        is_active: bool | None = None,
        actor,
    ) -> Warehouse:
        warehouse = self.get_warehouse(warehouse_id)
        self._validate(name=name)
        dup = self.repo.find_by_name(name)
        if dup is not None and dup.id != warehouse.id:
            raise WarehouseDuplicate("Tên kho đã tồn tại.")

        warehouse = self.repo.update(
            warehouse,
            name=name.strip(),
            description=(description or "").strip() or None,
            notes=(notes or "").strip() or None,
            is_active=is_active,
        )
        self.audit.create(
            actor_user_id=actor.id,
            action="update_warehouse",
            target=f"warehouse:{warehouse.id}",
            detail=f"{warehouse.code} - {warehouse.name}",
        )
        return warehouse

    def delete_warehouse(self, *, warehouse_id: int, actor) -> None:
        warehouse = self.get_warehouse(warehouse_id)
        code, name = warehouse.code, warehouse.name
        self.repo.delete(warehouse)
        self.audit.create(
            actor_user_id=actor.id,
            action="delete_warehouse",
            target=f"warehouse:{warehouse_id}",
            detail=f"{code} {name}",
        )
