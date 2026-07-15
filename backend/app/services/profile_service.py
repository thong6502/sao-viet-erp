"""Self-service profile logic (spec-04).

Lets the *current* user read and edit their own profile (display name, avatar). No RBAC
permission is required — a user always owns their own profile. Stays framework-agnostic:
file IO + HTTP live in the router; this layer resolves names and mutates via repositories.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from ..models.user import User
from ..repositories.employee_repo import EmployeeRepository
from ..repositories.rbac_repo import DepartmentRepository, RoleRepository
from ..repositories.user_repo import UserRepository


class ProfileError(Exception):
    """Profile domain error (mapped to HTTP 400 by the router)."""


@dataclass(frozen=True)
class ProfileData:
    """Read-only view of the current user's profile (department/role resolved to names)."""

    id: int
    username: str
    name: str
    avatar_url: str | None
    department_name: str | None
    role_name: str | None
    created_at: datetime


class ProfileService:
    def __init__(
        self,
        users: UserRepository,
        departments: DepartmentRepository,
        roles: RoleRepository,
        employees: EmployeeRepository,
    ) -> None:
        self.users = users
        self.departments = departments
        self.roles = roles
        self.employees = employees

    def get_profile(self, user: User) -> ProfileData:
        dept = self.departments.get_by_id(user.department_id) if user.department_id else None
        role = self.roles.get_by_id(user.role_id) if user.role_id else None
        return ProfileData(
            id=user.id,
            username=user.username,
            name=user.name,
            avatar_url=user.avatar_url,
            department_name=dept.name if dept else None,
            role_name=role.name if role else None,
            created_at=user.created_at,
        )

    def update_name(self, user: User, name: str) -> User:
        """Set the display name. Chặn nếu user CÓ hồ sơ nhân sự — tên hiển thị do hồ sơ quyết
        (Đ1); chỉ tài khoản KHÔNG gắn hồ sơ (vd admin) mới tự đổi tên được."""
        if self.employees.get_by_user_id(user.id) is not None:
            raise ProfileError("Tên hiển thị lấy từ hồ sơ nhân sự — nhờ HCNS cập nhật.")
        return self.users.set_name(user, name.strip())

    def set_avatar(self, user: User, avatar_url: str) -> User:
        """Đặt ảnh. User CÓ hồ sơ → ảnh gốc là ảnh hồ sơ (Đ1): ghi employees.photo_url rồi
        phản chiếu xuống avatar tài khoản. Admin không hồ sơ → chỉ users.avatar_url."""
        emp = self.employees.get_by_user_id(user.id)
        if emp is not None:
            self.employees.update(emp, photo_url=avatar_url)
        return self.users.set_avatar(user, avatar_url)

    def clear_avatar(self, user: User) -> User:
        emp = self.employees.get_by_user_id(user.id)
        if emp is not None:
            self.employees.update(emp, photo_url=None)
        return self.users.set_avatar(user, None)
