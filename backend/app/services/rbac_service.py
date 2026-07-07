"""Authorization business logic.

Resolves whether a user's single role grants a given (module, action). Pure
business logic: it reads permissions through a repository and returns a decision —
the HTTP mapping (401/403) lives in the route/dependency layer.
"""
from __future__ import annotations

from ..models.role import SCOPE_ALL, SCOPE_DEPARTMENT, SCOPE_OWN
from ..models.user import User
from ..repositories.rbac_repo import RoleRepository

# Permission actions, mapped to the RolePermission boolean columns.
ACTION_READ = "read"
ACTION_CREATE = "create"
ACTION_UPDATE = "update"
ACTION_DELETE = "delete"
# Quyền chi tiết (Cách B) — hành động đặc thù ngoài CRUD.
ACTION_REASSIGN = "reassign"
ACTION_EXPORT = "export"
ACTION_VIEW_DEBT = "view_debt"
ACTION_APPROVE = "approve"  # bao_gia: duyệt báo giá (đổi trạng thái → Khách duyệt)
ACTION_MANAGE_STATUS = "manage_status"  # don_hang_ban: chốt / hủy đơn
ACTION_RESET_PASSWORD = "reset_password"  # nguoi_dung: đặt lại mật khẩu
# Nhóm 1 — thao tác đặc thù khác:
ACTION_LOCK = "lock"  # nguoi_dung: khóa / mở tài khoản
ACTION_REVOKE_SESSIONS = "revoke_sessions"  # nguoi_dung: thu hồi mọi phiên
ACTION_ASSIGN_ROLE = "assign_role"  # nguoi_dung: gán vai trò (đơn + hàng loạt)
ACTION_TRANSFER = "transfer"  # nguoi_dung: chuyển phòng ban
ACTION_SET_HEAD = "set_head"  # phong_ban: đặt trưởng phòng
ACTION_REQUOTE = "requote"  # bao_gia: tạo bản mới (re-quote)
ACTION_MANAGE_PRICE = "manage_price"  # dm_*: cập nhật bảng giá theo mốc
ACTION_CANCEL = "cancel"  # bao_gia: hủy báo giá (→ Đã hủy) | don_hang_ban: hủy đơn
ACTION_MANAGE_PERMISSIONS = "manage_permissions"  # vai_tro: sửa ma trận phân quyền
ACTION_CLONE = "clone"  # dm_giay_vat_tu: nhân bản giấy
ACTION_TOGGLE_ACTIVE = "toggle_active"  # dm_giay_vat_tu: bật/tắt hoạt động
ACTION_REPARENT = "reparent"  # phong_ban: đổi cấp trên (cây tổ chức)
ACTION_VIEW_SALARY = "view_salary"  # nhan_su: xem dữ liệu nhạy cảm (lương/BHXH) của hồ sơ
ACTION_ADJUST = "adjust"  # nhan_su (Chấm công): điều chỉnh công qua punch nguồn (chấm bù/sửa)
# Ghi chú: don_hang_ban tái dùng ACTION_APPROVE (= "Chốt đơn") và ACTION_CANCEL (= "Hủy đơn").

_ACTION_ATTR = {
    ACTION_READ: "can_read",
    ACTION_CREATE: "can_create",
    ACTION_UPDATE: "can_update",
    ACTION_DELETE: "can_delete",
    ACTION_REASSIGN: "can_reassign",
    ACTION_EXPORT: "can_export",
    ACTION_VIEW_DEBT: "can_view_debt",
    ACTION_APPROVE: "can_approve",
    ACTION_MANAGE_STATUS: "can_manage_status",
    ACTION_RESET_PASSWORD: "can_reset_password",
    ACTION_LOCK: "can_lock",
    ACTION_REVOKE_SESSIONS: "can_revoke_sessions",
    ACTION_ASSIGN_ROLE: "can_assign_role",
    ACTION_TRANSFER: "can_transfer",
    ACTION_SET_HEAD: "can_set_head",
    ACTION_REQUOTE: "can_requote",
    ACTION_MANAGE_PRICE: "can_manage_price",
    ACTION_CANCEL: "can_cancel",
    ACTION_MANAGE_PERMISSIONS: "can_manage_permissions",
    ACTION_CLONE: "can_clone",
    ACTION_TOGGLE_ACTIVE: "can_toggle_active",
    ACTION_REPARENT: "can_reparent",
    ACTION_VIEW_SALARY: "can_view_salary",
    ACTION_ADJUST: "can_adjust",
}


class AuthorizationService:
    def __init__(self, roles: RoleRepository) -> None:
        self.roles = roles

    def can(self, user: User, module_key: str, action: str) -> bool:
        """True if the user's role grants `action` on `module_key`.

        A user with no role, or no permission row for the module, has no access.
        """
        attr = _ACTION_ATTR.get(action)
        if attr is None:
            raise ValueError(f"Unknown action: {action!r}")
        if user.role_id is None:
            return False
        perm = self.roles.get_permission(user.role_id, module_key)
        if perm is None:
            return False
        return bool(getattr(perm, attr))

    def readable_modules(self, user: User) -> list[str]:
        """Module keys the user's role can Read — drives sidebar/route gating."""
        if user.role_id is None:
            return []
        return [p.module_key for p in self.roles.permissions_for(user.role_id) if p.can_read]

    def capabilities(self, user: User) -> list[dict]:
        """Full CRUD matrix of the user's role, per module (spec-09 UI action gating).
        Empty if the user has no role."""
        if user.role_id is None:
            return []
        return [
            {
                "module_key": p.module_key,
                "can_read": p.can_read,
                "can_create": p.can_create,
                "can_update": p.can_update,
                "can_delete": p.can_delete,
                "scope": p.scope,
                "can_reassign": p.can_reassign,
                "can_export": p.can_export,
                "can_view_debt": p.can_view_debt,
                "can_approve": p.can_approve,
                "can_manage_status": p.can_manage_status,
                "can_reset_password": p.can_reset_password,
                "can_lock": p.can_lock,
                "can_revoke_sessions": p.can_revoke_sessions,
                "can_assign_role": p.can_assign_role,
                "can_transfer": p.can_transfer,
                "can_set_head": p.can_set_head,
                "can_requote": p.can_requote,
                "can_manage_price": p.can_manage_price,
                "can_cancel": p.can_cancel,
                "can_manage_permissions": p.can_manage_permissions,
                "can_clone": p.can_clone,
                "can_toggle_active": p.can_toggle_active,
                "can_reparent": p.can_reparent,
                "can_view_salary": p.can_view_salary,
                "can_adjust": p.can_adjust,
            }
            for p in self.roles.permissions_for(user.role_id)
        ]

    def scope_for(self, user: User, module_key: str) -> str | None:
        """The data scope (own|department|all) the user's role has on a module, or
        None if the user has no permission row for it. Callers feed this to
        `apply_scope` to narrow a list query."""
        if user.role_id is None:
            return None
        perm = self.roles.get_permission(user.role_id, module_key)
        return perm.scope if perm is not None else None


# --- Data-scope filtering (pure; reusable by any module's list query) -------


def scope_filter(*, scope: str, actor, owner_col, dept_col):
    """Build the SQLAlchemy filter expression for a scope, or None for `all`.

    `owner_col` / `dept_col` are the record's owner-user and owner-department
    columns (ORM attribute or Core column); `actor` is the requesting user (reads
    `.id` and `.department_id`). Pure: no session/HTTP coupling.
    """
    if scope == SCOPE_ALL:
        return None
    if scope == SCOPE_DEPARTMENT:
        return dept_col == actor.department_id
    if scope == SCOPE_OWN:
        return owner_col == actor.id
    raise ValueError(f"Unknown scope: {scope!r}")


def apply_scope(stmt, *, scope: str, actor, owner_col, dept_col):
    """Return `stmt` narrowed to the rows the scope allows (unchanged for `all`)."""
    condition = scope_filter(scope=scope, actor=actor, owner_col=owner_col, dept_col=dept_col)
    return stmt if condition is None else stmt.where(condition)
