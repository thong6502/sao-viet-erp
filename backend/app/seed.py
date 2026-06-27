"""Idempotent startup seed: RBAC catalog + the initial admin user.

Safe to call on every startup — every step creates rows only if absent, so re-runs
do not duplicate. Seeds only the Kinh doanh + Hành chính nhân sự scope for now; the
module catalog is data and grows as other departments come online (spec-02-rbac.md).
Credentials come from config/env (SEED_ADMIN_*).
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from .config import settings
from .models.role import SCOPE_ALL, SCOPE_DEPARTMENT, SCOPE_OWN
from .repositories.rbac_repo import DepartmentRepository, ModuleRepository, RoleRepository
from .repositories.user_repo import UserRepository
from .security import hash_password

# --- Catalog (seed data; expandable) ---------------------------------------

# Module catalog: (key, label). Kinh doanh + Hành chính nhân sự / quản trị only.
MODULES: list[tuple[str, str]] = [
    ("dashboard", "Dashboard"),
    ("khach_hang", "Khách hàng"),
    ("don_hang_ban", "Đơn hàng bán"),
    ("bao_gia", "Báo giá in ấn"),
    ("tinh_gia_thanh", "Tính giá thành"),
    ("san_pham", "Sản phẩm"),
    ("hop_dong", "Hợp đồng"),
    ("phong_ban", "Phòng ban"),
    ("vai_tro", "Vai trò"),
    ("nguoi_dung", "Người dùng"),
    ("activity_log", "Nhật ký hoạt động"),
]

ALL_MODULE_KEYS = [k for k, _ in MODULES]
KD_MODULE_KEYS = [
    "dashboard",
    "khach_hang",
    "don_hang_ban",
    "bao_gia",
    "tinh_gia_thanh",
    "san_pham",
    "hop_dong",
]

DEPARTMENTS = ["Ban giám đốc", "Hành chính nhân sự", "Kinh doanh"]

ADMIN_DEPARTMENT = "Ban giám đốc"
ADMIN_ROLE = "Giám đốc"


def _full(scope: str) -> dict:
    return dict(can_read=True, can_create=True, can_update=True, can_delete=True, scope=scope)


def _rcu(scope: str) -> dict:
    return dict(can_read=True, can_create=True, can_update=True, can_delete=False, scope=scope)


def _read(scope: str) -> dict:
    return dict(
        can_read=True, can_create=False, can_update=False, can_delete=False, scope=scope
    )


# Roles: (department_name, role_name, {module_key: permission}). The minimal default
# role ("Nhân viên") is Read-only on Dashboard, scope own.
ROLES: list[tuple[str, str, dict[str, dict]]] = [
    (ADMIN_DEPARTMENT, ADMIN_ROLE, {k: _full(SCOPE_ALL) for k in ALL_MODULE_KEYS}),
    (
        "Hành chính nhân sự",
        "Trưởng phòng HCNS",
        {
            "dashboard": _read(SCOPE_ALL),
            "nguoi_dung": _rcu(SCOPE_ALL),
            "phong_ban": _read(SCOPE_ALL),
            "vai_tro": _read(SCOPE_ALL),
            "activity_log": _read(SCOPE_ALL),
        },
    ),
    ("Hành chính nhân sự", "Nhân viên", {"dashboard": _read(SCOPE_OWN)}),
    ("Kinh doanh", "Trưởng phòng KD", {k: _full(SCOPE_DEPARTMENT) for k in KD_MODULE_KEYS}),
    (
        "Kinh doanh",
        "NV Sales",
        {
            "dashboard": _read(SCOPE_OWN),
            "khach_hang": _rcu(SCOPE_OWN),
            "don_hang_ban": _rcu(SCOPE_OWN),
            "bao_gia": _rcu(SCOPE_OWN),
        },
    ),
]


# --- Seed steps (each idempotent) ------------------------------------------


def seed_modules(db: Session) -> None:
    modules = ModuleRepository(db)
    for key, label in MODULES:
        if modules.get_by_key(key) is None:
            modules.create(key=key, label=label)


def seed_departments(db: Session) -> None:
    depts = DepartmentRepository(db)
    for name in DEPARTMENTS:
        if depts.get_by_name(name) is None:
            depts.create(name=name)


def seed_roles(db: Session) -> None:
    depts = DepartmentRepository(db)
    roles = RoleRepository(db)
    for dept_name, role_name, perms in ROLES:
        dept = depts.get_by_name(dept_name)
        if dept is None:
            continue
        role = roles.get_by_name_and_department(role_name, dept.id)
        if role is None:
            role = roles.create(name=role_name, department_id=dept.id)
        # Upsert permissions (no-op row-count on re-run; keeps the matrix in sync).
        for module_key, perm in perms.items():
            roles.set_permission(role_id=role.id, module_key=module_key, **perm)


def seed_admin(db: Session) -> None:
    """Create the initial admin user if absent (no self-registration this spec)."""
    users = UserRepository(db)
    if users.get_by_email(settings.seed_admin_email) is not None:
        return
    users.create(
        email=settings.seed_admin_email,
        name=settings.seed_admin_name,
        password_hash=hash_password(settings.seed_admin_password),
    )


def link_admin(db: Session) -> None:
    """Attach the admin user to the Ban giám đốc department + Giám đốc role, and make
    them that department's head. Idempotent."""
    users = UserRepository(db)
    depts = DepartmentRepository(db)
    roles = RoleRepository(db)

    admin = users.get_by_email(settings.seed_admin_email)
    dept = depts.get_by_name(ADMIN_DEPARTMENT)
    if admin is None or dept is None:
        return
    role = roles.get_by_name_and_department(ADMIN_ROLE, dept.id)
    if role is None:
        return
    if admin.department_id != dept.id or admin.role_id != role.id or not admin.is_active:
        users.set_assignment(admin, department_id=dept.id, role_id=role.id, is_active=True)
    if dept.head_user_id != admin.id:
        depts.set_head(dept, admin.id)


def seed_all(db: Session) -> None:
    """Full idempotent seed: RBAC catalog/roles, the admin user, and its assignment."""
    seed_modules(db)
    seed_departments(db)
    seed_roles(db)
    seed_admin(db)
    link_admin(db)
