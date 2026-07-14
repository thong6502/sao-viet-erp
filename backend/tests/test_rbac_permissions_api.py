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
    assert {"dashboard", "khach_hang", "bao_gia"} <= mods
    # …but not admin modules or other KD modules it has no permission for.
    assert "vai_tro" not in mods
    assert "nguoi_dung" not in mods
    assert "san_pham" not in mods


def test_permissions_requires_auth(client):
    assert client.get("/api/auth/permissions").status_code == 401


def test_permissions_include_crud_matrix(client):
    """spec-09: response carries the full CRUD matrix per module for the current user."""
    token = client.post("/api/auth/login", json=ADMIN).json()["access_token"]
    perms = client.get("/api/auth/permissions", headers=_h(token)).json()["permissions"]
    by_key = {p["module_key"]: p for p in perms}
    # Admin (Giám đốc) has full rights on phong_ban.
    pb = by_key["phong_ban"]
    assert pb["can_read"] and pb["can_create"] and pb["can_update"] and pb["can_delete"]

    # NV Sales: can read+create+update khach_hang but NOT delete, and no phong_ban row at all.
    sales = client.get("/api/auth/permissions", headers=_h(_sales_token())).json()["permissions"]
    s_by_key = {p["module_key"]: p for p in sales}
    assert "phong_ban" not in s_by_key
    kh = s_by_key["khach_hang"]
    assert kh["can_read"] and kh["can_create"] and kh["can_update"]
    assert kh["can_delete"] is False
