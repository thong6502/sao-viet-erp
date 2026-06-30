"""Self-service profile logic (spec-04).

Lets the *current* user read and edit their own profile (display name, avatar). No RBAC
permission is required — a user always owns their own profile. Stays framework-agnostic:
file IO + HTTP live in the router; this layer resolves names and mutates via repositories.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from ..models.user import User
from ..repositories.rbac_repo import DepartmentRepository, RoleRepository
from ..repositories.user_repo import UserRepository


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
    ) -> None:
        self.users = users
        self.departments = departments
        self.roles = roles

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
        """Set the display name. The schema already trimmed/validated 1..100 chars."""
        return self.users.set_name(user, name.strip())

    def set_avatar(self, user: User, avatar_url: str) -> User:
        return self.users.set_avatar(user, avatar_url)

    def clear_avatar(self, user: User) -> User:
        return self.users.set_avatar(user, None)
