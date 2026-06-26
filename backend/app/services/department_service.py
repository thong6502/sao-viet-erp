"""Department-management business logic (the Phòng ban admin screen).

Framework-agnostic: raises domain errors the router maps to HTTP. Owns department
create / rename / set-head / delete with name dedup, a head-must-belong-to-the-department
rule, and a block on deleting a department that still has roles or users.
"""
from __future__ import annotations

from ..models.department import Department
from ..repositories.audit_repo import AuditLogRepository
from ..repositories.rbac_repo import DepartmentRepository, RoleRepository
from ..repositories.user_repo import UserRepository


class DepartmentError(Exception):
    """Base for department-management domain errors."""


class DepartmentNameTaken(DepartmentError):
    """Another department already uses that name."""


class DepartmentNotFound(DepartmentError):
    """No department with that id."""


class InvalidHead(DepartmentError):
    """The chosen head is not a user of this department."""


class DepartmentInUse(DepartmentError):
    """A department with roles or users cannot be deleted."""

    def __init__(self, roles: int, users: int) -> None:
        self.roles = roles
        self.users = users
        parts = []
        if roles:
            parts.append(f"{roles} vai trò")
        if users:
            parts.append(f"{users} người dùng")
        super().__init__(
            "Không thể xóa: phòng còn " + " và ".join(parts) + ". Hãy chuyển trước."
        )


class DepartmentService:
    def __init__(
        self,
        departments: DepartmentRepository,
        roles: RoleRepository,
        users: UserRepository,
        audit: AuditLogRepository,
    ) -> None:
        self.departments = departments
        self.roles = roles
        self.users = users
        self.audit = audit

    def list_summaries(self) -> list[dict]:
        rows: list[dict] = []
        for dept in self.departments.list_all():
            head_name = None
            if dept.head_user_id is not None:
                head = self.users.get_by_id(dept.head_user_id)
                head_name = head.name if head is not None else None
            rows.append(
                {
                    "id": dept.id,
                    "name": dept.name,
                    "head_user_id": dept.head_user_id,
                    "head_name": head_name,
                    "role_count": self.roles.count_by_department(dept.id),
                    "user_count": self.users.count_by_department(dept.id),
                }
            )
        return rows

    def users_in_department(self, department_id: int):
        return self.users.list_by_department(department_id)

    def create(self, *, name: str, actor_id: int | None) -> Department:
        name = name.strip()
        if self.departments.get_by_name(name) is not None:
            raise DepartmentNameTaken("Tên phòng ban đã tồn tại")
        dept = self.departments.create(name=name)
        self.audit.create(
            actor_user_id=actor_id, action="create_department", target=f"dept:{dept.id}", detail=name
        )
        return dept

    def update(
        self, *, dept_id: int, name: str, head_user_id: int | None, actor_id: int | None
    ) -> Department:
        dept = self.departments.get_by_id(dept_id)
        if dept is None:
            raise DepartmentNotFound("Không tìm thấy phòng ban")
        name = name.strip()
        clash = self.departments.get_by_name(name)
        if clash is not None and clash.id != dept_id:
            raise DepartmentNameTaken("Tên phòng ban đã tồn tại")
        if head_user_id is not None:
            head = self.users.get_by_id(head_user_id)
            if head is None or head.department_id != dept_id:
                raise InvalidHead("Người đứng đầu phải thuộc phòng này")
        self.departments.rename(dept, name)
        self.departments.set_head(dept, head_user_id)
        self.audit.create(
            actor_user_id=actor_id,
            action="update_department",
            target=f"dept:{dept_id}",
            detail=f"{name} (head={head_user_id})",
        )
        return dept

    def delete(self, *, dept_id: int, actor_id: int | None) -> None:
        dept = self.departments.get_by_id(dept_id)
        if dept is None:
            raise DepartmentNotFound("Không tìm thấy phòng ban")
        roles = self.roles.count_by_department(dept_id)
        users = self.users.count_by_department(dept_id)
        if roles or users:
            raise DepartmentInUse(roles, users)
        name = dept.name
        self.departments.delete(dept)
        self.audit.create(
            actor_user_id=actor_id, action="delete_department", target=f"dept:{dept_id}", detail=name
        )
