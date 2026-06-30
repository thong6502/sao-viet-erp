"""Authentication business logic.

Verifies credentials and issues tokens. Raises a domain error (AuthError) that the
route maps to HTTP — the service itself stays framework-agnostic.
"""
from __future__ import annotations

from ..models.user import User
from ..repositories.user_repo import UserRepository
from ..security import create_access_token, hash_password, verify_password


class AuthError(Exception):
    """Raised when authentication fails. The route maps this to 401."""


class PasswordChangeError(Exception):
    """Raised when a self-service password change is rejected (wrong current password,
    or the new password equals the current one). The route maps this to 400 and surfaces
    the message verbatim (spec-04)."""


class AuthService:
    def __init__(self, users: UserRepository) -> None:
        self.users = users

    def authenticate(self, username: str, password: str) -> User:
        """Return the user on valid credentials, else raise AuthError.

        Login is by username (spec-0001). Generic failure for both unknown username and
        wrong password so we never leak which accounts exist (no user enumeration —
        docs/SECURITY.md).
        """
        user = self.users.get_by_username((username or "").strip())
        if user is None or not verify_password(password, user.password_hash):
            raise AuthError("Invalid username or password")
        # A locked account cannot authenticate (generic message — no enumeration).
        if not user.is_active:
            raise AuthError("Invalid username or password")
        return user

    def login(self, username: str, password: str) -> tuple[str, User]:
        """Authenticate and mint an access token. Returns (token, user)."""
        user = self.authenticate(username, password)
        token = create_access_token(subject=str(user.id), token_version=user.token_version)
        return token, user

    def change_password(self, user: User, current_password: str, new_password: str) -> User:
        """Self-service password change (spec-04).

        Verifies the current password (bcrypt), refuses an unchanged password, then stores
        the new hash and bumps `token_version` so every previously-issued access token dies.
        The caller (route) revokes the user's refresh tokens. Raises PasswordChangeError
        (→ 400) on a wrong current password or a new == current password. Pydantic enforces
        the strength rules before we get here (→ 422).
        """
        if not verify_password(current_password, user.password_hash):
            raise PasswordChangeError("Mật khẩu hiện tại không đúng")
        if verify_password(new_password, user.password_hash):
            raise PasswordChangeError("Mật khẩu mới phải khác mật khẩu hiện tại")
        self.users.set_password(user, hash_password(new_password))
        # Hard-revoke every outstanding access token (spec-03 lever).
        self.users.bump_token_version(user)
        return user

    def user_from_token_subject(self, subject: str | None) -> User:
        """Resolve the `sub` claim back to a live user, or raise AuthError."""
        if not subject:
            raise AuthError("Invalid token")
        try:
            user_id = int(subject)
        except (TypeError, ValueError):
            raise AuthError("Invalid token") from None
        user = self.users.get_by_id(user_id)
        if user is None:
            raise AuthError("Invalid token")
        return user
