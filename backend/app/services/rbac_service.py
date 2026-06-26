"""Authorization business logic.

Resolves whether a user's single role grants a given (module, action). Pure
business logic: it reads permissions through a repository and returns a decision —
the HTTP mapping (401/403) lives in the route/dependency layer.
"""
from __future__ import annotations

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
