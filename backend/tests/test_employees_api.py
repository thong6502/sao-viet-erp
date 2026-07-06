"""Hồ sơ nhân sự (module `nhan_su`) — lát #1.

CRUD + KPIs, soft duplicate CCCD/BHXH, stage transitions (confirm/resign/reinstate/
transfer/promote) with Quá trình công tác events, account link/create/unlink, attachments,
and the RBAC gate. Admin (Giám đốc) holds full nhan_su by seed; a NV Sales user does not.
"""
from __future__ import annotations

from app.db import SessionLocal
from app.repositories.rbac_repo import DepartmentRepository, RoleRepository
from app.repositories.user_repo import UserRepository
from app.security import create_access_token, hash_password

ADMIN = {"username": "admin", "password": "admin123"}


def _admin_token(client) -> str:
    return client.post("/api/auth/login", json=ADMIN).json()["access_token"]


def _h(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _dept_id(name: str) -> int:
    db = SessionLocal()
    try:
        return DepartmentRepository(db).get_by_name(name).id
    finally:
        db.close()


def _sales_token() -> str:
    db = SessionLocal()
    try:
        users = UserRepository(db)
        existing = users.get_by_username("sales-emp")
        if existing is not None:
            return create_access_token(str(existing.id))
        kd = DepartmentRepository(db).get_by_name("Kinh doanh")
        role = RoleRepository(db).get_by_name_and_department("NV Sales", kd.id)
        u = users.create(username="sales-emp", name="S", password_hash=hash_password("x"))
        users.set_assignment(u, department_id=kd.id, role_id=role.id, is_active=True)
        return create_access_token(str(u.id))
    finally:
        db.close()


def _create(client, token, **over):
    body = {
        "full_name": over.pop("full_name", "Trần Văn A"),
        "department_id": over.pop("department_id", _dept_id("Hành chính nhân sự")),
        "hire_date": over.pop("hire_date", "2024-01-15"),
    }
    body.update(over)
    return client.post("/api/employees", json=body, headers=_h(token))


# --- create + list ----------------------------------------------------------


def test_create_assigns_code_probation_and_hired_event(client):
    token = _admin_token(client)
    resp = _create(client, token, full_name="Nguyễn Thị B")
    assert resp.status_code == 201
    emp = resp.json()["employee"]
    assert emp["code"].startswith("NV")
    assert emp["status"] == "probation"  # mặc định Thử việc
    assert emp["department_name"] == "Hành chính nhân sự"

    events = client.get(f"/api/employees/{emp['id']}/events", headers=_h(token)).json()["items"]
    assert any(e["event_type"] == "hired" for e in events)


def test_list_has_kpis_and_status_filter(client):
    token = _admin_token(client)
    _create(client, token, full_name="A")
    active = _create(client, token, full_name="B").json()["employee"]
    client.post(
        f"/api/employees/{active['id']}/transitions",
        json={"kind": "confirm", "effective_date": "2024-03-01"},
        headers=_h(token),
    )

    data = client.get("/api/employees", headers=_h(token)).json()
    assert data["kpis"]["total"] == 2
    assert data["kpis"]["probation"] == 1
    assert data["kpis"]["active"] == 1

    only_active = client.get("/api/employees?status=active", headers=_h(token)).json()
    assert only_active["total"] == 1
    assert only_active["items"][0]["status"] == "active"


# --- soft duplicate ---------------------------------------------------------


def test_duplicate_cccd_is_soft_warning(client):
    token = _admin_token(client)
    first = _create(client, token, full_name="X", national_id="079123456789").json()["employee"]
    resp = _create(client, token, full_name="Y", national_id="079123456789")
    assert resp.status_code == 201  # KHÔNG chặn
    dup = resp.json()["duplicate_national_id"]
    assert dup is not None and dup["id"] == first["id"]


# --- edit -------------------------------------------------------------------


def test_update_edits_profile(client):
    token = _admin_token(client)
    emp = _create(client, token).json()["employee"]
    resp = client.put(
        f"/api/employees/{emp['id']}",
        json={"full_name": "Tên Mới", "phone": "0900000000", "dependents_count": 2},
        headers=_h(token),
    )
    assert resp.status_code == 200
    out = resp.json()["employee"]
    assert out["full_name"] == "Tên Mới"
    assert out["phone"] == "0900000000"
    assert out["dependents_count"] == 2


# --- transitions ------------------------------------------------------------


def test_confirm_then_illegal_transition(client):
    token = _admin_token(client)
    emp = _create(client, token).json()["employee"]
    ok = client.post(
        f"/api/employees/{emp['id']}/transitions",
        json={"kind": "confirm", "effective_date": "2024-03-01"},
        headers=_h(token),
    )
    assert ok.status_code == 200 and ok.json()["status"] == "active"
    # confirm again from `active` is illegal
    bad = client.post(
        f"/api/employees/{emp['id']}/transitions",
        json={"kind": "confirm"},
        headers=_h(token),
    )
    assert bad.status_code == 400


def test_resign_requires_reason_then_locks_edit_until_reinstate(client):
    token = _admin_token(client)
    emp = _create(client, token).json()["employee"]
    eid = emp["id"]

    no_reason = client.post(
        f"/api/employees/{eid}/transitions", json={"kind": "resign"}, headers=_h(token)
    )
    assert no_reason.status_code == 400

    resigned = client.post(
        f"/api/employees/{eid}/transitions",
        json={"kind": "resign", "effective_date": "2024-06-30", "resign_reason": "Tự xin nghỉ"},
        headers=_h(token),
    )
    assert resigned.status_code == 200 and resigned.json()["status"] == "resigned"

    # Resigned hồ sơ is read-only.
    locked = client.put(f"/api/employees/{eid}", json={"full_name": "Z"}, headers=_h(token))
    assert locked.status_code == 400

    # Reinstate reopens it.
    back = client.post(
        f"/api/employees/{eid}/transitions", json={"kind": "reinstate"}, headers=_h(token)
    )
    assert back.status_code == 200 and back.json()["status"] == "active"
    assert client.put(f"/api/employees/{eid}", json={"full_name": "Z"}, headers=_h(token)).status_code == 200


def test_transfer_and_promote_record_events(client):
    token = _admin_token(client)
    hcns = _dept_id("Hành chính nhân sự")
    kd = _dept_id("Kinh doanh")
    emp = _create(client, token, department_id=hcns).json()["employee"]
    eid = emp["id"]

    # transfer to another department
    t = client.post(
        f"/api/employees/{eid}/transitions",
        json={"kind": "transfer", "new_department_id": kd, "effective_date": "2024-04-06"},
        headers=_h(token),
    )
    assert t.status_code == 200 and t.json()["department_id"] == kd
    # transfer to same dept is rejected
    same = client.post(
        f"/api/employees/{eid}/transitions",
        json={"kind": "transfer", "new_department_id": kd},
        headers=_h(token),
    )
    assert same.status_code == 400

    # promote (bậc thợ)
    p = client.post(
        f"/api/employees/{eid}/transitions",
        json={"kind": "promote", "new_job_grade": "3/7"},
        headers=_h(token),
    )
    assert p.status_code == 200 and p.json()["job_grade"] == "3/7"

    kinds = {e["event_type"] for e in client.get(f"/api/employees/{eid}/events", headers=_h(token)).json()["items"]}
    assert {"hired", "transferred", "promoted"} <= kinds


# --- account link -----------------------------------------------------------


def test_create_account_in_wizard_then_unlink_and_relink(client):
    token = _admin_token(client)
    resp = _create(
        client, token, full_name="Có Tài Khoản",
        account={"username": "nv_login", "password": "secret1"},
    )
    assert resp.status_code == 201
    payload = resp.json()
    assert payload["account_username"] == "nv_login"
    eid = payload["employee"]["id"]

    # the new account can authenticate
    login = client.post("/api/auth/login", json={"username": "nv_login", "password": "secret1"})
    assert login.status_code == 200

    # unlink, then link it back via the account endpoint
    unlinked = client.delete(f"/api/employees/{eid}/account", headers=_h(token)).json()
    assert unlinked["user_id"] is None

    uid = login.json()  # not the user id; fetch via meta
    meta = client.get("/api/employees/meta", headers=_h(token)).json()
    user_id = next(u["id"] for u in meta["unlinked_users"] if u["username"] == "nv_login")
    relinked = client.post(
        f"/api/employees/{eid}/account", json={"user_id": user_id}, headers=_h(token)
    ).json()
    assert relinked["account_username"] == "nv_login"


# --- attachments ------------------------------------------------------------


def test_attachment_upload_list_delete(client):
    token = _admin_token(client)
    emp = _create(client, token).json()["employee"]
    eid = emp["id"]

    up = client.post(
        f"/api/employees/{eid}/attachments",
        files={"file": ("cccd.pdf", b"%PDF-1.4 fake", "application/pdf")},
        data={"doc_kind": "cccd"},
        headers=_h(token),
    )
    assert up.status_code == 201
    att = up.json()
    assert att["doc_kind"] == "cccd" and att["file_name"] == "cccd.pdf"
    assert att["file_url"].startswith(f"/static/hr/{eid}/")

    listed = client.get(f"/api/employees/{eid}/attachments", headers=_h(token)).json()["items"]
    assert len(listed) == 1

    assert client.delete(f"/api/employees/{eid}/attachments/{att['id']}", headers=_h(token)).status_code == 204
    assert client.get(f"/api/employees/{eid}/attachments", headers=_h(token)).json()["items"] == []


# --- RBAC -------------------------------------------------------------------


def test_forbidden_without_permission(client):
    token = _sales_token()
    assert client.get("/api/employees", headers=_h(token)).status_code == 403
    assert _create(client, token).status_code == 403
