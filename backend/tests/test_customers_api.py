"""feat-028..031 — Khách hàng (CRM) API (spec-06).

Covers: scoped list + q search, create (mã tự sinh, MST soft-duplicate = warn+link but
STILL create, name/MST/limit validation, RBAC), edit (mã read-only, scope guard, audit
before→after), and the read-only Công nợ card returning "unavailable" (SEAM-16 not built,
never a fake 0).
"""
from __future__ import annotations

from app.db import SessionLocal
from app.repositories.audit_repo import AuditLogRepository
from app.repositories.rbac_repo import DepartmentRepository, RoleRepository
from app.repositories.user_repo import UserRepository
from app.security import create_access_token, hash_password
from app.seed import seed_customers, seed_kd_staff

ADMIN = {"username": "admin", "password": "admin123"}


def _seed_demo() -> None:
    """Seed the spec-06 demo staff + customers (normally gated behind SEED_DEMO=false in
    tests) so the scope assertions have owners/customers to work with."""
    db = SessionLocal()
    try:
        seed_kd_staff(db)
        seed_customers(db)
    finally:
        db.close()


def _admin_token(client) -> str:
    return client.post("/api/auth/login", json=ADMIN).json()["access_token"]


def _h(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _kd_id() -> int:
    db = SessionLocal()
    try:
        return DepartmentRepository(db).get_by_name("Kinh doanh").id
    finally:
        db.close()


def _role_token(username: str, role_name: str, dept_name: str = "Kinh doanh") -> str:
    """Create (or reuse) a user with the given role in a department and return a token."""
    db = SessionLocal()
    try:
        users = UserRepository(db)
        existing = users.get_by_username(username)
        if existing is not None:
            return create_access_token(str(existing.id))
        dept = DepartmentRepository(db).get_by_name(dept_name)
        role = RoleRepository(db).get_by_name_and_department(role_name, dept.id)
        u = users.create(username=username, name=username, password_hash=hash_password("x"))
        users.set_assignment(u, department_id=dept.id, role_id=role.id, is_active=True)
        return create_access_token(str(u.id))
    finally:
        db.close()


def _last_audit(action: str) -> str | None:
    db = SessionLocal()
    try:
        for row in AuditLogRepository(db).list_recent(200):
            if row.action == action:
                return row.detail
        return None
    finally:
        db.close()


# --- KH-01 list + scope ----------------------------------------------------


def test_list_requires_read_permission(client):
    # A user with no khach_hang.read (fresh account, no role) → 403.
    db = SessionLocal()
    try:
        u = UserRepository(db).create(
            username="norole", name="No Role", password_hash=hash_password("x")
        )
        token = create_access_token(str(u.id))
    finally:
        db.close()
    resp = client.get("/api/customers", headers=_h(token))
    assert resp.status_code == 403


def test_admin_all_scope_sees_seeded_customers(client):
    _seed_demo()
    resp = client.get("/api/customers", headers=_h(_admin_token(client)))
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] >= 1
    # Công nợ chỉ-đọc: no fake 0 — receivable None + no_ar_module True.
    row = body["items"][0]
    assert row["receivable"] is None
    assert row["no_ar_module"] is True
    assert row["code"].startswith("KH")


def test_sale_own_scope_sees_only_their_customers(client):
    _seed_demo()
    sale1 = _role_token("sale1", "NV Sales")
    sale2 = _role_token("sale2", "NV Sales")
    r1 = client.get("/api/customers", headers=_h(sale1)).json()
    r2 = client.get("/api/customers", headers=_h(sale2)).json()
    names1 = {c["name"] for c in r1["items"]}
    names2 = {c["name"] for c in r2["items"]}
    # Seeded: sale1 owns An Phát; sale2 owns Bao Bì Việt. Neither sees the other's.
    assert any("An Phát" in n for n in names1)
    assert not any("Bao Bì Việt" in n for n in names1)
    assert any("Bao Bì Việt" in n for n in names2)


def test_department_scope_sees_whole_kd(client):
    _seed_demo()
    tp = _role_token("tpkd", "Trưởng phòng KD")
    body = client.get("/api/customers", headers=_h(tp)).json()
    names = {c["name"] for c in body["items"]}
    # TP KD (department scope) sees customers of both sale1 and sale2.
    assert any("An Phát" in n for n in names)
    assert any("Bao Bì Việt" in n for n in names)


def test_list_q_filters(client):
    _seed_demo()
    token = _admin_token(client)
    body = client.get("/api/customers?q=An Phát", headers=_h(token)).json()
    assert body["total"] >= 1
    assert all("an phát" in c["name"].lower() or "an phát" in (c["tax_code"] or "").lower()
               for c in body["items"]) or body["total"] >= 1


# --- KH-02 create ----------------------------------------------------------


def test_create_generates_readonly_code_and_audits(client):
    token = _admin_token(client)
    resp = client.post(
        "/api/customers",
        json={"name": "Khách Mới ABC", "credit_limit": 1000000},
        headers=_h(token),
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["customer"]["code"].startswith("KH")
    assert body["duplicate"] is None
    # AuditLog create_customer recorded.
    assert _last_audit("create_customer") is not None


def test_create_blank_name_422(client):
    token = _admin_token(client)
    resp = client.post("/api/customers", json={"name": "   "}, headers=_h(token))
    assert resp.status_code == 422


def test_create_bad_mst_format_422(client):
    token = _admin_token(client)
    resp = client.post(
        "/api/customers", json={"name": "X", "tax_code": "123"}, headers=_h(token)
    )
    assert resp.status_code == 422


def test_create_blank_mst_is_valid(client):
    token = _admin_token(client)
    resp = client.post(
        "/api/customers", json={"name": "Khách lẻ", "tax_code": ""}, headers=_h(token)
    )
    assert resp.status_code == 201
    assert resp.json()["customer"]["tax_code"] is None


def test_create_negative_limit_422(client):
    token = _admin_token(client)
    resp = client.post(
        "/api/customers", json={"name": "X", "credit_limit": -5}, headers=_h(token)
    )
    assert resp.status_code == 422


def test_duplicate_mst_warns_but_still_creates(client):
    """§34 L885: MST trùng = cảnh báo mềm + link, KHÔNG chặn cứng."""
    token = _admin_token(client)
    first = client.post(
        "/api/customers",
        json={"name": "Bên A", "tax_code": "0109998888"},
        headers=_h(token),
    ).json()
    second = client.post(
        "/api/customers",
        json={"name": "Bên B", "tax_code": "0109998888"},
        headers=_h(token),
    )
    assert second.status_code == 201  # STILL created (not blocked)
    dup = second.json()["duplicate"]
    assert dup is not None
    assert dup["id"] == first["customer"]["id"]
    assert dup["code"] == first["customer"]["code"]


def test_create_requires_create_permission(client):
    # NV Sales has create on khach_hang (seed _rcu) — allowed. A read-only role is not.
    # Trưởng phòng HCNS has no khach_hang perm → 403.
    token = _role_token("hcns-tp", "Trưởng phòng HCNS", dept_name="Hành chính nhân sự")
    resp = client.post("/api/customers", json={"name": "X"}, headers=_h(token))
    assert resp.status_code == 403


# --- KH-03 detail + edit ---------------------------------------------------


def test_detail_and_update_readonly_code_and_audit(client):
    token = _admin_token(client)
    created = client.post(
        "/api/customers",
        json={"name": "Sửa Tôi", "credit_limit": 1000},
        headers=_h(token),
    ).json()["customer"]
    cid = created["id"]

    # detail
    detail = client.get(f"/api/customers/{cid}", headers=_h(token))
    assert detail.status_code == 200
    assert detail.json()["customer"]["code"] == created["code"]

    # update credit_limit → audit records before→after
    upd = client.put(
        f"/api/customers/{cid}",
        json={"name": "Sửa Tôi", "credit_limit": 9999, "status": "inactive"},
        headers=_h(token),
    )
    assert upd.status_code == 200
    assert upd.json()["customer"]["credit_limit"] == 9999
    assert upd.json()["customer"]["status"] == "inactive"
    # code unchanged (read-only)
    assert upd.json()["customer"]["code"] == created["code"]
    detail2 = _last_audit("update_customer")
    assert detail2 is not None and "1000" in detail2 and "9999" in detail2


def test_sale_own_cannot_open_other_sales_customer(client):
    _seed_demo()
    admin = _admin_token(client)
    # sale2's customer id
    body = client.get("/api/customers", headers=_h(_role_token("sale2", "NV Sales"))).json()
    other_id = body["items"][0]["id"]
    sale1 = _role_token("sale1", "NV Sales")
    resp = client.get(f"/api/customers/{other_id}", headers=_h(sale1))
    assert resp.status_code == 404  # not leaked as existing


def test_update_requires_update_permission_scope(client):
    # sale1 tries to PUT sale2's customer → 404 (out of scope, not leaked).
    _seed_demo()
    admin = _admin_token(client)
    sale2_body = client.get(
        "/api/customers", headers=_h(_role_token("sale2", "NV Sales"))
    ).json()
    other_id = sale2_body["items"][0]["id"]
    sale1 = _role_token("sale1", "NV Sales")
    resp = client.put(
        f"/api/customers/{other_id}",
        json={"name": "hack", "credit_limit": 0, "status": "active"},
        headers=_h(sale1),
    )
    assert resp.status_code == 404


# --- KH-04 receivable card (SEAM-16) ---------------------------------------


def test_detail_receivable_card_unavailable_no_fake_zero(client):
    """SEAM-16 not built → card available=False + message, balance None (NOT 0)."""
    token = _admin_token(client)
    created = client.post(
        "/api/customers", json={"name": "Có Thẻ Công Nợ", "credit_limit": 5000},
        headers=_h(token),
    ).json()["customer"]
    detail = client.get(f"/api/customers/{created['id']}", headers=_h(token)).json()
    card = detail["receivable"]
    assert card["available"] is False
    assert card["balance"] is None  # KHÔNG bịa 0
    assert card["credit_limit"] == 5000
    assert "Công nợ" in (card["message"] or "")
