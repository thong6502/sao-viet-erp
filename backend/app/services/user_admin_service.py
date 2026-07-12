"""User-management business logic (the Người dùng admin screen).

HR creates accounts + assigns a department; a head assigns a role (must be a role of
the user's department); accounts can be locked/unlocked. Framework-agnostic: raises
domain errors the router maps to HTTP, and writes an audit row on every change.
"""
from __future__ import annotations

from ..config import settings
from ..models.audit import AuditLog
from ..models.refresh_token import RefreshToken
from ..models.user import User
from ..repositories.audit_repo import AuditLogRepository
from ..repositories.employee_repo import EmployeeRepository
from ..repositories.rbac_repo import DepartmentRepository, RoleRepository
from ..repositories.refresh_token_repo import RefreshTokenRepository
from ..repositories.user_repo import UserRepository
from ..security import generate_temp_password, hash_password


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


class CannotRevokeSelf(UserAdminError):
    """A user may not revoke their own sessions (would log themselves out)."""


class TransferForbidden(UserAdminError):
    """Đổi phòng ban của người dùng cần quyền chi tiết `transfer` (tách khỏi sửa hồ sơ)."""


class UserAdminService:
    def __init__(
        self,
        users: UserRepository,
        departments: DepartmentRepository,
        roles: RoleRepository,
        audit: AuditLogRepository,
        tokens: RefreshTokenRepository,
        employees: EmployeeRepository,
    ) -> None:
        self.users = users
        self.departments = departments
        self.roles = roles
        self.audit = audit
        self.tokens = tokens
        self.employees = employees

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
                    "code": u.code,
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
        self, *, name: str, username: str, department_id: int, actor_id: int | None,
        password: str | None = None,
    ) -> User:
        username = username.strip()
        if self.departments.get_by_id(department_id) is None:
            raise DepartmentNotFound("Không tìm thấy phòng ban")
        if self.users.get_by_username(username) is not None:
            raise UsernameTaken("Tên đăng nhập đã được sử dụng")
        # Mật khẩu: admin nhập (nếu có) hoặc mật khẩu mặc định.
        effective_pw = (password or "").strip() or settings.default_user_password
        user = self.users.create(
            username=username,
            name=name.strip(),
            password_hash=hash_password(effective_pw),
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

    def bulk_assign_role(
        self, *, user_ids: list[int], role_id: int, actor_id: int | None
    ) -> int:
        """Gán một vai trò cho nhiều người cùng lúc từ màn Phòng ban (bulk).

        The role must belong to the same department as every selected user (a role lives in
        exactly one department). Validates the role + all users up front so a bad id fails the
        whole batch (no partial change), then sets the role and writes one audit row per person.
        Returns how many were assigned.
        """
        role = self.roles.get_by_id(role_id)
        if role is None:
            raise InvalidRoleForDepartment("Vai trò không tồn tại")
        # Resolve everyone first; each must be in the role's department (nothing changes on error).
        users: list[User] = []
        for uid in user_ids:
            u = self.users.get_by_id(uid)
            if u is None:
                raise UserNotFound(f"Không tìm thấy người dùng (id={uid})")
            if u.department_id != role.department_id:
                raise InvalidRoleForDepartment("Vai trò không thuộc phòng của người dùng")
            users.append(u)
        for u in users:
            self.users.set_role(u, role_id)
            self.audit.create(
                actor_user_id=actor_id,
                action="assign_role",
                target=f"user:{u.id}",
                detail=f"role:{role_id}",
            )
        return len(users)

    def transfer_users(
        self, *, user_ids: list[int], target_department_id: int, actor_id: int | None
    ) -> int:
        """Bulk-move people to a target department (spec-06 / PBI-4008).

        Each transferred user lands in the target department with NO role (role_id=None) —
        back to minimal access until the new head assigns one. If a moved user headed their
        OLD department, that department's head is cleared. Validates the target and every
        user up front (nothing changes if any is missing), then writes one audit row per
        person moved. Returns how many were moved.
        """
        target = self.departments.get_by_id(target_department_id)
        if target is None:
            raise DepartmentNotFound("Không tìm thấy phòng đích")
        # Resolve everyone first so a bad id fails the whole batch (no partial move).
        users: list[User] = []
        for uid in user_ids:
            u = self.users.get_by_id(uid)
            if u is None:
                raise UserNotFound(f"Không tìm thấy người dùng (id={uid})")
            users.append(u)
        for u in users:
            old_dept_id = u.department_id
            if old_dept_id is not None and old_dept_id != target_department_id:
                old = self.departments.get_by_id(old_dept_id)
                if old is not None and old.head_user_id == u.id:
                    self.departments.set_head(old, None)  # they no longer head the old unit
            self.users.set_assignment(
                u, department_id=target_department_id, role_id=None, is_active=u.is_active
            )
            # Đ2: tài khoản có hồ sơ → ghi XUYÊN phòng xuống hồ sơ (1 nguồn, không split-brain).
            emp = self.employees.get_by_user_id(u.id)
            if emp is not None and emp.department_id != target_department_id:
                self.employees.update(emp, department_id=target_department_id)
            self.audit.create(
                actor_user_id=actor_id,
                action="transfer_user",
                target=f"user:{u.id}",
                detail=f"{u.username} → dept:{target_department_id}",
            )
        return len(users)

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

    def update_user(
        self,
        *,
        user_id: int,
        name: str,
        department_id: int,
        actor_id: int | None,
        allow_transfer: bool = True,
    ) -> tuple[User, bool]:
        """Edit a user's name + department (spec-08 / PBI-2003). Username is NOT editable.
        Changing department drops the current role (it belongs to the old department). Returns
        (user, role_dropped). Đổi phòng ban cần `allow_transfer` (quyền chi tiết `transfer`);
        đổi tên trong cùng phòng thì không cần."""
        user = self.users.get_by_id(user_id)
        if user is None:
            raise UserNotFound("Không tìm thấy người dùng")
        if self.departments.get_by_id(department_id) is None:
            raise DepartmentNotFound("Không tìm thấy phòng ban")
        if department_id != user.department_id and not allow_transfer:
            raise TransferForbidden("Bạn không có quyền chuyển phòng ban cho người dùng.")
        role_dropped = department_id != user.department_id and user.role_id is not None
        new_role_id = user.role_id if department_id == user.department_id else None
        self.users.set_name(user, name.strip())
        self.users.set_assignment(
            user, department_id=department_id, role_id=new_role_id, is_active=user.is_active
        )
        # Đ2: đổi phòng tài khoản có hồ sơ → ghi xuyên xuống hồ sơ (giữ 1 nguồn).
        emp = self.employees.get_by_user_id(user.id)
        if emp is not None and emp.department_id != department_id:
            self.employees.update(emp, department_id=department_id)
        self.audit.create(
            actor_user_id=actor_id,
            action="update_user",
            target=f"user:{user_id}",
            detail=f"{user.username} → dept:{department_id}"
            + (" (gỡ vai trò)" if role_dropped else ""),
        )
        return user, role_dropped

    def reset_password(self, *, user_id: int, actor_id: int | None) -> str:
        """Set a fresh temporary password (spec-08 / PBI-2006), revoke every session, audit,
        and return the plaintext ONCE (never stored/logged in plaintext)."""
        user = self.users.get_by_id(user_id)
        if user is None:
            raise UserNotFound("Không tìm thấy người dùng")
        temp = generate_temp_password()
        self.users.set_password(user, hash_password(temp))
        self.users.bump_token_version(user)
        self.tokens.revoke_all_for_user(user_id)
        self.audit.create(
            actor_user_id=actor_id,
            action="reset_password",
            target=f"user:{user_id}",
            detail=user.username,
        )
        return temp

    def revoke_sessions(self, *, user_id: int, actor_id: int | None) -> int:
        """Log the user out everywhere (spec-08): bump token_version + revoke refresh tokens."""
        if user_id == actor_id:
            raise CannotRevokeSelf("Không thể tự thu hồi phiên của tài khoản chính mình")
        user = self.users.get_by_id(user_id)
        if user is None:
            raise UserNotFound("Không tìm thấy người dùng")
        self.users.bump_token_version(user)
        n = self.tokens.revoke_all_for_user(user_id)
        self.audit.create(
            actor_user_id=actor_id,
            action="revoke_sessions",
            target=f"user:{user_id}",
            detail=user.username,
        )
        return n

    def list_sessions(self, user_id: int) -> list[RefreshToken]:
        """Live sessions (active refresh tokens) for a user (spec-08)."""
        return self.tokens.list_active_for_user(user_id)

    def list_activity(self, user_id: int) -> list[AuditLog]:
        """Recent audit rows targeting this user (spec-08)."""
        return self.audit.list_for_target(f"user:{user_id}")
