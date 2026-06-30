"""User-management business logic (the Người dùng admin screen).

HR creates accounts + assigns a department; a head assigns a role (must be a role of
the user's department); accounts can be locked/unlocked. Framework-agnostic: raises
domain errors the router maps to HTTP, and writes an audit row on every change.
"""
from __future__ import annotations

from ..config import settings
from ..models.user import User
from ..repositories.audit_repo import AuditLogRepository
from ..repositories.rbac_repo import DepartmentRepository, RoleRepository
from ..repositories.user_repo import UserRepository
from ..security import hash_password


class UserAdminError(Exception):
    """Base for user-management domain errors."""


class UsernameTaken(UserAdminError):
    """An account with that username already exists."""


class UserNotFound(UserAdminError):
    """No user with that id."""


class DepartmentNotFound(UserAdminError):
    """No department with that id."""


class InvalidRoleForDepartment(UserAdminError):
    """The role does not belong to the user's department."""


class CannotLockSelf(UserAdminError):
    """A user may not lock their own account."""


class UserAdminService:
    def __init__(
        self,
        users: UserRepository,
        departments: DepartmentRepository,
        roles: RoleRepository,
        audit: AuditLogRepository,
    ) -> None:
        self.users = users
        self.departments = departments
        self.roles = roles
        self.audit = audit

    def list_users(self) -> list[dict]:
        dept_names: dict[int, str] = {}
        role_names: dict[int, str] = {}
        rows: list[dict] = []
        for u in self.users.list_all():
            dept_name = None
            if u.department_id is not None:
                if u.department_id not in dept_names:
                    d = self.departments.get_by_id(u.department_id)
                    dept_names[u.department_id] = d.name if d else None
                dept_name = dept_names[u.department_id]
            role_name = None
            if u.role_id is not None:
                if u.role_id not in role_names:
                    r = self.roles.get_by_id(u.role_id)
                    role_names[u.role_id] = r.name if r else None
                role_name = role_names[u.role_id]
            rows.append(
                {
                    "id": u.id,
                    "name": u.name,
                    "username": u.username,
                    "department_id": u.department_id,
                    "department_name": dept_name,
                    "role_id": u.role_id,
                    "role_name": role_name,
                    "is_active": u.is_active,
                }
            )
        return rows

    def create_user(
        self, *, name: str, username: str, department_id: int, actor_id: int | None
    ) -> User:
        username = username.strip()
        if self.departments.get_by_id(department_id) is None:
            raise DepartmentNotFound("Không tìm thấy phòng ban")
        if self.users.get_by_username(username) is not None:
            raise UsernameTaken("Tên đăng nhập đã được sử dụng")
        user = self.users.create(
            username=username,
            name=name.strip(),
            password_hash=hash_password(settings.default_user_password),
        )
        # New account: in the department, no role yet (most-minimal access until a
        # head assigns one), active.
        self.users.set_assignment(
            user, department_id=department_id, role_id=None, is_active=True
        )
        self.audit.create(
            actor_user_id=actor_id,
            action="create_user",
            target=f"user:{user.id}",
            detail=f"{username} → dept:{department_id}",
        )
        return user

    def assign_role(self, *, user_id: int, role_id: int | None, actor_id: int | None) -> User:
        user = self.users.get_by_id(user_id)
        if user is None:
            raise UserNotFound("Không tìm thấy người dùng")
        if role_id is not None:
            role = self.roles.get_by_id(role_id)
            if role is None or role.department_id != user.department_id:
                raise InvalidRoleForDepartment("Vai trò không thuộc phòng của người dùng")
        self.users.set_role(user, role_id)
        self.audit.create(
            actor_user_id=actor_id,
            action="assign_role",
            target=f"user:{user_id}",
            detail=f"role:{role_id}",
        )
        return user

    def set_active(
        self, *, user_id: int, is_active: bool, actor_id: int | None
    ) -> User:
        if not is_active and user_id == actor_id:
            raise CannotLockSelf("Không thể tự khóa tài khoản của mình")
        user = self.users.get_by_id(user_id)
        if user is None:
            raise UserNotFound("Không tìm thấy người dùng")
        self.users.set_active(user, is_active)
        self.audit.create(
            actor_user_id=actor_id,
            action="lock_user" if not is_active else "unlock_user",
            target=f"user:{user_id}",
            detail=user.username,
        )
        return user
