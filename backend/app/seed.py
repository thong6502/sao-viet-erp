"""Idempotent seed of the initial admin user (no self-registration this sprint).

Credentials come from config/env (SEED_ADMIN_*). Safe to call on every startup:
it creates the user only if absent.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from .config import settings
from .repositories.user_repo import UserRepository
from .security import hash_password


def seed_admin(db: Session) -> None:
    users = UserRepository(db)
    if users.get_by_email(settings.seed_admin_email) is not None:
        return
    users.create(
        email=settings.seed_admin_email,
        name=settings.seed_admin_name,
        password_hash=hash_password(settings.seed_admin_password),
    )
