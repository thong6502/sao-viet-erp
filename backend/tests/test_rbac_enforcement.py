"""feat-005 — permission enforcement layer.

Exercises require_permission() over a tiny guarded app: a user whose role grants the
permission gets 200; one without gets 403; an unauthenticated request gets 401; a
locked account is rejected even with a valid token.
"""
from __future__ import annotations

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from app.db import SessionLocal, init_db
from app.deps import get_current_user, require_permission
from app.repositories.rbac_repo import DepartmentRepository, RoleRepository
from app.repositories.user_repo import UserRepository
from app.security import create_access_token, hash_password
from app.seed import seed_all


def _guarded_app() -> FastAPI:
    app = FastAPI()

    @app.get("/guarded")
    def guarded(user=Depends(require_permission("khach_hang", "read"))):
        return {"ok": True, "user_id": user.id}

    @app.get("/whoami")
    def whoami(user=Depends(get_current_user)):
        return {"id": user.id}

    return app


@pytest.fixture
def db():
    init_db()
    session = SessionLocal()
    try:
        seed_all(session)
        yield session
    finally:
        session.close()


def _bearer(user_id: int) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(str(user_id))}"}


def _admin(session):
    return UserRepository(session).get_by_username("admin")


def _minimal_employee(session):
    """A user holding the minimal 'Nhân viên' role (Dashboard read only — no
    khach_hang permission). Idempotent within the shared in-memory DB."""
    users = UserRepository(session)
    existing = users.get_by_username("nv")
    if existing is not None:
        return existing
    depts = DepartmentRepository(session)
    roles = RoleRepository(session)
    hcns = depts.get_by_name("Hành chính nhân sự")
    nhan_vien = roles.get_by_name_and_department("Nhân viên", hcns.id)
    user = users.create(username="nv", name="NV", password_hash=hash_password("x"))
    users.set_assignment(
        user, department_id=hcns.id, role_id=nhan_vien.id, is_active=True
    )
    return user


def test_allowed_user_gets_200(db):
    admin = _admin(db)  # Giám đốc role -> khach_hang read granted
    resp = TestClient(_guarded_app()).get("/guarded", headers=_bearer(admin.id))
    assert resp.status_code == 200
    assert resp.json()["user_id"] == admin.id


def test_missing_permission_is_403(db):
    nv = _minimal_employee(db)
    resp = TestClient(_guarded_app()).get("/guarded", headers=_bearer(nv.id))
    assert resp.status_code == 403
    assert resp.json()["detail"] == "Bạn không có quyền thực hiện thao tác này"


def test_unauthenticated_is_401(db):
    resp = TestClient(_guarded_app()).get("/guarded")
    assert resp.status_code == 401


def test_locked_user_is_rejected(db):
    nv = _minimal_employee(db)
    UserRepository(db).set_assignment(
        nv, department_id=nv.department_id, role_id=nv.role_id, is_active=False
    )
    # Even an authentication-only route rejects a locked account.
    resp = TestClient(_guarded_app()).get("/whoami", headers=_bearer(nv.id))
    assert resp.status_code == 403
    assert resp.json()["detail"] == "Tài khoản đã bị khóa"
