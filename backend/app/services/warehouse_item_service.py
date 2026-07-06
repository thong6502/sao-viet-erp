"""Warehouse item service — module Kho hàng vận hành (nhân viên nhập)."""
from __future__ import annotations

from ..models.warehouse_item import WarehouseItem
from ..repositories.audit_repo import AuditLogRepository
from ..repositories.user_repo import UserRepository
from ..repositories.warehouse_item_repo import WarehouseItemRepository
from ..repositories.warehouse_repo import WarehouseRepository


class WarehouseItemError(Exception):
    pass


class WarehouseItemValidationError(WarehouseItemError):
    pass


class WarehouseItemNotFound(WarehouseItemError):
    pass


class WarehouseNotConfigured(WarehouseItemError):
    """The chosen warehouse is not one admin has configured (or is inactive)."""


class WarehouseItemService:
    def __init__(
        self,
        repo: WarehouseItemRepository,
        warehouses: WarehouseRepository,
        users: UserRepository,
        audit: AuditLogRepository,
    ) -> None:
        self.repo = repo
        self.warehouses = warehouses
        self.users = users
        self.audit = audit

    # --- helpers ------------------------------------------------------------

    def active_warehouse_options(self) -> list[dict]:
        """Active warehouses (admin-configured) for the operational picker."""
        rows, _ = self.warehouses.list(is_active=True, sort="code", page=1, size=200)
        return [{"id": w.id, "code": w.code, "name": w.name} for w in rows]

    def _require_configured_warehouse(self, warehouse_id: int) -> None:
        w = self.warehouses.get_by_id(warehouse_id)
        if w is None:
            raise WarehouseNotConfigured("Kho không tồn tại trong danh mục đã cấu hình.")
        if not w.is_active:
            raise WarehouseNotConfigured("Kho đang bị ẩn — không thể nhập vào kho này.")

    def _validate(self, *, name: str, quantity: float) -> None:
        if not name.strip():
            raise WarehouseItemValidationError("Tên mặt hàng không được trống.")
        if quantity < 0:
            raise WarehouseItemValidationError("Số lượng không được âm.")

    def _to_row(self, item: WarehouseItem) -> dict:
        w = self.warehouses.get_by_id(item.warehouse_id)
        creator = (
            self.users.get_by_id(item.created_by_user_id)
            if item.created_by_user_id is not None
            else None
        )
        return {
            "id": item.id,
            "warehouse_id": item.warehouse_id,
            "warehouse_code": w.code if w else None,
            "warehouse_name": w.name if w else None,
            "name": item.name,
            "quantity": float(item.quantity),
            "unit": item.unit,
            "notes": item.notes,
            "created_by_user_id": item.created_by_user_id,
            "created_by_name": creator.name if creator else None,
            "created_at": item.created_at,
            "updated_at": item.updated_at,
        }

    # --- queries ------------------------------------------------------------

    def list_items(
        self,
        *,
        warehouse_id: int | None = None,
        q: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict], int]:
        rows, total = self.repo.list(warehouse_id=warehouse_id, q=q, page=page, size=size)
        return [self._to_row(r) for r in rows], total

    def get_item(self, item_id: int) -> WarehouseItem:
        item = self.repo.get_by_id(item_id)
        if item is None:
            raise WarehouseItemNotFound("Không tìm thấy mặt hàng.")
        return item

    # --- commands -----------------------------------------------------------

    def create_item(
        self,
        *,
        warehouse_id: int,
        name: str,
        quantity: float,
        unit: str,
        notes: str | None,
        actor,
    ) -> dict:
        self._validate(name=name, quantity=quantity)
        self._require_configured_warehouse(warehouse_id)
        item = self.repo.create(
            warehouse_id=warehouse_id,
            name=name.strip(),
            quantity=quantity,
            unit=(unit or "").strip() or "cái",
            notes=(notes or "").strip() or None,
            created_by_user_id=actor.id,
        )
        self.audit.create(
            actor_user_id=actor.id,
            action="create_warehouse_item",
            target=f"warehouse_item:{item.id}",
            detail=f"{item.name} x{float(item.quantity):g} {item.unit} → kho:{warehouse_id}",
        )
        return self._to_row(item)

    def update_item(
        self,
        *,
        item_id: int,
        warehouse_id: int,
        name: str,
        quantity: float,
        unit: str,
        notes: str | None,
        actor,
    ) -> dict:
        item = self.get_item(item_id)
        self._validate(name=name, quantity=quantity)
        self._require_configured_warehouse(warehouse_id)
        item = self.repo.update(
            item,
            warehouse_id=warehouse_id,
            name=name.strip(),
            quantity=quantity,
            unit=(unit or "").strip() or "cái",
            notes=(notes or "").strip() or None,
        )
        self.audit.create(
            actor_user_id=actor.id,
            action="update_warehouse_item",
            target=f"warehouse_item:{item.id}",
            detail=f"{item.name} x{float(item.quantity):g} {item.unit}",
        )
        return self._to_row(item)

    def delete_item(self, *, item_id: int, actor) -> None:
        item = self.get_item(item_id)
        name = item.name
        self.repo.delete(item)
        self.audit.create(
            actor_user_id=actor.id,
            action="delete_warehouse_item",
            target=f"warehouse_item:{item_id}",
            detail=name,
        )
