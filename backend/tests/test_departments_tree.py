"""feat-026 / PBI-4005 — delete a department by branch, with personnel block.

API + DB level: the subtree preview endpoint, cascade-delete of a whole branch (units +
their roles), the block when any unit in the branch still has a user, and one AuditLog row
per deleted unit.
"""
from __future__ import annotations

from sqlalchemy import func, select

from app.db import SessionLocal
from app.models.audit import AuditLog
from app.repositories.rbac_repo import DepartmentRepository, RoleRepository
from app.repositories.user_repo import UserRepository
from app.security import hash_password

ADMIN = {"username": "admin", "password": "admin123"}


def _token(client) -> str:
    return client.post("/api/auth/login", json=ADMIN).json()["access_token"]


def _h(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _mk(client, token, name, parent_id=None) -> dict:
    return client.post(
        "/api/departments", json={"name": name, "parent_id": parent_id}, headers=_h(token)
    ).json()


def _count_delete_audits() -> int:
    db = SessionLocal()
    try:
        return db.execute(
            select(func.count())
            .select_from(AuditLog)
            .where(AuditLog.action == "delete_department")
        ).scalar_one()
    finally:
        db.close()


def test_subtree_endpoint_lists_whole_branch(client):
    token = _token(client)
    root = _mk(client, token, "Tree A")
    c1 = _mk(client, token, "Tree A-1", root["id"])
    g1 = _mk(client, token, "Tree A-1-a", c1["id"])

    resp = client.get(f"/api/departments/{root['id']}/subtree", headers=_h(token))
    assert resp.status_code == 200
    rows = resp.json()
    assert {r["id"] for r in rows} == {root["id"], c1["id"], g1["id"]}
    assert all(r.get("code") and r.get("name") for r in rows)


def test_delete_cascades_branch_and_roles(client):
    token = _token(client)
    root = _mk(client, token, "Cas A")
    c1 = _mk(client, token, "Cas A-1", root["id"])

    db = SessionLocal()
    try:
        RoleRepository(db).create(name="Vai trò con", department_id=c1["id"])
    finally:
        db.close()

    resp = client.delete(f"/api/departments/{root['id']}", headers=_h(token))
    assert resp.status_code == 204

    db = SessionLocal()
    try:
        depts = DepartmentRepository(db)
        assert depts.get_by_id(root["id"]) is None
        assert depts.get_by_id(c1["id"]) is None  # child gone too
        assert RoleRepository(db).count_by_department(c1["id"]) == 0  # roles cascaded
    finally:
        db.close()


def test_delete_blocked_when_any_descendant_has_user(client):
    token = _token(client)
    root = _mk(client, token, "Blk A")
    c1 = _mk(client, token, "Blk A-1", root["id"])
    g1 = _mk(client, token, "Blk A-1-a", c1["id"])

    db = SessionLocal()
    try:
        u = UserRepository(db).create(
            username="deep-user", name="D", password_hash=hash_password("x")
        )
        UserRepository(db).set_assignment(u, department_id=g1["id"], role_id=None, is_active=True)
    finally:
        db.close()

    resp = client.delete(f"/api/departments/{root['id']}", headers=_h(token))
    assert resp.status_code == 409  # a grandchild still has personnel
    assert "nhân sự" in resp.json()["detail"]

    # Nothing was deleted.
    db = SessionLocal()
    try:
        depts = DepartmentRepository(db)
        assert depts.get_by_id(root["id"]) is not None
        assert depts.get_by_id(g1["id"]) is not None
    finally:
        db.close()


def test_delete_writes_one_audit_per_deleted_unit(client):
    token = _token(client)
    root = _mk(client, token, "Aud A")
    _mk(client, token, "Aud A-1", root["id"])
    _mk(client, token, "Aud A-2", root["id"])

    before = _count_delete_audits()
    resp = client.delete(f"/api/departments/{root['id']}", headers=_h(token))
    assert resp.status_code == 204
    assert _count_delete_audits() - before == 3  # root + 2 children
