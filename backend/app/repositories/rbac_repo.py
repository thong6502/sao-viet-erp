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

    def create(self, *, name: str, head_user_id: int | None = None) -> Department:
        dept = Department(name=name, head_user_id=head_user_id)
        self.db.add(dept)
        self.db.commit()
        self.db.refresh(dept)
        return dept

    def set_head(self, dept: Department, head_user_id: int | None) -> Department:
        dept.head_user_id = head_user_id
        self.db.commit()
        self.db.refresh(dept)
        return dept

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
        self.db.commit()
        self.db.refresh(perm)
        return perm

    def count(self) -> int:
        return self.db.execute(select(func.count()).select_from(Role)).scalar_one()
