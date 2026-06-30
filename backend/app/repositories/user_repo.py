"""User data access. All SQL goes through SQLAlchemy bound parameters (no string
formatting of input — docs/SECURITY.md)."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models.user import User


class UserRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_by_id(self, user_id: int) -> User | None:
        return self.db.get(User, user_id)

    def get_by_username(self, username: str) -> User | None:
        """Resolve the login identifier (spec-0001). A blank value never matches."""
        if not username:
            return None
        stmt = select(User).where(User.username == username)
        return self.db.execute(stmt).scalar_one_or_none()

    def create(self, *, username: str, name: str, password_hash: str) -> User:
        user = User(username=username, name=name, password_hash=password_hash)
        self.db.add(user)
        self.db.commit()
        self.db.refresh(user)
        return user

    def set_assignment(
        self,
        user: User,
        *,
        department_id: int | None,
        role_id: int | None,
        is_active: bool = True,
    ) -> User:
        """Set a user's department + role (RBAC assignment)."""
        user.department_id = department_id
        user.role_id = role_id
        user.is_active = is_active
        self.db.commit()
        self.db.refresh(user)
        return user

    def set_role(self, user: User, role_id: int | None) -> User:
        user.role_id = role_id
        self.db.commit()
        self.db.refresh(user)
        return user

    def set_active(self, user: User, is_active: bool) -> User:
        user.is_active = is_active
        self.db.commit()
        self.db.refresh(user)
        return user

    def bump_token_version(self, user: User) -> User:
        """Invalidate every outstanding access token for the user (logout-all / lock)."""
        user.token_version = (user.token_version or 0) + 1
        self.db.commit()
        self.db.refresh(user)
        return user

    def list_all(self) -> list[User]:
        return list(self.db.execute(select(User).order_by(User.id)).scalars())

    def count(self) -> int:
        from sqlalchemy import func

        return self.db.execute(select(func.count()).select_from(User)).scalar_one()

    def count_by_role(self, role_id: int) -> int:
        from sqlalchemy import func

        return self.db.execute(
            select(func.count()).select_from(User).where(User.role_id == role_id)
        ).scalar_one()

    def count_by_department(self, department_id: int) -> int:
        from sqlalchemy import func

        return self.db.execute(
            select(func.count()).select_from(User).where(User.department_id == department_id)
        ).scalar_one()

    def list_by_department(self, department_id: int) -> list[User]:
        stmt = select(User).where(User.department_id == department_id).order_by(User.id)
        return list(self.db.execute(stmt).scalars())
