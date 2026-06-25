"""HTTP routers. Routes parse/validate and shape responses only — no business logic."""
from . import auth

__all__ = ["auth"]
