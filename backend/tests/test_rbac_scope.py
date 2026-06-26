"""feat-006 — data-scope resolver.

`apply_scope` narrows a query to own / department / all. Tested against a throwaway
fixture table (its own MetaData, NOT Base — so the schema-doc guard ignores it), and
`scope_for` is checked against the seeded roles.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from sqlalchemy import Column, Integer, MetaData, Table, insert, select

from app.db import SessionLocal, engine, init_db
from app.models.role import SCOPE_ALL, SCOPE_DEPARTMENT, SCOPE_OWN
from app.repositories.rbac_repo import DepartmentRepository, RoleRepository
from app.services.rbac_service import AuthorizationService, apply_scope
from app.seed import seed_all

# A standalone fixture table (not registered on Base.metadata).
_meta = MetaData()
demo = Table(
    "scope_demo",
    _meta,
    Column("id", Integer, primary_key=True),
    Column("owner_user_id", Integer, nullable=False),
    Column("owner_department_id", Integer, nullable=False),
)

# Three rows: two owned in dept 10 (by users 1 and 2), one in dept 20 (user 3).
_ROWS = [
    {"id": 1, "owner_user_id": 1, "owner_department_id": 10},
    {"id": 2, "owner_user_id": 2, "owner_department_id": 10},
    {"id": 3, "owner_user_id": 3, "owner_department_id": 20},
]


@pytest.fixture
def demo_table():
    _meta.create_all(engine)
    with engine.begin() as conn:
        conn.execute(demo.delete())
        conn.execute(insert(demo), _ROWS)
    yield


def _scoped_ids(scope: str, actor) -> list[int]:
    stmt = apply_scope(
        select(demo.c.id),
        scope=scope,
        actor=actor,
        owner_col=demo.c.owner_user_id,
        dept_col=demo.c.owner_department_id,
    )
    with engine.begin() as conn:
        return sorted(row[0] for row in conn.execute(stmt))


def test_scope_own_returns_only_actor_rows(demo_table):
    actor = SimpleNamespace(id=1, department_id=10)
    assert _scoped_ids(SCOPE_OWN, actor) == [1]


def test_scope_department_returns_same_department(demo_table):
    actor = SimpleNamespace(id=1, department_id=10)
    assert _scoped_ids(SCOPE_DEPARTMENT, actor) == [1, 2]


def test_scope_all_returns_everything(demo_table):
    actor = SimpleNamespace(id=1, department_id=10)
    assert _scoped_ids(SCOPE_ALL, actor) == [1, 2, 3]


@pytest.fixture
def db():
    init_db()
    session = SessionLocal()
    try:
        seed_all(session)
        yield session
    finally:
        session.close()


def test_scope_for_reads_role_permission(db):
    depts = DepartmentRepository(db)
    roles = RoleRepository(db)
    authz = AuthorizationService(roles)

    kd = depts.get_by_name("Kinh doanh")
    bgd = depts.get_by_name("Ban giám đốc")
    hcns = depts.get_by_name("Hành chính nhân sự")

    sales = roles.get_by_name_and_department("NV Sales", kd.id)
    giam_doc = roles.get_by_name_and_department("Giám đốc", bgd.id)
    nhan_vien = roles.get_by_name_and_department("Nhân viên", hcns.id)

    assert authz.scope_for(SimpleNamespace(role_id=sales.id), "khach_hang") == SCOPE_OWN
    assert authz.scope_for(SimpleNamespace(role_id=giam_doc.id), "khach_hang") == SCOPE_ALL
    # Minimal role has no khach_hang permission -> no scope.
    assert authz.scope_for(SimpleNamespace(role_id=nhan_vien.id), "khach_hang") is None
