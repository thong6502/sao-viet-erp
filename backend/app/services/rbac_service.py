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

_ACTION_ATTR = {
    ACTION_READ: "can_read",
    ACTION_CREATE: "can_create",
    ACTION_UPDATE: "can_update",
    ACTION_DELETE: "can_delete",
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
