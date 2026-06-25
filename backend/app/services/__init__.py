"""Services — framework-agnostic business logic. No HTTP, no raw SQL."""
from .auth_service import AuthError, AuthService

__all__ = ["AuthError", "AuthService"]
