"""feat-010 — GET /api/auth/permissions (readable modules for menu/route gating)."""
from __future__ import annotations

from app.db import SessionLocal
from app.repositories.rbac_repo import DepartmentRepository, RoleRepository
from app.repositories.user_repo import UserRepository
from app.security import create_access_token, hash_password

ADMIN = {"username": "admin", "password": "admin123"}


def _h(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _sales_token() -> str:
    db = SessionLocal()
    try:
        users = UserRepository(db)
        existing = users.get_by_username("sales-perm")
        if existing is not None:
            return create_access_token(str(existing.id))
        kd = DepartmentRepository(db).get_by_name("Kinh doanh")
        sales = RoleRepository(db).get_by_name_and_department("NV Sales", kd.id)
        u = users.create(
            username="sales-perm", name="S", password_hash=hash_password("x")
        )
        users.set_assignment(u, department_id=kd.id, role_id=sales.id, is_active=True)
        return create_access_token(str(u.id))
    finally:
        db.close()


def test_admin_permissions_cover_catalog(client):
    token = client.post("/api/auth/login", json=ADMIN).json()["access_token"]
    mods = set(client.get("/api/auth/permissions", headers=_h(token)).json()["modules"])
    assert {"dashboard", "khach_hang", "vai_tro", "nguoi_dung", "phong_ban"} <= mods


def test_sales_permissions_are_limited(client):
    token = _sales_token()
    mods = set(client.get("/api/auth/permissions", headers=_h(token)).json()["modules"])
    # NV Sales can read its KD modules…
    assert {"dashboard", "khach_hang", "don_hang_ban", "bao_gia"} <= mods
    # …but not admin modules or other KD modules it has no permission for.
    assert "vai_tro" not in mods
    assert "nguoi_dung" not in mods
    assert "san_pham" not in mods


def test_permissions_requires_auth(client):
    assert client.get("/api/auth/permissions").status_code == 401
