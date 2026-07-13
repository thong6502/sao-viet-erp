"""RBAC data access: departments, roles, role permissions, module catalog.

The ONLY layer that touches the DB for RBAC. SQL goes through SQLAlchemy bound
parameters (no string-formatted input). No business rules here.
"""
from __future__ import annotations

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from ..models.department import Department
from ..models.module import Module
from ..models.role import Role, RolePermission
from ..models.unit_level import UnitLevel


class ModuleRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_by_key(self, key: str) -> Module | None:
        return self.db.execute(
            select(Module).where(Module.key == key)
        ).scalar_one_or_none()

    def create(self, *, key: str, label: str) -> Module:
        module = Module(key=key, label=label)
        self.db.add(module)
        self.db.commit()
        self.db.refresh(module)
        return module

    def list_all(self) -> list[Module]:
        return list(self.db.execute(select(Module).order_by(Module.id)).scalars())

    def count(self) -> int:
        return self.db.execute(select(func.count()).select_from(Module)).scalar_one()


class DepartmentRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_by_id(self, dept_id: int) -> Department | None:
        return self.db.get(Department, dept_id)

    def get_by_name(self, name: str) -> Department | None:
        return self.db.execute(
            select(Department).where(Department.name == name)
        ).scalar_one_or_none()

    def _next_code(self) -> str:
        """Next sequential department code: 'PB' + zero-padded number (spec-05). Based on the
        max existing PB-number so codes stay unique even after deletions (no reuse)."""
        max_n = 0
        for code in self.db.execute(select(Department.code)).scalars():
            if code and code.startswith("PB"):
                try:
                    max_n = max(max_n, int(code[2:]))
                except ValueError:
                    continue
        return f"PB{max_n + 1:03d}"

    def create(
        self,
        *,
        name: str,
        head_user_id: int | None = None,
        description: str | None = None,
        parent_id: int | None = None,
    ) -> Department:
        dept = Department(
            name=name,
            code=self._next_code(),
            description=description,
            parent_id=parent_id,
            head_user_id=head_user_id,
        )
        self.db.add(dept)
        self.db.commit()
        self.db.refresh(dept)
        return dept

    def set_description(self, dept: Department, description: str | None) -> Department:
        dept.description = description
        self.db.commit()
        self.db.refresh(dept)
        return dept

    def children_of(self, parent_id: int) -> list[Department]:
        """Direct child departments of a parent (spec-05 tree)."""
        return list(
            self.db.execute(
                select(Department).where(Department.parent_id == parent_id).order_by(Department.id)
            ).scalars()
        )

    def subtree(self, root_id: int) -> list[Department]:
        """The department and ALL its descendants (spec-05), breadth-first from the root.
        Returns [] if the root does not exist. No duplicates."""
        root = self.get_by_id(root_id)
        if root is None:
            return []
        result: list[Department] = [root]
        seen = {root.id}
        queue = [root.id]
        while queue:
            current = queue.pop(0)
            for child in self.children_of(current):
                if child.id not in seen:
                    seen.add(child.id)
                    result.append(child)
                    queue.append(child.id)
        return result

    def set_head(self, dept: Department, head_user_id: int | None) -> Department:
        dept.head_user_id = head_user_id
        self.db.commit()
        self.db.refresh(dept)
        return dept

    def set_parent(self, dept: Department, parent_id: int | None) -> Department:
        """Re-parent a department in the org tree (spec-06 / PBI-4007). Cycle/level checks
        live in the service, not here."""
        dept.parent_id = parent_id
        self.db.commit()
        self.db.refresh(dept)
        return dept

    def set_level(self, dept: Department, level_id: int | None) -> Department:
        """Tag (or clear) a department's organizational tier (spec-06 / PBI-4009)."""
        dept.level_id = level_id
        self.db.commit()
        self.db.refresh(dept)
        return dept

    def count_by_level(self, level_id: int) -> int:
        """How many departments are tagged with a given unit level (delete guard)."""
        return self.db.execute(
            select(func.count()).select_from(Department).where(Department.level_id == level_id)
        ).scalar_one()

    def rename(self, dept: Department, name: str) -> Department:
        dept.name = name
        self.db.commit()
        self.db.refresh(dept)
        return dept

    def delete(self, dept: Department) -> None:
        self.db.delete(dept)
        self.db.commit()

    def list_all(self) -> list[Department]:
        return list(self.db.execute(select(Department).order_by(Department.id)).scalars())

    def count(self) -> int:
        return self.db.execute(select(func.count()).select_from(Department)).scalar_one()


class RoleRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_by_id(self, role_id: int) -> Role | None:
        return self.db.get(Role, role_id)

    def get_by_name_and_department(self, name: str, department_id: int) -> Role | None:
        return self.db.execute(
            select(Role).where(Role.name == name, Role.department_id == department_id)
        ).scalar_one_or_none()

    def create(self, *, name: str, department_id: int) -> Role:
        role = Role(name=name, department_id=department_id)
        self.db.add(role)
        self.db.commit()
        self.db.refresh(role)
        return role

    def update_name(self, role: Role, name: str) -> Role:
        role.name = name
        self.db.commit()
        self.db.refresh(role)
        return role

    def delete(self, role: Role) -> None:
        """Delete a role and its permission rows (no DB cascade configured)."""
        self.db.execute(delete(RolePermission).where(RolePermission.role_id == role.id))
        self.db.delete(role)
        self.db.commit()

    def list_by_department(self, department_id: int) -> list[Role]:
        return list(
            self.db.execute(
                select(Role).where(Role.department_id == department_id).order_by(Role.id)
            ).scalars()
        )

    def count_by_department(self, department_id: int) -> int:
        return self.db.execute(
            select(func.count()).select_from(Role).where(Role.department_id == department_id)
        ).scalar_one()

    def get_permission(self, role_id: int, module_key: str) -> RolePermission | None:
        return self.db.execute(
            select(RolePermission).where(
                RolePermission.role_id == role_id,
                RolePermission.module_key == module_key,
            )
        ).scalar_one_or_none()

    def permissions_for(self, role_id: int) -> list[RolePermission]:
        return list(
            self.db.execute(
                select(RolePermission).where(RolePermission.role_id == role_id)
            ).scalars()
        )

    def set_permission(
        self,
        *,
        role_id: int,
        module_key: str,
        can_read: bool = False,
        can_create: bool = False,
        can_update: bool = False,
        can_delete: bool = False,
        scope: str,
        can_reassign: bool = False,
        can_export: bool = False,
        can_view_debt: bool = False,
        can_view_discount: bool = False,
        can_approve: bool = False,
        can_manage_status: bool = False,
        can_reset_password: bool = False,
        can_lock: bool = False,
        can_revoke_sessions: bool = False,
        can_assign_role: bool = False,
        can_transfer: bool = False,
        can_set_head: bool = False,
        can_requote: bool = False,
        can_manage_price: bool = False,
        can_cancel: bool = False,
        can_manage_permissions: bool = False,
        can_clone: bool = False,
        can_toggle_active: bool = False,
        can_reparent: bool = False,
        can_view_salary: bool = False,
        can_edit_salary: bool = False,
        can_adjust: bool = False,
        can_approve_exception: bool = False,
    ) -> RolePermission:
        """Upsert the (role, module) permission row."""
        perm = self.get_permission(role_id, module_key)
        if perm is None:
            perm = RolePermission(role_id=role_id, module_key=module_key)
            self.db.add(perm)
        perm.can_read = can_read
        perm.can_create = can_create
        perm.can_update = can_update
        perm.can_delete = can_delete
        perm.scope = scope
        perm.can_reassign = can_reassign
        perm.can_export = can_export
        perm.can_view_debt = can_view_debt
        perm.can_view_discount = can_view_discount
        perm.can_approve = can_approve
        perm.can_manage_status = can_manage_status
        perm.can_reset_password = can_reset_password
        perm.can_lock = can_lock
        perm.can_revoke_sessions = can_revoke_sessions
        perm.can_assign_role = can_assign_role
        perm.can_transfer = can_transfer
        perm.can_set_head = can_set_head
        perm.can_requote = can_requote
        perm.can_manage_price = can_manage_price
        perm.can_cancel = can_cancel
        perm.can_manage_permissions = can_manage_permissions
        perm.can_clone = can_clone
        perm.can_toggle_active = can_toggle_active
        perm.can_reparent = can_reparent
        perm.can_view_salary = can_view_salary
        perm.can_edit_salary = can_edit_salary
        perm.can_adjust = can_adjust
        perm.can_approve_exception = can_approve_exception
        self.db.commit()
        self.db.refresh(perm)
        return perm

    def count(self) -> int:
        return self.db.execute(select(func.count()).select_from(Role)).scalar_one()


class UnitLevelRepository:
    """Data access for the unit-level catalog (cấp đơn vị, spec-06 / PBI-4009)."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def get_by_id(self, level_id: int) -> UnitLevel | None:
        return self.db.get(UnitLevel, level_id)

    def get_by_name(self, name: str) -> UnitLevel | None:
        return self.db.execute(
            select(UnitLevel).where(UnitLevel.name == name)
        ).scalar_one_or_none()

    def get_by_rank(self, rank: int) -> UnitLevel | None:
        return self.db.execute(
            select(UnitLevel).where(UnitLevel.rank == rank)
        ).scalar_one_or_none()

    def list_all(self) -> list[UnitLevel]:
        """All levels, highest tier first (rank ascending)."""
        return list(
            self.db.execute(select(UnitLevel).order_by(UnitLevel.rank)).scalars()
        )

    def create(self, *, name: str, rank: int, head_title: str) -> UnitLevel:
        level = UnitLevel(name=name, rank=rank, head_title=head_title)
        self.db.add(level)
        self.db.commit()
        self.db.refresh(level)
        return level

    def update(self, level: UnitLevel, *, name: str, rank: int, head_title: str) -> UnitLevel:
        level.name = name
        level.rank = rank
        level.head_title = head_title
        self.db.commit()
        self.db.refresh(level)
        return level

    def delete(self, level: UnitLevel) -> None:
        self.db.delete(level)
        self.db.commit()

    def count(self) -> int:
        return self.db.execute(select(func.count()).select_from(UnitLevel)).scalar_one()
