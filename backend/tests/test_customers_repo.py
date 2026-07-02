"""feat-027 — Khách hàng (CRM) data model + repository (spec-06).

Repository level: sequential unique KH### codes, soft duplicate MST lookup, and the
own/department/all scope filter + q search.
"""
from __future__ import annotations

import pytest

from app.db import SessionLocal, init_db
from app.repositories.customer_repo import CustomerRepository
from app.repositories.rbac_repo import DepartmentRepository, RoleRepository
from app.repositories.user_repo import UserRepository
from app.security import hash_password
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


class _Actor:
    def __init__(self, id: int, department_id: int | None) -> None:
        self.id = id
        self.department_id = department_id


def _kd(db):
    return DepartmentRepository(db).get_by_name("Kinh doanh")


def _mk_sale(db, username: str, dept_id: int) -> int:
    users = UserRepository(db)
    roles = RoleRepository(db)
    existing = users.get_by_username(username)
    if existing is not None:
        return existing.id
    role = roles.get_by_name_and_department("NV Sales", dept_id)
    u = users.create(username=username, name=username, password_hash=hash_password("x"))
    users.set_assignment(u, department_id=dept_id, role_id=role.id, is_active=True)
    return u.id


def _new_customer(repo: CustomerRepository, name: str, sale_id: int, tax_code=None):
    return repo.create(
        name=name,
        tax_code=tax_code,
        phone=None,
        email=None,
        address=None,
        contact_name=None,
        credit_limit=0,
        sale_user_id=sale_id,
        status="active",
    )


def test_create_generates_sequential_unique_code(db):
    repo = CustomerRepository(db)
    sale = _mk_sale(db, "sale-rt-1", _kd(db).id)
    a = _new_customer(repo, "KH A", sale)
    b = _new_customer(repo, "KH B", sale)
    assert a.code.startswith("KH") and b.code.startswith("KH")
    assert a.code != b.code
    assert int(b.code[2:]) == int(a.code[2:]) + 1
    assert len(a.code) >= 5  # "KH" + >=3 digits


def test_find_by_tax_code_returns_soft_duplicate(db):
    repo = CustomerRepository(db)
    sale = _mk_sale(db, "sale-rt-2", _kd(db).id)
    _new_customer(repo, "Có MST", sale, tax_code="0106660001")
    found = repo.find_by_tax_code("0106660001")
    assert found is not None and found.name == "Có MST"
    assert repo.find_by_tax_code("9999999999") is None
    assert repo.find_by_tax_code("") is None  # blank never matches


def test_scope_own_returns_only_owned(db):
    repo = CustomerRepository(db)
    kd = _kd(db).id
    mine = _mk_sale(db, "sale-own-a", kd)
    other = _mk_sale(db, "sale-own-b", kd)
    _new_customer(repo, "Của tôi", mine)
    _new_customer(repo, "Của người khác", other)
    rows, total = repo.list(scope="own", actor=_Actor(mine, kd))
    names = {r.name for r in rows}
    assert "Của tôi" in names
    assert "Của người khác" not in names
    assert total == sum(1 for r in rows) or total >= 1


def test_scope_department_spans_the_department(db):
    repo = CustomerRepository(db)
    kd = _kd(db).id
    a = _mk_sale(db, "sale-dep-a", kd)
    b = _mk_sale(db, "sale-dep-b", kd)
    _new_customer(repo, "Dep A cust", a)
    _new_customer(repo, "Dep B cust", b)
    rows, _ = repo.list(scope="department", actor=_Actor(a, kd))
    names = {r.name for r in rows}
    assert {"Dep A cust", "Dep B cust"} <= names


def test_scope_all_returns_every_customer(db):
    repo = CustomerRepository(db)
    kd = _kd(db).id
    a = _mk_sale(db, "sale-all-a", kd)
    _new_customer(repo, "All-scope cust", a)
    rows, total = repo.list(scope="all", actor=_Actor(0, None))
    assert total >= 1
    assert any(r.name == "All-scope cust" for r in rows)


def test_list_q_filters_by_name_mst_phone(db):
    repo = CustomerRepository(db)
    kd = _kd(db).id
    sale = _mk_sale(db, "sale-q", kd)
    repo.create(
        name="Findable Corp", tax_code="0107777777", phone="0988000111",
        email=None, address=None, contact_name=None, credit_limit=0,
        sale_user_id=sale, status="active",
    )
    actor = _Actor(sale, kd)
    # Case-insensitive substring on name (ASCII lowercasing is portable SQLite/Postgres).
    assert any(r.name == "Findable Corp" for r in repo.list(scope="own", actor=actor, q="findable")[0])
    # MST + phone substrings also match.
    assert any(r.name == "Findable Corp" for r in repo.list(scope="own", actor=actor, q="0107777777")[0])
    assert any(r.name == "Findable Corp" for r in repo.list(scope="own", actor=actor, q="0988000111")[0])
    assert repo.list(scope="own", actor=actor, q="khong-ton-tai-zzz")[0] == []


def test_can_access_enforces_scope(db):
    repo = CustomerRepository(db)
    kd = _kd(db).id
    mine = _mk_sale(db, "sale-acc-a", kd)
    other = _mk_sale(db, "sale-acc-b", kd)
    c_mine = _new_customer(repo, "acc mine", mine)
    c_other = _new_customer(repo, "acc other", other)
    actor = _Actor(mine, kd)
    assert repo.can_access(customer=c_mine, scope="own", actor=actor) is True
    assert repo.can_access(customer=c_other, scope="own", actor=actor) is False
    # department scope: both visible (same dept)
    assert repo.can_access(customer=c_other, scope="department", actor=actor) is True
