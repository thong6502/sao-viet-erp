"""feat-038/039 — Tính giá (Costing) API (spec-08), LÀM-NGAY slice.

Covers: data model + create in one transaction (header + phương án giấy + công đoạn);
mã tự sinh CG### duy nhất; qty_final ≤ 0 chặn; pieces_per_sheet ≤ 0 chặn; ≥1 phương án giấy;
gợi ý số con/khổ hình học (grain_locked bỏ nhánh xoay; pieces=0 không chia 0); list
?page&size&sort&q&filters + empty-state; SEAM-07 paper picker + SEAM-11 product read
"chưa sẵn sàng"; AuditEntry create/update/delete; RBAC 403.

Cost numbers (giá vốn, số tờ, đơn giá) are DEFERRED behind SEAM-07..12 — not asserted here.
"""
from __future__ import annotations

from app.db import SessionLocal
from app.repositories.audit_repo import AuditLogRepository
from app.repositories.rbac_repo import DepartmentRepository, RoleRepository
from app.repositories.user_repo import UserRepository
from app.security import create_access_token, hash_password

ADMIN = {"username": "admin", "password": "admin123"}


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


def _last_audit(action: str) -> str | None:
    db = SessionLocal()
    try:
        for row in AuditLogRepository(db).list_recent(200):
            if row.action == action:
                return row.detail
        return None
    finally:
        db.close()


def _payload(qty=1000, papers=None, ops=None, product_id=None, status=None):
    body = {
        "qty_final": qty,
        "paper_options": papers
        if papers is not None
        else [
            {
                "sheet_w": 65.0,
                "sheet_h": 86.0,
                "pieces_per_sheet": 8,
                "grain_locked": False,
            }
        ],
        "operations": ops if ops is not None else [],
    }
    if product_id is not None:
        body["product_id"] = product_id
    if status is not None:
        body["status"] = status
    return body


# --- RBAC ------------------------------------------------------------------


def test_list_requires_read_permission(client):
    db = SessionLocal()
    try:
        u = UserRepository(db).create(
            username="norole-cg", name="No Role", password_hash=hash_password("x")
        )
        token = create_access_token(str(u.id))
    finally:
        db.close()
    assert client.get("/api/costings", headers=_h(token)).status_code == 403


def test_create_requires_create_permission(client):
    # NV Sales has no tinh_gia_thanh permission → 403.
    token = _role_token("sales-cg", "NV Sales")
    resp = client.post("/api/costings", json=_payload(), headers=_h(token))
    assert resp.status_code == 403


# --- F1 list + empty-state -------------------------------------------------


def test_list_empty_then_filters(client):
    token = _admin_token(client)
    empty = client.get("/api/costings", headers=_h(token)).json()
    assert empty["total"] == 0 and empty["items"] == []

    client.post("/api/costings", json=_payload(qty=1000), headers=_h(token))
    client.post(
        "/api/costings", json=_payload(qty=500, status="ready"), headers=_h(token)
    )

    all_ = client.get("/api/costings", headers=_h(token)).json()
    assert all_["total"] == 2
    # paper_option_count reflected.
    assert all(r["paper_option_count"] == 1 for r in all_["items"])
    # total_cost is null at P0 (SEAM-07..12 not built) — never a fabricated number.
    assert all(r["total_cost"] is None for r in all_["items"])

    # Filter by status.
    ready = client.get("/api/costings?status=ready", headers=_h(token)).json()
    assert ready["total"] == 1
    assert ready["items"][0]["status"] == "ready"


def test_list_pagination_and_sort(client):
    token = _admin_token(client)
    for _ in range(3):
        client.post("/api/costings", json=_payload(), headers=_h(token))
    page1 = client.get("/api/costings?page=1&size=2&sort=code", headers=_h(token)).json()
    assert page1["total"] == 3 and len(page1["items"]) == 2
    page2 = client.get("/api/costings?page=2&size=2&sort=code", headers=_h(token)).json()
    assert len(page2["items"]) == 1


# --- F2 create -------------------------------------------------------------


def test_create_generates_unique_cg_code_and_persists_children(client):
    token = _admin_token(client)
    r1 = client.post(
        "/api/costings",
        json=_payload(
            papers=[
                {"sheet_w": 65, "sheet_h": 86, "pieces_per_sheet": 8, "grain_locked": True},
                {"sheet_w": 79, "sheet_h": 109, "pieces_per_sheet": 16, "grain_locked": False},
            ],
            ops=[
                {"name": "Cán màng", "execution_mode": "internal", "sequence": 0},
                {"name": "Bế", "execution_mode": "outsourced", "sequence": 1},
            ],
        ),
        headers=_h(token),
    )
    assert r1.status_code == 201, r1.text
    d1 = r1.json()
    assert d1["code"] == "CG001"
    assert len(d1["paper_options"]) == 2
    assert len(d1["operations"]) == 2
    assert d1["operations"][0]["execution_mode"] == "internal"
    assert d1["operations"][1]["execution_mode"] == "outsourced"

    r2 = client.post("/api/costings", json=_payload(), headers=_h(token))
    assert r2.json()["code"] == "CG002"  # unique + sequential

    assert (_last_audit("create_costing") or "").startswith("CG002")


def test_qty_final_must_be_positive(client):
    token = _admin_token(client)
    assert (
        client.post("/api/costings", json=_payload(qty=0), headers=_h(token)).status_code
        == 422
    )
    assert (
        client.post("/api/costings", json=_payload(qty=-5), headers=_h(token)).status_code
        == 422
    )


def test_needs_at_least_one_paper_option(client):
    token = _admin_token(client)
    resp = client.post("/api/costings", json=_payload(papers=[]), headers=_h(token))
    assert resp.status_code == 422
    assert "phương án giấy" in resp.json()["detail"].lower()


def test_pieces_per_sheet_must_be_positive(client):
    token = _admin_token(client)
    resp = client.post(
        "/api/costings",
        json=_payload(
            papers=[{"sheet_w": 65, "sheet_h": 86, "pieces_per_sheet": 0}]
        ),
        headers=_h(token),
    )
    assert resp.status_code == 422
    assert "số con/khổ" in resp.json()["detail"].lower()


def test_bad_execution_mode_rejected(client):
    token = _admin_token(client)
    resp = client.post(
        "/api/costings",
        json=_payload(ops=[{"name": "X", "execution_mode": "bogus"}]),
        headers=_h(token),
    )
    assert resp.status_code == 422


# --- F2 số con/khổ suggestion (pure geometry, no seam) ---------------------


def test_suggest_pieces_geometry(client):
    token = _admin_token(client)
    # 65x86 sheet, 10x10 piece → 6 cols x 8 rows = 48 straight; rotation same → 48.
    resp = client.post(
        "/api/costings/suggest-pieces",
        json={"sheet_w": 65, "sheet_h": 86, "piece_w": 10, "piece_h": 10},
        headers=_h(token),
    )
    assert resp.status_code == 200
    assert resp.json()["pieces"] == 48


def test_suggest_pieces_rotation_helps_unless_grain_locked(client):
    token = _admin_token(client)
    # sheet 30x20, piece 20x10: straight 1x2=2; rotated (10x20) 3x1=3 → best 3.
    free = client.post(
        "/api/costings/suggest-pieces",
        json={"sheet_w": 30, "sheet_h": 20, "piece_w": 20, "piece_h": 10, "grain_locked": False},
        headers=_h(token),
    ).json()
    assert free["pieces"] == 3
    # grain_locked → drop the xoay branch → only straight 2.
    locked = client.post(
        "/api/costings/suggest-pieces",
        json={"sheet_w": 30, "sheet_h": 20, "piece_w": 20, "piece_h": 10, "grain_locked": True},
        headers=_h(token),
    ).json()
    assert locked["pieces"] == 2


def test_suggest_pieces_zero_when_paper_too_small(client):
    token = _admin_token(client)
    resp = client.post(
        "/api/costings/suggest-pieces",
        json={"sheet_w": 5, "sheet_h": 5, "piece_w": 10, "piece_h": 10},
        headers=_h(token),
    ).json()
    assert resp["pieces"] == 0
    assert resp["message"]  # explicit warning, never a divide-by-zero


# --- Seam pickers ("chưa sẵn sàng", never fabricated) ----------------------


def test_paper_cost_picker_unavailable_seam_07(client):
    token = _admin_token(client)
    resp = client.get("/api/costings/papers", headers=_h(token)).json()
    assert resp["available"] is False
    assert "chưa sẵn sàng" in (resp["message"] or "").lower()
    assert resp["items"] == []


def test_product_read_unavailable_seam_11(client):
    token = _admin_token(client)
    resp = client.get("/api/costings/products/1", headers=_h(token)).json()
    assert resp["available"] is False
    assert "chưa sẵn sàng" in (resp["message"] or "").lower()


# --- Detail / update / delete ----------------------------------------------


def test_get_update_delete_lifecycle(client):
    token = _admin_token(client)
    created = client.post(
        "/api/costings", json=_payload(qty=1000), headers=_h(token)
    ).json()
    cid = created["id"]

    got = client.get(f"/api/costings/{cid}", headers=_h(token))
    assert got.status_code == 200 and got.json()["code"] == created["code"]

    upd = client.put(
        f"/api/costings/{cid}",
        json=_payload(qty=2000, status="ready"),
        headers=_h(token),
    )
    assert upd.status_code == 200
    assert upd.json()["qty_final"] == 2000 and upd.json()["status"] == "ready"
    assert upd.json()["code"] == created["code"]  # mã read-only
    assert (_last_audit("update_costing") or "").startswith(created["code"])

    dele = client.delete(f"/api/costings/{cid}", headers=_h(token))
    assert dele.status_code == 204
    assert client.get(f"/api/costings/{cid}", headers=_h(token)).status_code == 404
    assert _last_audit("delete_costing") == created["code"]


def test_get_missing_is_404(client):
    token = _admin_token(client)
    assert client.get("/api/costings/9999", headers=_h(token)).status_code == 404


def test_enums(client):
    token = _admin_token(client)
    enums = client.get("/api/costings/enums", headers=_h(token)).json()
    assert {o["value"] for o in enums["statuses"]} == {"draft", "ready"}
    assert {o["value"] for o in enums["execution_modes"]} == {"internal", "outsourced"}
