"""Authentication business logic.

Verifies credentials and issues tokens. Raises a domain error (AuthError) that the
route maps to HTTP — the service itself stays framework-agnostic.
"""
from __future__ import annotations

from ..models.user import User
from ..repositories.user_repo import UserRepository
from ..security import create_access_token, verify_password


class AuthError(Exception):
    """Raised when authentication fails. The route maps this to 401."""


class AuthService:
    def __init__(self, users: UserRepository) -> None:
        self.users = users

    def authenticate(self, email: str, password: str) -> User:
        """Return the user on valid credentials, else raise AuthError.

        Generic failure for both unknown email and wrong password so we never
        leak which accounts exist (no user enumeration — docs/SECURITY.md).
        """
        user = self.users.get_by_email(email)
        if user is None or not verify_password(password, user.password_hash):
            raise AuthError("Invalid email or password")
        return user

    def login(self, email: str, password: str) -> tuple[str, User]:
        """Authenticate and mint an access token. Returns (token, user)."""
        user = self.authenticate(email, password)
        token = create_access_token(subject=str(user.id))
        return token, user

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
