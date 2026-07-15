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

    def next_code(self) -> str:
        """Next sequential ACCOUNT code: 'TK' + zero-padded number. Tiền tố 'TK' tách khỏi
        employees.code ('NV###') để không nhầm tài khoản với hồ sơ (Đ1). Dựa max số TK hiện
        có nên mã không tái dùng dù có xoá."""
        max_n = 0
        for code in self.db.execute(select(User.code)).scalars():
            if code and code.startswith("TK"):
                try:
                    max_n = max(max_n, int(code[2:]))
                except ValueError:
                    continue
        return f"TK{max_n + 1:03d}"

    def create(self, *, username: str, name: str, password_hash: str) -> User:
        user = User(
            username=username,
            name=name,
            password_hash=password_hash,
            code=self.next_code(),
        )
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

    def set_name(self, user: User, name: str) -> User:
        """Update the user's display name (self-service profile edit, spec-04)."""
        user.name = name
        self.db.commit()
        self.db.refresh(user)
        return user

    def set_avatar(self, user: User, avatar_url: str | None) -> User:
        """Set or clear the user's avatar path (spec-04)."""
        user.avatar_url = avatar_url
        self.db.commit()
        self.db.refresh(user)
        return user

    def sync_from_employee(self, user: User, *, name: str, department_id: int | None,
                           avatar_url: str | None = None) -> User:
        """Đồng bộ 1 chiều HỒ SƠ→TÀI KHOẢN (Đ1: hồ sơ là nguồn) — tên hiển thị + phòng
        (data-scope RBAC). Ảnh CHỈ ghi khi hồ sơ CÓ ảnh (tránh xoá avatar tài khoản khi hồ sơ
        chưa có ảnh). KHÔNG đụng role."""
        user.name = name
        user.department_id = department_id
        if avatar_url:
            user.avatar_url = avatar_url
        self.db.commit()
        self.db.refresh(user)
        return user

    def set_password(self, user: User, password_hash: str) -> User:
        """Replace the user's bcrypt password hash (self-service change, spec-04)."""
        user.password_hash = password_hash
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
