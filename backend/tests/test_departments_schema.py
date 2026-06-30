"""Department tree + code/description columns (feat-023, spec-05).

Repository level: proves create() generates a unique sequential PB-code, stores
description + parent_id, and that children_of/subtree walk the org tree correctly.
"""
from __future__ import annotations

import pytest

from app.db import SessionLocal, init_db
from app.repositories.rbac_repo import DepartmentRepository
from app.seed import seed_all


@pytest.fixture
def db():
    init_db()
    session = SessionLocal()
    try:
        seed_all(session)
        yield session
    finally:
        session.close()


def _repo(session) -> DepartmentRepository:
    return DepartmentRepository(session)


def test_create_generates_sequential_unique_code(db):
    repo = _repo(db)
    a = repo.create(name="Phòng A (s5)")
    b = repo.create(name="Phòng B (s5)")
    assert a.code.startswith("PB") and b.code.startswith("PB")
    assert a.code != b.code
    # Consecutive creates increment by one.
    assert int(b.code[2:]) == int(a.code[2:]) + 1
    # Codes are zero-padded to at least 3 digits.
    assert len(a.code) >= 5  # "PB" + >=3 digits


def test_seeded_departments_have_codes(db):
    # seed_all created the base departments; each must carry a generated code.
    for dept in _repo(db).list_all():
        assert dept.code and dept.code.startswith("PB")


def test_create_stores_description_and_parent(db):
    repo = _repo(db)
    parent = repo.create(name="Cha (s5)")
    child = repo.create(name="Con (s5)", description="Phòng con để test", parent_id=parent.id)
    assert child.description == "Phòng con để test"
    assert child.parent_id == parent.id
    # Description defaults to null, parent defaults to root (null).
    assert parent.description is None
    assert parent.parent_id is None


def test_children_of_returns_direct_children_only(db):
    repo = _repo(db)
    root = repo.create(name="Root (s5)")
    c1 = repo.create(name="C1 (s5)", parent_id=root.id)
    c2 = repo.create(name="C2 (s5)", parent_id=root.id)
    grandchild = repo.create(name="G1 (s5)", parent_id=c1.id)
    direct = {d.id for d in repo.children_of(root.id)}
    assert direct == {c1.id, c2.id}
    assert grandchild.id not in direct  # grandchild is not a direct child of root


def test_subtree_returns_root_plus_all_descendants(db):
    repo = _repo(db)
    root = repo.create(name="Tree root (s5)")
    c1 = repo.create(name="Tree c1 (s5)", parent_id=root.id)
    c2 = repo.create(name="Tree c2 (s5)", parent_id=root.id)
    g1 = repo.create(name="Tree g1 (s5)", parent_id=c1.id)
    g2 = repo.create(name="Tree g2 (s5)", parent_id=g1.id)  # 3 levels deep

    ids = [d.id for d in repo.subtree(root.id)]
    assert set(ids) == {root.id, c1.id, c2.id, g1.id, g2.id}
    assert len(ids) == len(set(ids))  # no duplicates
    assert ids[0] == root.id  # root first (breadth-first)


def test_subtree_unknown_root_is_empty(db):
    assert _repo(db).subtree(10_000_000) == []
