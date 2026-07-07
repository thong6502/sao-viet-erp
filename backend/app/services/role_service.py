"""Role-management business logic (the Vai trò admin screen).

Framework-agnostic: raises domain errors the router maps to HTTP. Owns role
creation (with per-department name dedup) and reading/saving a role's permission
matrix (CRUD + scope per module), writing an audit row on every change.
"""
from __future__ import annotations

from ..models.role import Role
from ..repositories.audit_repo import AuditLogRepository
from ..repositories.rbac_repo import DepartmentRepository, ModuleRepository, RoleRepository
from ..repositories.user_repo import UserRepository


class RoleError(Exception):
    """Base for role-management domain errors."""


class RoleNameTaken(RoleError):
    """A role with that name already exists in the department."""


class RoleNotFound(RoleError):
    """No role with that id."""


class DepartmentNotFound(RoleError):
    """No department with that id."""


class RoleInUse(RoleError):
    """A role still assigned to users cannot be deleted."""

    def __init__(self, count: int) -> None:
        self.count = count
        super().__init__(
            f"Không thể xóa: còn {count} người dùng đang giữ vai trò này. "
            "Hãy chuyển họ sang vai trò khác trước."
        )


class RoleService:
    def __init__(
        self,
        roles: RoleRepository,
        modules: ModuleRepository,
        departments: DepartmentRepository,
        audit: AuditLogRepository,
        users: UserRepository,
    ) -> None:
        self.roles = roles
        self.modules = modules
        self.departments = departments
        self.audit = audit
        self.users = users

    def list_modules(self):
        return self.modules.list_all()

    def list_departments(self):
        return self.departments.list_all()

    def list_roles(self, department_id: int) -> list[Role]:
        return self.roles.list_by_department(department_id)

    def create_role(self, *, name: str, department_id: int, actor_id: int | None) -> Role:
        dept = self.departments.get_by_id(department_id)
        if dept is None:
            raise DepartmentNotFound("Không tìm thấy phòng ban")
        name = name.strip()
        if self.roles.get_by_name_and_department(name, department_id) is not None:
            raise RoleNameTaken("Tên vai trò đã tồn tại trong phòng này")
        role = self.roles.create(name=name, department_id=department_id)
        self.audit.create(
            actor_user_id=actor_id,
            action="create_role",
            target=f"role:{role.id}",
            detail=f"{dept.name} / {name}",
        )
        return role

    def rename_role(self, *, role_id: int, name: str, actor_id: int | None) -> Role:
        role = self.roles.get_by_id(role_id)
        if role is None:
            raise RoleNotFound("Không tìm thấy vai trò")
        name = name.strip()
        clash = self.roles.get_by_name_and_department(name, role.department_id)
        if clash is not None and clash.id != role_id:
            raise RoleNameTaken("Tên vai trò đã tồn tại trong phòng này")
        old = role.name
        self.roles.update_name(role, name)
        self.audit.create(
            actor_user_id=actor_id,
            action="rename_role",
            target=f"role:{role_id}",
            detail=f"{old} → {name}",
        )
        return role

    def delete_role(self, *, role_id: int, actor_id: int | None) -> None:
        role = self.roles.get_by_id(role_id)
        if role is None:
            raise RoleNotFound("Không tìm thấy vai trò")
        in_use = self.users.count_by_role(role_id)
        if in_use > 0:
            raise RoleInUse(in_use)
        name = role.name
        self.roles.delete(role)
        self.audit.create(
            actor_user_id=actor_id,
            action="delete_role",
            target=f"role:{role_id}",
            detail=name,
        )

    def get_matrix(self, role_id: int) -> list[dict]:
        """Full matrix for a role: one row per module, merged with stored permissions
        (modules with no stored row default to all-false / own scope)."""
        role = self.roles.get_by_id(role_id)
        if role is None:
            raise RoleNotFound("Không tìm thấy vai trò")
        stored = {p.module_key: p for p in self.roles.permissions_for(role_id)}
        rows: list[dict] = []
        for module in self.modules.list_all():
            p = stored.get(module.key)
            rows.append(
                {
                    "module_key": module.key,
                    "can_read": bool(p.can_read) if p else False,
                    "can_create": bool(p.can_create) if p else False,
                    "can_update": bool(p.can_update) if p else False,
                    "can_delete": bool(p.can_delete) if p else False,
                    "scope": p.scope if p else "own",
                    "can_reassign": bool(p.can_reassign) if p else False,
                    "can_export": bool(p.can_export) if p else False,
                    "can_view_debt": bool(p.can_view_debt) if p else False,
                    "can_approve": bool(p.can_approve) if p else False,
                    "can_manage_status": bool(p.can_manage_status) if p else False,
                    "can_reset_password": bool(p.can_reset_password) if p else False,
                    "can_lock": bool(p.can_lock) if p else False,
                    "can_revoke_sessions": bool(p.can_revoke_sessions) if p else False,
                    "can_assign_role": bool(p.can_assign_role) if p else False,
                    "can_transfer": bool(p.can_transfer) if p else False,
                    "can_set_head": bool(p.can_set_head) if p else False,
                    "can_requote": bool(p.can_requote) if p else False,
                    "can_manage_price": bool(p.can_manage_price) if p else False,
                    "can_cancel": bool(p.can_cancel) if p else False,
                    "can_manage_permissions": bool(p.can_manage_permissions) if p else False,
                    "can_clone": bool(p.can_clone) if p else False,
                    "can_toggle_active": bool(p.can_toggle_active) if p else False,
                    "can_reparent": bool(p.can_reparent) if p else False,
                }
            )
        return rows

    def save_matrix(self, *, role_id: int, rows: list[dict], actor_id: int | None) -> list[dict]:
        role = self.roles.get_by_id(role_id)
        if role is None:
            raise RoleNotFound("Không tìm thấy vai trò")
        valid_keys = {m.key for m in self.modules.list_all()}
        for row in rows:
            if row["module_key"] not in valid_keys:
                continue  # ignore unknown modules rather than create dangling rows
            self.roles.set_permission(
                role_id=role_id,
                module_key=row["module_key"],
                can_read=row.get("can_read", False),
                can_create=row.get("can_create", False),
                can_update=row.get("can_update", False),
                can_delete=row.get("can_delete", False),
                scope=row.get("scope", "own"),
                can_reassign=row.get("can_reassign", False),
                can_export=row.get("can_export", False),
                can_view_debt=row.get("can_view_debt", False),
                can_approve=row.get("can_approve", False),
                can_manage_status=row.get("can_manage_status", False),
                can_reset_password=row.get("can_reset_password", False),
                can_lock=row.get("can_lock", False),
                can_revoke_sessions=row.get("can_revoke_sessions", False),
                can_assign_role=row.get("can_assign_role", False),
                can_transfer=row.get("can_transfer", False),
                can_set_head=row.get("can_set_head", False),
                can_requote=row.get("can_requote", False),
                can_manage_price=row.get("can_manage_price", False),
                can_cancel=row.get("can_cancel", False),
                can_manage_permissions=row.get("can_manage_permissions", False),
                can_clone=row.get("can_clone", False),
                can_toggle_active=row.get("can_toggle_active", False),
                can_reparent=row.get("can_reparent", False),
                can_view_salary=row.get("can_view_salary", False),
                can_adjust=row.get("can_adjust", False),
            )
        self.audit.create(
            actor_user_id=actor_id,
            action="update_role_permissions",
            target=f"role:{role_id}",
            detail=role.name,
        )
        return self.get_matrix(role_id)
