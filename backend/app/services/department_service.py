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


class DepartmentBranchHasUsers(DepartmentError):
    """A department branch still has personnel — deletion is blocked (spec-05 / PBI-4005)
    until the people are moved out. `offenders` is a list of (Department, user_count)."""

    def __init__(self, offenders: list[tuple[Department, int]]) -> None:
        self.offenders = offenders
        listed = ", ".join(f"{d.name} ({c} người)" for d, c in offenders)
        super().__init__(
            "Không thể xóa: còn nhân sự trong " + listed + ". Hãy chuyển người đi trước."
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
                    "code": dept.code,
                    "description": dept.description,
                    "parent_id": dept.parent_id,
                    "head_user_id": dept.head_user_id,
                    "head_name": head_name,
                    "role_count": self.roles.count_by_department(dept.id),
                    "user_count": self.users.count_by_department(dept.id),
                }
            )
        return rows

    def summary_of(self, dept: Department) -> dict:
        """Build the list-row shape for a single department (after create/update)."""
        head_name = None
        if dept.head_user_id is not None:
            head = self.users.get_by_id(dept.head_user_id)
            head_name = head.name if head is not None else None
        return {
            "id": dept.id,
            "name": dept.name,
            "code": dept.code,
            "description": dept.description,
            "parent_id": dept.parent_id,
            "head_user_id": dept.head_user_id,
            "head_name": head_name,
            "role_count": self.roles.count_by_department(dept.id),
            "user_count": self.users.count_by_department(dept.id),
        }

    def users_in_department(self, department_id: int):
        return self.users.list_by_department(department_id)

    def create(
        self,
        *,
        name: str,
        description: str | None = None,
        parent_id: int | None = None,
        actor_id: int | None,
    ) -> Department:
        name = name.strip()
        if self.departments.get_by_name(name) is not None:
            raise DepartmentNameTaken("Tên phòng ban đã tồn tại")
        if parent_id is not None and self.departments.get_by_id(parent_id) is None:
            raise DepartmentNotFound("Không tìm thấy phòng cha")
        desc = (description or "").strip() or None
        dept = self.departments.create(name=name, description=desc, parent_id=parent_id)
        self.audit.create(
            actor_user_id=actor_id,
            action="create_department",
            target=f"dept:{dept.id}",
            detail=f"{dept.code} {name}",
        )
        return dept

    def update(
        self,
        *,
        dept_id: int,
        name: str,
        description: str | None = None,
        head_user_id: int | None,
        actor_id: int | None,
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
        # The code is system-owned and never edited here (spec-05).
        self.departments.rename(dept, name)
        self.departments.set_description(dept, (description or "").strip() or None)
        self.departments.set_head(dept, head_user_id)
        self.audit.create(
            actor_user_id=actor_id,
            action="update_department",
            target=f"dept:{dept_id}",
            detail=f"{name} (head={head_user_id})",
        )
        return dept

    def branch(self, dept_id: int) -> list[Department]:
        """The department + its whole subtree (spec-05) — the units a delete would remove.
        Empty if the department does not exist."""
        return self.departments.subtree(dept_id)

    def delete(self, *, dept_id: int, actor_id: int | None) -> None:
        """Delete a department AND its entire subtree (PBI-4005). Blocked if ANY unit in the
        branch still has personnel; roles of the deleted units are removed with them. Writes
        one AuditLog row per deleted unit."""
        dept = self.departments.get_by_id(dept_id)
        if dept is None:
            raise DepartmentNotFound("Không tìm thấy phòng ban")
        branch = self.departments.subtree(dept_id)  # root first (breadth-first)
        offenders = [
            (d, self.users.count_by_department(d.id))
            for d in branch
            if self.users.count_by_department(d.id) > 0
        ]
        if offenders:
            raise DepartmentBranchHasUsers(offenders)
        # Delete leaves first (reverse of the breadth-first order) so a parent's self-FK is
        # never left dangling. Each unit's roles go with it (no one holds them — branch has
        # no users).
        for d in reversed(branch):
            for role in self.roles.list_by_department(d.id):
                self.roles.delete(role)
            self.departments.delete(d)
            self.audit.create(
                actor_user_id=actor_id,
                action="delete_department",
                target=f"dept:{d.id}",
                detail=f"{d.code} {d.name}",
            )
