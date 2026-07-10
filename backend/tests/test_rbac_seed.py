"""feat-004 — RBAC data model + seed.

Verifies the RBAC tables exist, the catalog/roles seed correctly, the admin user is
linked to the Ban giám đốc / Giám đốc role, and that seeding is idempotent.
"""
from __future__ import annotations

from sqlalchemy import func, select

from app.db import Base, SessionLocal
from app.models.role import SCOPE_ALL, SCOPE_OWN, RolePermission
from app.models.user import User
from app.repositories.rbac_repo import (
    DepartmentRepository,
    ModuleRepository,
    RoleRepository,
)
from app.repositories.user_repo import UserRepository
from app.seed import MODULES, seed_all


def test_rbac_tables_registered():
    for table in ("users", "departments", "roles", "role_permissions", "modules", "audit_logs"):
        assert table in Base.metadata.tables


def test_user_has_rbac_columns():
    cols = Base.metadata.tables["users"].columns
    for col in ("department_id", "role_id", "is_active"):
        assert col in cols


def test_modules_seeded(client):
    db = SessionLocal()
    try:
        modules = ModuleRepository(db)
        assert modules.count() == len(MODULES)
        keys = {m.key for m in modules.list_all()}
        assert {"dashboard", "khach_hang", "vai_tro", "nguoi_dung"} <= keys
        # Các phân hệ mới (Thu mua/Kế toán/Sản xuất/Kho) đã có module riêng.
        assert {"thu_mua", "ke_toan", "san_xuat", "kho"} <= keys
    finally:
        db.close()


def test_roles_and_permissions_seeded(client):
    db = SessionLocal()
    try:
        depts = DepartmentRepository(db)
        roles = RoleRepository(db)

        bgd = depts.get_by_name("Ban giám đốc")
        assert bgd is not None
        giam_doc = roles.get_by_name_and_department("Giám đốc", bgd.id)
        assert giam_doc is not None
        # Giám đốc = full CRUD + scope all on khach_hang.
        perm = roles.get_permission(giam_doc.id, "khach_hang")
        assert perm is not None
        assert perm.can_read and perm.can_create and perm.can_update and perm.can_delete
        assert perm.scope == SCOPE_ALL

        kd = depts.get_by_name("Kinh doanh")
        sales = roles.get_by_name_and_department("NV Sales", kd.id)
        assert sales is not None
        sales_perm = roles.get_permission(sales.id, "khach_hang")
        # NV Sales: can edit but only own data, and cannot delete.
        assert sales_perm.can_read and sales_perm.can_create and sales_perm.can_update
        assert not sales_perm.can_delete
        assert sales_perm.scope == SCOPE_OWN
    finally:
        db.close()


def test_admin_linked_to_dept_and_role(client):
    db = SessionLocal()
    try:
        users = UserRepository(db)
        depts = DepartmentRepository(db)
        roles = RoleRepository(db)

        admin = users.get_by_username("admin")
        assert admin is not None
        assert admin.is_active is True
        assert admin.department_id is not None and admin.role_id is not None

        dept = depts.get_by_id(admin.department_id)
        role = roles.get_by_id(admin.role_id)
        assert dept.name == "Ban giám đốc"
        assert role.name == "Giám đốc"
        # Admin is the head of their department.
        assert dept.head_user_id == admin.id
    finally:
        db.close()


def test_seed_is_idempotent(client):
    db = SessionLocal()
    try:
        def counts() -> tuple[int, int, int, int, int]:
            return (
                ModuleRepository(db).count(),
                DepartmentRepository(db).count(),
                RoleRepository(db).count(),
                db.execute(select(func.count()).select_from(RolePermission)).scalar_one(),
                db.execute(select(func.count()).select_from(User)).scalar_one(),
            )

        before = counts()
        seed_all(db)
        seed_all(db)
        assert counts() == before
    finally:
        db.close()
