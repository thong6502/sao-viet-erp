"""Department-management business logic (the Phòng ban admin screen).

Framework-agnostic: raises domain errors the router maps to HTTP. Owns department
create / rename / set-head / delete with name dedup, a head-must-belong-to-the-department
rule, and a block on deleting a department that still has roles or users.
"""
from __future__ import annotations

from ..models.department import Department
from ..repositories.audit_repo import AuditLogRepository
from ..repositories.employee_repo import EmployeeRepository
from ..repositories.rbac_repo import DepartmentRepository, RoleRepository, UnitLevelRepository
from ..repositories.user_repo import UserRepository

# Sentinel: "caller did not send this field" — distinct from an explicit None (which means
# "clear the parent / make it a root"). Lets a partial update keep the current parent.
_KEEP = object()


class DepartmentError(Exception):
    """Base for department-management domain errors."""


class DepartmentNameTaken(DepartmentError):
    """Another department already uses that name."""


class DepartmentNotFound(DepartmentError):
    """No department with that id."""


class InvalidHead(DepartmentError):
    """The chosen head is not a user of this department."""


class SetHeadForbidden(DepartmentError):
    """Đổi trưởng phòng cần quyền chi tiết `set_head` (tách khỏi sửa phòng ban)."""


class ReparentForbidden(DepartmentError):
    """Đổi cấp trên (cây tổ chức) cần quyền chi tiết `reparent` (tách khỏi sửa phòng ban)."""


class DepartmentCycle(DepartmentError):
    """Re-parenting would create a cycle (parent is the unit itself or a descendant)."""


class InvalidLevelOrder(DepartmentError):
    """A child unit's level must rank BELOW its parent's level (spec-06 / PBI-4007)."""


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
        levels: UnitLevelRepository,
        employees: EmployeeRepository,
    ) -> None:
        self.departments = departments
        self.roles = roles
        self.users = users
        self.audit = audit
        self.levels = levels
        self.employees = employees

    def _head_name(self, dept: Department) -> str | None:
        if dept.head_user_id is None:
            return None
        head = self.users.get_by_id(dept.head_user_id)
        return head.name if head is not None else None

    def _head_title(self, dept: Department) -> str | None:
        """The head's title from the department's level (spec-06 / PBI-4004 label), or None."""
        if dept.level_id is None:
            return None
        level = self.levels.get_by_id(dept.level_id)
        return (level.head_title or None) if level is not None else None

    def _level_rank(self, level_id: int | None) -> int | None:
        if level_id is None:
            return None
        level = self.levels.get_by_id(level_id)
        return level.rank if level is not None else None

    def _validate_hierarchy(
        self, *, dept_id: int | None, parent_id: int | None, level_id: int | None
    ) -> None:
        """Guard the org tree (spec-06 / PBI-4007): no parent cycle, and a child unit's level
        must rank strictly BELOW its parent's (rank number higher = lower tier). `dept_id` is
        None on create (the unit has no descendants/children yet)."""
        # Cycle: the chosen parent may not be the unit itself or any of its descendants.
        if parent_id is not None and dept_id is not None:
            if any(d.id == parent_id for d in self.departments.subtree(dept_id)):
                raise DepartmentCycle(
                    "Không thể chọn chính đơn vị hoặc đơn vị con/cháu làm đơn vị cha"
                )
        my_rank = self._level_rank(level_id)
        # This unit's level vs its parent's: child must be a lower tier (bigger rank).
        if parent_id is not None and my_rank is not None:
            parent = self.departments.get_by_id(parent_id)
            parent_rank = self._level_rank(parent.level_id) if parent is not None else None
            if parent_rank is not None and my_rank <= parent_rank:
                raise InvalidLevelOrder(
                    "Cấp của đơn vị con phải thấp hơn cấp của đơn vị cha"
                )
        # This unit's level vs its existing direct children (update only): each child must
        # stay a lower tier than this unit.
        if my_rank is not None and dept_id is not None:
            for child in self.departments.children_of(dept_id):
                child_rank = self._level_rank(child.level_id)
                if child_rank is not None and child_rank <= my_rank:
                    raise InvalidLevelOrder(
                        "Cấp của đơn vị phải cao hơn cấp của các đơn vị con"
                    )

    def list_summaries(self) -> list[dict]:
        """All departments with own + branch-rolled-up role/user counts (PBI-4001).

        Counts each department's own roles/users once, then sums every descendant's counts
        into each ancestor via a memoized walk over the parent→children map — so a parent
        unit's `total_*` aggregates its whole sub-tree.
        """
        depts = self.departments.list_all()
        own_roles = {d.id: self.roles.count_by_department(d.id) for d in depts}
        own_users = {d.id: self.users.count_by_department(d.id) for d in depts}
        # Đ2: "số nhân sự" đếm theo HỒ SƠ (employees), tách khỏi "số tài khoản" (users).
        own_emps = {d.id: self.employees.count_by_department(d.id) for d in depts}

        children: dict[int, list[int]] = {}
        for d in depts:
            if d.parent_id is not None:
                children.setdefault(d.parent_id, []).append(d.id)

        role_total: dict[int, int] = {}
        user_total: dict[int, int] = {}
        emp_total: dict[int, int] = {}

        def totals(dept_id: int, visiting: frozenset[int]) -> tuple[int, int, int]:
            if dept_id in role_total:
                return role_total[dept_id], user_total[dept_id], emp_total[dept_id]
            r, u, e = own_roles.get(dept_id, 0), own_users.get(dept_id, 0), own_emps.get(dept_id, 0)
            for child_id in children.get(dept_id, []):
                if child_id in visiting:  # defensive: never recurse a cycle
                    continue
                cr, cu, ce = totals(child_id, visiting | {dept_id})
                r += cr
                u += cu
                e += ce
            role_total[dept_id], user_total[dept_id], emp_total[dept_id] = r, u, e
            return r, u, e

        rows: list[dict] = []
        for dept in depts:
            tr, tu, te = totals(dept.id, frozenset())
            rows.append(
                {
                    "id": dept.id,
                    "name": dept.name,
                    "code": dept.code,
                    "description": dept.description,
                    "parent_id": dept.parent_id,
                    "head_user_id": dept.head_user_id,
                    "head_name": self._head_name(dept),
                    "level_id": dept.level_id,
                    "head_title": self._head_title(dept),
                    "la_san_xuat": dept.la_san_xuat,
                    "role_count": own_roles[dept.id],
                    "user_count": own_users[dept.id],
                    "employee_count": own_emps[dept.id],
                    "total_role_count": tr,
                    "total_user_count": tu,
                    "total_employee_count": te,
                }
            )
        return rows

    def summary_of(self, dept: Department) -> dict:
        """Build the list-row shape for a single department (after create/update), including
        the branch-rolled-up counts (PBI-4001)."""
        branch = self.departments.subtree(dept.id)
        total_roles = sum(self.roles.count_by_department(d.id) for d in branch)
        total_users = sum(self.users.count_by_department(d.id) for d in branch)
        total_emps = sum(self.employees.count_by_department(d.id) for d in branch)
        return {
            "id": dept.id,
            "name": dept.name,
            "code": dept.code,
            "description": dept.description,
            "parent_id": dept.parent_id,
            "head_user_id": dept.head_user_id,
            "head_name": self._head_name(dept),
            "level_id": dept.level_id,
            "head_title": self._head_title(dept),
            "la_san_xuat": dept.la_san_xuat,
            "role_count": self.roles.count_by_department(dept.id),
            "user_count": self.users.count_by_department(dept.id),
            "employee_count": self.employees.count_by_department(dept.id),
            "total_role_count": total_roles,
            "total_user_count": total_users,
            "total_employee_count": total_emps,
        }

    def members_of_department(self, department_id: int) -> list[dict]:
        """NHÂN SỰ của một phòng — liệt kê theo HỒ SƠ, không phải theo tài khoản (Đ2:
        "ai thuộc phòng nào" bám hồ sơ). Kèm thông tin tài khoản nếu có: mọi tài khoản đều
        thuộc một hồ sơ, nhưng hồ sơ thì CÓ THỂ chưa có tài khoản (công nhân xưởng không
        cần đăng nhập) — những người đó trước đây bị màn Phòng ban bỏ sót."""
        dept = self.departments.get_by_id(department_id)
        head_id = dept.head_user_id if dept is not None else None
        members: list[dict] = []
        for emp in self.employees.list_by_department(department_id):
            user = self.users.get_by_id(emp.user_id) if emp.user_id is not None else None
            role_name = None
            if user is not None and user.role_id is not None:
                role = self.roles.get_by_id(user.role_id)
                role_name = role.name if role is not None else None
            members.append(
                {
                    "employee_id": emp.id,
                    "code": emp.code,
                    "name": emp.full_name,
                    "position": emp.position,
                    "status": emp.status,
                    "user_id": user.id if user is not None else None,
                    "username": user.username if user is not None else None,
                    "role_name": role_name,
                    "is_active": user.is_active if user is not None else None,
                    "is_head": user is not None and user.id == head_id,
                }
            )
        return members

    def head_candidates(self, dept_id: int) -> list:
        """People eligible to head a unit (spec-06 / PBI-4004): everyone in the unit and its
        sub-units (subtree). Returns User rows; empty if the department does not exist."""
        candidates: list = []
        seen: set[int] = set()
        for d in self.departments.subtree(dept_id):
            for user in self.users.list_by_department(d.id):
                if user.id not in seen:
                    seen.add(user.id)
                    candidates.append(user)
        return candidates

    def create(
        self,
        *,
        name: str,
        description: str | None = None,
        parent_id: int | None = None,
        level_id: int | None = None,
        la_san_xuat: bool = False,
        actor_id: int | None,
    ) -> Department:
        name = name.strip()
        if self.departments.get_by_name(name) is not None:
            raise DepartmentNameTaken("Tên phòng ban đã tồn tại")
        if parent_id is not None and self.departments.get_by_id(parent_id) is None:
            raise DepartmentNotFound("Không tìm thấy phòng cha")
        if level_id is not None and self.levels.get_by_id(level_id) is None:
            raise DepartmentNotFound("Không tìm thấy cấp đơn vị")
        # New unit has no descendants yet — only the parent/level ordering rule applies.
        self._validate_hierarchy(dept_id=None, parent_id=parent_id, level_id=level_id)
        desc = (description or "").strip() or None
        dept = self.departments.create(name=name, description=desc, parent_id=parent_id)
        if level_id is not None:
            self.departments.set_level(dept, level_id)
        if la_san_xuat:
            self.departments.set_la_san_xuat(dept, True)
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
        level_id: int | None = None,
        parent_id: int | None | object = _KEEP,
        actor_id: int | None,
        allow_set_head: bool = True,
        allow_reparent: bool = True,
        la_san_xuat: bool = False,
    ) -> Department:
        dept = self.departments.get_by_id(dept_id)
        if dept is None:
            raise DepartmentNotFound("Không tìm thấy phòng ban")
        # Đổi trưởng phòng là quyền chi tiết riêng; giữ nguyên head thì không cần.
        if head_user_id != dept.head_user_id and not allow_set_head:
            raise SetHeadForbidden("Bạn không có quyền đặt trưởng phòng.")
        # Absent parent_id → keep the current parent (partial update, e.g. a plain rename).
        if parent_id is _KEEP:
            parent_id = dept.parent_id
        # Đổi cấp trên (tái cấu trúc cây) là quyền chi tiết riêng; giữ nguyên thì không cần.
        if parent_id != dept.parent_id and not allow_reparent:
            raise ReparentForbidden("Bạn không có quyền đổi cấp trên của phòng ban.")
        name = name.strip()
        clash = self.departments.get_by_name(name)
        if clash is not None and clash.id != dept_id:
            raise DepartmentNameTaken("Tên phòng ban đã tồn tại")
        if head_user_id is not None and not self._can_head(dept_id, head_user_id):
            raise InvalidHead("Người đứng đầu phải thuộc phòng này hoặc đơn vị con")
        if level_id is not None and self.levels.get_by_id(level_id) is None:
            raise DepartmentNotFound("Không tìm thấy cấp đơn vị")
        if parent_id is not None and self.departments.get_by_id(parent_id) is None:
            raise DepartmentNotFound("Không tìm thấy phòng cha")
        # No cycle (parent ∉ this unit's subtree) + child level ranks below parent (PBI-4007).
        self._validate_hierarchy(dept_id=dept_id, parent_id=parent_id, level_id=level_id)
        # The code is system-owned and never edited here (spec-05).
        self.departments.rename(dept, name)
        self.departments.set_description(dept, (description or "").strip() or None)
        self.departments.set_head(dept, head_user_id)
        self.departments.set_level(dept, level_id)
        self.departments.set_parent(dept, parent_id)
        self.departments.set_la_san_xuat(dept, la_san_xuat)
        self.audit.create(
            actor_user_id=actor_id,
            action="update_department",
            target=f"dept:{dept_id}",
            detail=f"{name} (head={head_user_id}, level={level_id}, parent={parent_id})",
        )
        return dept

    def _can_head(self, dept_id: int, user_id: int) -> bool:
        """A valid head belongs to the unit OR any unit in its subtree (spec-06 / PBI-4004)."""
        user = self.users.get_by_id(user_id)
        if user is None or user.department_id is None:
            return False
        return any(d.id == user.department_id for d in self.departments.subtree(dept_id))

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
        # Đ2: chặn nếu nhánh còn HỒ SƠ nhân sự (không để employees.department_id mồ côi) HOẶC
        # còn TÀI KHOẢN (users.department_id là FK cứng — xóa sẽ vỡ). Chặn theo hồ-sơ ∪ tài-khoản.
        offenders: list[tuple[Department, int]] = []
        for d in branch:
            u = self.users.count_by_department(d.id)
            e = self.employees.count_by_department(d.id)
            if u > 0 or e > 0:
                offenders.append((d, max(u, e)))
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
