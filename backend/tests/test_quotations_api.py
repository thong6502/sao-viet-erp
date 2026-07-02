"""feat-044/045 — Báo giá (Quotation) API (spec-09 F1..F6).

Covers: list ?page&size&sort&q&status + scope; create (giá bán = giá vốn + lãi − chiết khấu)
+ validation 422; edit only when draft (409) + optimistic lock (409); SEAM-13 costing picker
"chưa sẵn sàng" (no fabricated cost); lifecycle send→approved by a manager, Sale can't approve
(403); change_order new version; PDF đối ngoại (no buildup keywords); RBAC 403.
"""
from __future__ import annotations

from datetime import date, timedelta

from app.db import SessionLocal
from app.repositories.rbac_repo import DepartmentRepository, RoleRepository
from app.repositories.user_repo import UserRepository
from app.security import create_access_token, hash_password

ADMIN = {"username": "admin", "password": "admin123"}
TOMORROW = (date.today() + timedelta(days=30)).isoformat()
YESTERDAY = (date.today() - timedelta(days=1)).isoformat()


def _admin_token(client) -> str:
    return client.post("/api/auth/login", json=ADMIN).json()["access_token"]


def _h(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _role_token(username: str, role_name: str, dept_name: str = "Kinh doanh") -> str:
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


def _create(client, token, **over) -> dict:
    body = {
        "customer_id": None, "costing_id": None, "cost_von_total": 1_000_000,
        "margin": 200_000, "discount": 50_000, "valid_until": TOMORROW,
    }
    body.update(over)
    r = client.post("/api/quotations", json=body, headers=_h(token))
    assert r.status_code == 201, r.text
    return r.json()


# --- F1 list -------------------------------------------------------------------

def test_list_empty_then_shows_created(client):
    token = _admin_token(client)
    r = client.get("/api/quotations", headers=_h(token))
    assert r.status_code == 200
    assert r.json()["total"] == 0
    q = _create(client, token)
    r = client.get("/api/quotations?sort=code&page=1&size=10", headers=_h(token))
    body = r.json()
    assert body["total"] == 1
    row = body["items"][0]
    assert row["code"].startswith("BG")
    assert row["version"] == 1
    assert row["total"] == q["total"]
    assert row["status"] == "draft"


def test_list_status_filter(client):
    token = _admin_token(client)
    _create(client, token)
    r = client.get("/api/quotations?status=approved", headers=_h(token))
    assert r.status_code == 200 and r.json()["total"] == 0


# --- F2 create + pricing -------------------------------------------------------

def test_create_computes_gia_ban(client):
    token = _admin_token(client)
    q = _create(client, token, cost_von_total=1_000_000, margin=300_000, discount=100_000)
    assert q["total"] == 1_200_000
    assert q["cost_von_total"] == 1_000_000


def test_create_validation_422(client):
    token = _admin_token(client)
    # discount > cost + margin
    r = client.post(
        "/api/quotations",
        json={"cost_von_total": 100, "margin": 0, "discount": 500, "valid_until": TOMORROW},
        headers=_h(token),
    )
    assert r.status_code == 422
    # past valid_until
    r = client.post(
        "/api/quotations",
        json={"cost_von_total": 100, "margin": 0, "discount": 0, "valid_until": YESTERDAY},
        headers=_h(token),
    )
    assert r.status_code == 422


# --- edit draft only + optimistic lock ----------------------------------------

def test_update_draft_then_lock_after_send(client):
    token = _admin_token(client)
    q = _create(client, token)
    # ok while draft
    r = client.put(
        f"/api/quotations/{q['id']}",
        json={"cost_von_total": 900_000, "margin": 100_000, "discount": 0,
              "valid_until": TOMORROW, "row_version": q["row_version"]},
        headers=_h(token),
    )
    assert r.status_code == 200 and r.json()["total"] == 1_000_000
    rv = r.json()["row_version"]
    # send → sent
    client.post(f"/api/quotations/{q['id']}/transition", json={"to_status": "sent"},
                headers=_h(token))
    # now edit is locked
    r = client.put(
        f"/api/quotations/{q['id']}",
        json={"cost_von_total": 1, "margin": 0, "discount": 0,
              "valid_until": TOMORROW, "row_version": rv + 1},
        headers=_h(token),
    )
    assert r.status_code == 409


def test_stale_row_version_409(client):
    token = _admin_token(client)
    q = _create(client, token)
    r = client.put(
        f"/api/quotations/{q['id']}",
        json={"cost_von_total": 1, "margin": 0, "discount": 0,
              "valid_until": TOMORROW, "row_version": q["row_version"] + 9},
        headers=_h(token),
    )
    assert r.status_code == 409


# --- SEAM-13 costing picker ----------------------------------------------------

def test_costing_picker_unavailable(client):
    token = _admin_token(client)
    r = client.get("/api/quotations/costings/1", headers=_h(token))
    assert r.status_code == 200
    body = r.json()
    assert body["available"] is False
    assert "chưa sẵn sàng" in body["message"]
    assert body["cost_von_total"] is None  # never a fabricated cost


# --- F3/F4/F5 lifecycle --------------------------------------------------------

def test_send_freezes_snapshot(client):
    token = _admin_token(client)
    q = _create(client, token)
    r = client.post(f"/api/quotations/{q['id']}/transition", json={"to_status": "sent"},
                    headers=_h(token))
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "sent"
    assert body["unit_price_snapshot"] is not None
    assert body["norm_snapshot"] is not None  # P0: both vế frozen


def test_illegal_transition_409(client):
    token = _admin_token(client)
    q = _create(client, token)
    r = client.post(f"/api/quotations/{q['id']}/transition", json={"to_status": "approved"},
                    headers=_h(token))
    assert r.status_code == 409  # draft → approved illegal


def test_sale_cannot_approve_manager_can(client):
    admin = _admin_token(client)
    q = _create(client, admin)
    client.post(f"/api/quotations/{q['id']}/transition", json={"to_status": "sent"},
                headers=_h(admin))
    # A Sale (scope=own) → 403 on approve.
    sale = _role_token("sale-approve", "NV Sales")
    r = client.post(f"/api/quotations/{q['id']}/transition", json={"to_status": "approved"},
                    headers=_h(sale))
    assert r.status_code in (403, 404)  # own-scope sale may not even see it → both are "no"
    # Admin (scope=all) approves.
    r = client.post(f"/api/quotations/{q['id']}/transition", json={"to_status": "approved"},
                    headers=_h(admin))
    assert r.status_code == 200 and r.json()["status"] == "approved"


def test_cancel_requires_reason(client):
    token = _admin_token(client)
    q = _create(client, token)
    r = client.post(f"/api/quotations/{q['id']}/transition", json={"to_status": "cancelled"},
                    headers=_h(token))
    assert r.status_code == 422
    r = client.post(f"/api/quotations/{q['id']}/transition",
                    json={"to_status": "cancelled", "cancel_reason": "khách đổi ý"},
                    headers=_h(token))
    assert r.status_code == 200
    assert r.json()["status"] == "cancelled"
    assert r.json()["cancelled_at_state"] == "draft"


def test_requote_new_version(client):
    token = _admin_token(client)
    q = _create(client, token)
    client.post(f"/api/quotations/{q['id']}/transition", json={"to_status": "sent"},
                headers=_h(token))
    r = client.post(f"/api/quotations/{q['id']}/requote", headers=_h(token))
    assert r.status_code == 201
    body = r.json()
    assert body["code"] == q["code"] and body["version"] == 2 and body["status"] == "draft"
    # old one superseded, still fetchable
    old = client.get(f"/api/quotations/{q['id']}", headers=_h(token)).json()
    assert old["status"] == "change_order"
    assert len(body["versions"]) == 2


# --- F6 PDF đối ngoại ----------------------------------------------------------

def test_pdf_is_pdf_and_hides_buildup(client):
    token = _admin_token(client)
    q = _create(client, token)
    r = client.get(f"/api/quotations/{q['id']}/pdf", headers=_h(token))
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/pdf"
    assert r.content[:4] == b"%PDF"
    # The buildup vocabulary must NOT appear in the document bytes.
    lowered = r.content.lower()
    for banned in (b"ke\xcc\x83m", b"imposition", b"bu hao", b"buildup", b"so to", b"so con"):
        assert banned not in lowered


# --- RBAC ----------------------------------------------------------------------

def test_requires_permission(client):
    r = client.get("/api/quotations")
    assert r.status_code == 401
