"""feat-047 — Đơn hàng bán API (spec-10 F1/F2).

Covers: enums; approved-quotation picker (only approved+còn hạn); list ?page&size&sort&q +
scope; create from an approved quotation → pins quotation_id+version+effective_from + order-line
snapshot (no live FK); order_type/order_kind; đơn bổ sung bắt buộc parent (422); ẩn field vật lý
in every response shape; gate ③→④ deposit TREO (can_confirm=false, no fake cọc); chốt blocked
while cọc TREO; cancel captures cancelled_at_state; RBAC 403/401.
"""
from __future__ import annotations

from datetime import date, timedelta

from app.db import SessionLocal
from app.models.quotation import STATUS_APPROVED
from app.repositories.quotation_repo import QuotationRepository
from app.repositories.rbac_repo import DepartmentRepository, RoleRepository
from app.repositories.user_repo import UserRepository
from app.security import create_access_token, hash_password

ADMIN = {"username": "admin", "password": "admin123"}
TOMORROW = (date.today() + timedelta(days=30)).isoformat()
YESTERDAY = (date.today() - timedelta(days=1)).isoformat()

# The physical layer must NEVER appear in any Sale response (§29 P0, §43 #1).
PHYSICAL_KEYS = (
    "kho_giay", "so_mau", "so_kem", "imposition", "printform",
    "print_form", "so_to", "so_con", "bu_hao", "plate", "colors",
)


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


def _seed_approved_quotation(*, sale_user_id: int, total=1_000_000, valid_until=None) -> int:
    """Insert an approved quotation directly (Báo giá is a peer module; SEAM-04 reads it live)."""
    db = SessionLocal()
    try:
        q = QuotationRepository(db).create(
            customer_id=None, costing_id=None, cost_von_total=total, margin=0, discount=0,
            total=total, valid_until=valid_until, sale_user_id=sale_user_id,
            status=STATUS_APPROVED,
        )
        return q.id
    finally:
        db.close()


def _admin_id() -> int:
    db = SessionLocal()
    try:
        return UserRepository(db).get_by_username("admin").id
    finally:
        db.close()


def _create_order(client, token, quotation_id, **over):
    body = {
        "quotation_id": quotation_id, "order_type": "theo_yc", "order_kind": "moi",
        "parent_order_id": None, "has_customer_paper": False, "vat_pct_estimate": 8,
    }
    body.update(over)
    return client.post("/api/orders", json=body, headers=_h(token))


# --- enums + approved picker (F1) ---------------------------------------------

def test_enums(client):
    token = _admin_token(client)
    r = client.get("/api/orders/enums", headers=_h(token))
    assert r.status_code == 200
    body = r.json()
    assert {o["value"] for o in body["order_types"]} == {"noi_bo", "theo_yc"}
    assert {o["value"] for o in body["order_kinds"]} == {"moi", "bo_sung"}
    assert "ordered" in {o["value"] for o in body["statuses"]}


def test_approved_picker_only_approved_and_in_date(client):
    token = _admin_token(client)
    admin_id = _admin_id()
    good = _seed_approved_quotation(sale_user_id=admin_id, valid_until=date.today() + timedelta(days=10))
    # An approved-but-expired quotation must NOT be choosable.
    _seed_expired = SessionLocal()
    try:
        QuotationRepository(_seed_expired).create(
            customer_id=None, costing_id=None, cost_von_total=1, margin=0, discount=0, total=1,
            valid_until=date.today() - timedelta(days=1), sale_user_id=admin_id,
            status=STATUS_APPROVED,
        )
    finally:
        _seed_expired.close()

    r = client.get("/api/orders/approved-quotations", headers=_h(token))
    assert r.status_code == 200
    ids = {row["id"] for row in r.json()["items"]}
    assert good in ids
    # The expired one is filtered out.
    assert len(ids) == 1


# --- list (F1) ----------------------------------------------------------------

def test_list_empty_then_created(client):
    token = _admin_token(client)
    r = client.get("/api/orders", headers=_h(token))
    assert r.status_code == 200 and r.json()["total"] == 0

    qid = _seed_approved_quotation(sale_user_id=_admin_id(), total=1_200_000)
    created = _create_order(client, token, qid)
    assert created.status_code == 201, created.text

    r = client.get("/api/orders?sort=order_no&page=1&size=10", headers=_h(token))
    body = r.json()
    assert body["total"] == 1
    row = body["items"][0]
    assert row["order_no"].startswith("DH")
    assert row["order_type"] == "theo_yc"
    assert row["total_estimate"] == 1_200_000
    # ③→④ gate not met (cọc TREO) → honest false, not a fake pass.
    assert row["gate_ordered_ok"] is False


# --- create pins quotation + snapshot (F1) ------------------------------------

def test_create_pins_and_snapshots(client):
    token = _admin_token(client)
    qid = _seed_approved_quotation(sale_user_id=_admin_id(), total=1_500_000)
    r = _create_order(client, token, qid)
    assert r.status_code == 201
    d = r.json()
    assert d["quotation_id"] == qid
    assert d["quotation_version"] == 1
    assert len(d["lines"]) == 1
    assert d["lines"][0]["unit_price_snapshot"] == 1_500_000
    assert d["lines"][0]["line_total"] == 1_500_000


def test_snapshot_not_live_fk(client):
    token = _admin_token(client)
    qid = _seed_approved_quotation(sale_user_id=_admin_id(), total=1_000_000)
    order = _create_order(client, token, qid).json()
    # Mutate the source quotation total.
    db = SessionLocal()
    try:
        qrepo = QuotationRepository(db)
        qrepo.update(qrepo.get_by_id(qid), total=9_999_999)
    finally:
        db.close()
    d = client.get(f"/api/orders/{order['id']}", headers=_h(token)).json()
    assert d["lines"][0]["unit_price_snapshot"] == 1_000_000  # unchanged


# --- reject non-approved / expired (F1 edge) ----------------------------------

def test_create_from_draft_quotation_blocked(client):
    token = _admin_token(client)
    db = SessionLocal()
    try:
        q = QuotationRepository(db).create(
            customer_id=None, costing_id=None, cost_von_total=1, margin=0, discount=0, total=1,
            valid_until=None, sale_user_id=_admin_id(), status="draft",
        )
        qid = q.id
    finally:
        db.close()
    r = _create_order(client, token, qid)
    assert r.status_code == 422
    assert "duyệt" in r.json()["detail"]


# --- loại đơn & đơn bổ sung (F2) ----------------------------------------------

def test_bo_sung_requires_parent(client):
    token = _admin_token(client)
    qid = _seed_approved_quotation(sale_user_id=_admin_id())
    r = _create_order(client, token, qid, order_kind="bo_sung", parent_order_id=None)
    assert r.status_code == 422
    assert "bổ sung" in r.json()["detail"]


def test_bo_sung_with_parent_ok(client):
    token = _admin_token(client)
    q1 = _seed_approved_quotation(sale_user_id=_admin_id())
    parent = _create_order(client, token, q1).json()
    q2 = _seed_approved_quotation(sale_user_id=_admin_id())
    r = _create_order(client, token, q2, order_kind="bo_sung", parent_order_id=parent["id"])
    assert r.status_code == 201
    assert r.json()["order_kind"] == "bo_sung"
    assert r.json()["parent_order_id"] == parent["id"]


# --- ẩn field vật lý (§29 P0) -------------------------------------------------

def test_no_physical_fields_in_any_view(client):
    token = _admin_token(client)
    qid = _seed_approved_quotation(sale_user_id=_admin_id())
    order = _create_order(client, token, qid).json()

    # list + detail response bodies (raw text) must not carry any physical vocabulary as a key.
    list_txt = client.get("/api/orders", headers=_h(token)).text.lower()
    detail_txt = client.get(f"/api/orders/{order['id']}", headers=_h(token)).text.lower()
    for key in PHYSICAL_KEYS:
        assert key not in list_txt, f"physical key leaked in list: {key}"
        assert key not in detail_txt, f"physical key leaked in detail: {key}"


# --- gate ③→④ + chốt blocked while cọc TREO (F3) ------------------------------

def test_gate_deposit_unavailable(client):
    token = _admin_token(client)
    qid = _seed_approved_quotation(sale_user_id=_admin_id(), total=1_000_000)
    order = _create_order(client, token, qid).json()
    gate = order["gate"]
    assert gate["quotation_approved"] is True
    assert gate["deposit_available"] is False
    assert gate["deposit_paid"] is None
    assert gate["can_confirm"] is False
    assert gate["deposit_required"] == 300_000


def test_confirm_blocked_while_deposit_treo(client):
    token = _admin_token(client)
    qid = _seed_approved_quotation(sale_user_id=_admin_id(), total=1_000_000)
    order = _create_order(client, token, qid).json()
    r = client.post(
        f"/api/orders/{order['id']}/transition", json={"to_status": "ordered"}, headers=_h(token)
    )
    # Chốt cần cọc, ghi cọc TREO (SEAM-04 Payment) → 409, nêu rõ chờ phân hệ.
    assert r.status_code == 409


# --- đổi/hủy (F8) -------------------------------------------------------------

def test_cancel_captures_state(client):
    token = _admin_token(client)
    qid = _seed_approved_quotation(sale_user_id=_admin_id())
    order = _create_order(client, token, qid).json()
    # cancel without reason → 422
    r = client.post(
        f"/api/orders/{order['id']}/transition", json={"to_status": "cancelled"}, headers=_h(token)
    )
    assert r.status_code == 422
    r = client.post(
        f"/api/orders/{order['id']}/transition",
        json={"to_status": "cancelled", "cancel_reason": "khách hủy"}, headers=_h(token),
    )
    assert r.status_code == 200
    assert r.json()["status"] == "cancelled"
    assert r.json()["cancelled_at_state"] == "draft"


def test_change_order_transition(client):
    token = _admin_token(client)
    qid = _seed_approved_quotation(sale_user_id=_admin_id())
    order = _create_order(client, token, qid).json()
    r = client.post(
        f"/api/orders/{order['id']}/transition", json={"to_status": "change_order"},
        headers=_h(token),
    )
    assert r.status_code == 200
    assert r.json()["status"] == "change_order"
    # change_order does NOT set parent_order_id (đổi giữ lịch sử qua Quotation-version).
    assert r.json()["parent_order_id"] is None


def test_illegal_transition_409(client):
    token = _admin_token(client)
    qid = _seed_approved_quotation(sale_user_id=_admin_id())
    order = _create_order(client, token, qid).json()
    r = client.post(
        f"/api/orders/{order['id']}/transition", json={"to_status": "cancelled",
        "cancel_reason": "x"}, headers=_h(token),
    )
    assert r.status_code == 200
    # cancelled is terminal → any further transition illegal.
    r = client.post(
        f"/api/orders/{order['id']}/transition", json={"to_status": "ordered"}, headers=_h(token)
    )
    assert r.status_code == 409


# --- RBAC ---------------------------------------------------------------------

def test_requires_auth(client):
    r = client.get("/api/orders")
    assert r.status_code == 401
