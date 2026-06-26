"""feat-011 — Activity Log API (GET /api/audit, read-only)."""
from __future__ import annotations

from app.db import SessionLocal
from app.repositories.rbac_repo import DepartmentRepository, RoleRepository
from app.repositories.user_repo import UserRepository
from app.security import create_access_token, hash_password

ADMIN = {"email": "admin@example.com", "password": "admin123"}


def _h(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _sales_token() -> str:
    db = SessionLocal()
    try:
        users = UserRepository(db)
        existing = users.get_by_email("sales-audit@example.com")
        if existing is not None:
            return create_access_token(str(existing.id))
        kd = DepartmentRepository(db).get_by_name("Kinh doanh")
        sales = RoleRepository(db).get_by_name_and_department("NV Sales", kd.id)
        u = users.create(
            email="sales-audit@example.com", name="S", password_hash=hash_password("x")
        )
        users.set_assignment(u, department_id=kd.id, role_id=sales.id, is_active=True)
        return create_access_token(str(u.id))
    finally:
        db.close()


def test_action_appears_in_audit_log(client):
    token = client.post("/api/auth/login", json=ADMIN).json()["access_token"]
    # An action that writes an audit row.
    client.post("/api/departments", json={"name": "Phòng Audit Test"}, headers=_h(token))

    rows = client.get("/api/audit", headers=_h(token)).json()
    match = [
        r
        for r in rows
        if r["action"] == "create_department" and "Phòng Audit Test" in r["detail"]
    ]
    assert match, "expected a create_department audit row"
    assert match[0]["actor_name"] == "Admin"
    assert match[0]["created_at"]  # serialized timestamp present


def test_audit_requires_permission(client):
    token = _sales_token()  # NV Sales has no activity_log permission
    assert client.get("/api/audit", headers=_h(token)).status_code == 403
