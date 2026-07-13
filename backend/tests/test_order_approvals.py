"""A2 — Đơn hàng bán: GĐ duyệt "đơn đặc thù" (order_approvals).

Bao phủ: soi 3 điều kiện (giá trị cao / biên thấp / dưới giá vốn) → chặn chốt tới khi GĐ duyệt;
GĐ duyệt "bao phủ" → mở khóa; đơn xấu đi sau duyệt → stale (trình lại); từ chối → chặn; RBAC (chỉ
GĐ duyệt, Sales/TP KD 403); KHÔNG rò biên/giá vốn cho người thiếu quyền; on_hold→ordered cũng gated.
"""
from __future__ import annotations

from datetime import date, timedelta

from app.db import SessionLocal
from app.models.quotation import STATUS_ACCEPTED, Quote, QuoteItem, QuoteVersion
from app.repositories.rbac_repo import DepartmentRepository, RoleRepository
from app.repositories.user_repo import UserRepository
from app.security import create_access_token, hash_password

ADMIN = {"username": "admin", "password": "admin123"}  # admin = Giám đốc (có approve_exception)
VALID = date.today() + timedelta(days=30)   # Date column — phải là date object (không phải chuỗi)


def _admin_token(client) -> str:
    return client.post("/api/auth/login", json=ADMIN).json()["access_token"]


def _h(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _admin_id() -> int:
    db = SessionLocal()
    try:
        return UserRepository(db).get_by_username("admin").id
    finally:
        db.close()


def _role_token(username: str, role_name: str, dept_name: str = "Kinh doanh") -> tuple[str, int]:
    db = SessionLocal()
    try:
        users = UserRepository(db)
        existing = users.get_by_username(username)
        if existing is not None:
            return create_access_token(str(existing.id)), existing.id
        dept = DepartmentRepository(db).get_by_name(dept_name)
        role = RoleRepository(db).get_by_name_and_department(role_name, dept.id)
        u = users.create(username=username, name=username, password_hash=hash_password("x"))
        users.set_assignment(u, department_id=dept.id, role_id=role.id, is_active=True)
        return create_access_token(str(u.id)), u.id
    finally:
        db.close()


def _seed_quote(*, sale_user_id: int, total: int, cost: int, discount: int = 0, valid_until=VALID) -> int:
    """Báo giá đã duyệt qty=1: giá bán TRƯỚC chiết khấu `total`, chiết khấu `discount`, giá vốn `cost`.
    (unit_price/selling_price = TRƯỚC CK như engine thật; đơn phải tự lấy net = total − discount.)"""
    db = SessionLocal()
    try:
        n = db.query(Quote).count() + 1
        q = Quote(
            quote_number=f"BGA-{n:04d}", customer_id=None, salesperson_id=sale_user_id,
            status=STATUS_ACCEPTED, valid_until=valid_until, created_by=sale_user_id,
        )
        db.add(q)
        db.flush()
        v = QuoteVersion(
            quote_id=q.id, version_number=1, status="accepted",
            total_cost_snapshot=cost, subtotal_amount=total, discount_amount=0,
            vat_percent=0, vat_amount=0, final_amount=total, created_by=sale_user_id,
        )
        db.add(v)
        db.flush()
        db.add(QuoteItem(
            quote_version_id=v.id, line_no=1, product_type="brochure", product_name="SP Test",
            quantity=1, unit="cái", total_cost_snapshot=cost, margin_percent=0,
            selling_price=total, unit_price=total, discount_amount=discount,
            vat_percent=0, vat_amount=0, final_amount=total - discount,
        ))
        q.current_version_id = v.id
        db.commit()
        return q.id
    finally:
        db.close()


def _create_order(client, token, qid, vat=8):
    body = {
        "quotation_id": qid, "order_type": "theo_yc", "order_kind": "moi",
        "parent_order_id": None, "has_customer_paper": False, "vat_pct_estimate": vat,
    }
    return client.post("/api/orders", json=body, headers=_h(token))


# --- soi điều kiện đặc thù -----------------------------------------------------

def test_high_value_trips_and_blocks_chot(client):
    token = _admin_token(client)
    # 100tr + VAT 8% = 108tr ≥ ngưỡng 100tr → "giá trị cao"; cost 50tr → biên 50% (không kích biên).
    qid = _seed_quote(sale_user_id=_admin_id(), total=100_000_000, cost=50_000_000)
    order = _create_order(client, token, qid).json()
    gate = order["gate"]
    assert gate["exception_required"] is True
    assert gate["exception_status"] == "pending"
    keys = {e["key"] for e in gate["exceptions"]}
    assert keys == {"high_value"}
    assert gate["can_confirm"] is False

    oid = order["id"]
    # Nộp đủ cọc (50% của 108tr = 54tr) — vẫn chưa chốt được vì CHƯA có GĐ duyệt.
    client.post(f"/api/orders/{oid}/payments", json={"amount": 54_000_000, "method": "bank"}, headers=_h(token))
    r = client.post(f"/api/orders/{oid}/transition", json={"to_status": "ordered"}, headers=_h(token))
    assert r.status_code == 422
    assert "Giám đốc" in r.json()["detail"]


def test_below_cost_trips(client):
    token = _admin_token(client)
    # bán 10tr, giá vốn 15tr → dưới giá vốn (lỗ). Không kích high_value (10.8tr < 100tr).
    qid = _seed_quote(sale_user_id=_admin_id(), total=10_000_000, cost=15_000_000)
    order = _create_order(client, token, qid).json()
    keys = {e["key"] for e in order["gate"]["exceptions"]}
    assert keys == {"below_cost"}
    assert order["gate"]["margin_pct"] < 0  # admin có quyền → thấy biên âm


def test_low_margin_trips(client):
    token = _admin_token(client)
    # bán 10tr, giá vốn 9tr → biên 10% < 15% (mà ≥ 0) → "lời mỏng".
    qid = _seed_quote(sale_user_id=_admin_id(), total=10_000_000, cost=9_000_000)
    order = _create_order(client, token, qid).json()
    keys = {e["key"] for e in order["gate"]["exceptions"]}
    assert keys == {"low_margin"}
    assert order["gate"]["margin_pct"] == 10


def test_discount_flows_into_order_and_margin(client):
    token = _admin_token(client)
    # Bán 120tr, giá vốn 90tr (biên gốc 25%), chiết khấu 30tr → khách chốt 90tr = HÒA VỐN (biên 0%).
    qid = _seed_quote(sale_user_id=_admin_id(), total=120_000_000, cost=90_000_000, discount=30_000_000)
    order = _create_order(client, token, qid, vat=0).json()
    # Đơn phải lấy giá SAU chiết khấu = 90tr (KHÔNG phải 120tr) → khớp số khách chốt.
    assert order["lines"][0]["line_total"] == 90_000_000
    # Biên thực 0% < 15% → PHẢI trip đặc thù (nếu lấy giá TRƯỚC CK sẽ là 25% → lọt cổng).
    keys = {e["key"] for e in order["gate"]["exceptions"]}
    assert "low_margin" in keys
    assert order["gate"]["margin_pct"] == 0


def test_normal_order_no_exception(client):
    token = _admin_token(client)
    # 10tr, giá vốn 5tr → biên 50%, giá trị nhỏ → KHÔNG đặc thù.
    qid = _seed_quote(sale_user_id=_admin_id(), total=10_000_000, cost=5_000_000)
    gate = _create_order(client, token, qid).json()["gate"]
    assert gate["exception_required"] is False
    assert gate["exception_status"] == "none"
    assert gate["exceptions"] == []


# --- GĐ duyệt → mở khóa; đổi xấu đi → stale; từ chối → chặn --------------------

def test_gd_approve_unlocks_chot(client):
    token = _admin_token(client)
    qid = _seed_quote(sale_user_id=_admin_id(), total=100_000_000, cost=50_000_000)
    oid = _create_order(client, token, qid).json()["id"]
    client.post(f"/api/orders/{oid}/payments", json={"amount": 54_000_000, "method": "bank"}, headers=_h(token))
    # GĐ duyệt đơn đặc thù.
    r = client.post(f"/api/orders/{oid}/approval", json={"decision": "approved", "note": "OK khách lớn"}, headers=_h(token))
    assert r.status_code == 200, r.text
    assert r.json()["gate"]["exception_status"] == "approved"
    assert r.json()["gate"]["can_confirm"] is True
    # Giờ chốt được.
    r = client.post(f"/api/orders/{oid}/transition", json={"to_status": "ordered"}, headers=_h(token))
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "ordered"
    # Lịch sử duyệt có 1 bản.
    hist = client.get(f"/api/orders/{oid}/approvals", headers=_h(token)).json()
    assert len(hist["items"]) == 1 and hist["items"][0]["decision"] == "approved"


def test_gd_reject_blocks_chot(client):
    token = _admin_token(client)
    qid = _seed_quote(sale_user_id=_admin_id(), total=100_000_000, cost=50_000_000)
    oid = _create_order(client, token, qid).json()["id"]
    client.post(f"/api/orders/{oid}/payments", json={"amount": 54_000_000, "method": "bank"}, headers=_h(token))
    r = client.post(f"/api/orders/{oid}/approval", json={"decision": "rejected", "note": "giá quá thấp"}, headers=_h(token))
    assert r.status_code == 200
    assert r.json()["gate"]["exception_status"] == "rejected"
    assert r.json()["gate"]["can_confirm"] is False
    r = client.post(f"/api/orders/{oid}/transition", json={"to_status": "ordered"}, headers=_h(token))
    assert r.status_code == 422
    assert "từ chối" in r.json()["detail"].lower()


def test_approval_goes_stale_when_order_worsens(client):
    token = _admin_token(client)
    qid = _seed_quote(sale_user_id=_admin_id(), total=100_000_000, cost=50_000_000)
    oid = _create_order(client, token, qid).json()["id"]
    client.post(f"/api/orders/{oid}/approval", json={"decision": "approved", "note": "ok"}, headers=_h(token))
    # Đơn PHÌNH giá trị SAU khi GĐ duyệt (mô phỏng sửa dòng qua DB) → vượt mức đã ký → stale.
    db = SessionLocal()
    try:
        from app.models.order import OrderLine
        ln = db.query(OrderLine).filter(OrderLine.order_id == oid).first()
        ln.line_total = 300_000_000
        db.commit()
    finally:
        db.close()
    gate = client.get(f"/api/orders/{oid}", headers=_h(token)).json()["gate"]
    assert gate["exception_status"] == "stale"
    assert gate["can_confirm"] is False


def test_approve_rejects_non_exceptional_order(client):
    token = _admin_token(client)
    # Đơn thường (không đặc thù) → không cho tạo bản duyệt vô nghĩa.
    qid = _seed_quote(sale_user_id=_admin_id(), total=10_000_000, cost=5_000_000)
    oid = _create_order(client, token, qid).json()["id"]
    r = client.post(f"/api/orders/{oid}/approval", json={"decision": "approved"}, headers=_h(token))
    assert r.status_code == 422
    assert "đặc thù" in r.json()["detail"].lower()


# --- RBAC + không rò số -------------------------------------------------------

def test_sales_cannot_approve_exception(client):
    _admin_token(client)  # đảm bảo seed
    sales_token, _ = _role_token("nv_sales_a2", "NV Sales")
    admin_token = _admin_token(client)
    qid = _seed_quote(sale_user_id=_admin_id(), total=100_000_000, cost=50_000_000)
    oid = _create_order(client, admin_token, qid).json()["id"]
    # NV Sales KHÔNG có quyền approve_exception → 403 (dependency chặn trước cả scope).
    r = client.post(f"/api/orders/{oid}/approval", json={"decision": "approved"}, headers=_h(sales_token))
    assert r.status_code == 403


def test_truongphong_kd_cannot_approve_exception(client):
    _admin_token(client)
    tp_token, _ = _role_token("tp_kd_a2", "Trưởng phòng KD")
    admin_token = _admin_token(client)
    qid = _seed_quote(sale_user_id=_admin_id(), total=100_000_000, cost=50_000_000)
    oid = _create_order(client, admin_token, qid).json()["id"]
    # TP KD chốt được đơn THƯỜNG (can_approve) nhưng KHÔNG duyệt được đơn ĐẶC THÙ.
    r = client.post(f"/api/orders/{oid}/approval", json={"decision": "approved"}, headers=_h(tp_token))
    assert r.status_code == 403


def test_sales_does_not_see_margin_number(client):
    _admin_token(client)
    sales_token, sales_id = _role_token("nv_sales_margin", "NV Sales")
    # Sales tạo đơn đặc thù của CHÍNH MÌNH (owner=sales) → xem được (scope own) nhưng KHÔNG thấy số biên.
    qid = _seed_quote(sale_user_id=sales_id, total=10_000_000, cost=15_000_000)
    order = _create_order(client, sales_token, qid).json()
    gate = order["gate"]
    assert gate["exception_required"] is True
    assert {e["key"] for e in gate["exceptions"]} == {"below_cost"}   # nhãn định tính vẫn thấy
    assert gate["margin_pct"] is None                                  # số nhạy cảm bị ẩn
    # Admin (GĐ) xem CÙNG đơn → thấy số biên.
    admin_gate = client.get(f"/api/orders/{order['id']}", headers=_h(_admin_token(client))).json()["gate"]
    assert admin_gate["margin_pct"] is not None


# --- vá lách cổng: on_hold → ordered cũng phải qua gate -----------------------

def test_on_hold_to_ordered_is_gated(client):
    token = _admin_token(client)
    qid = _seed_quote(sale_user_id=_admin_id(), total=100_000_000, cost=50_000_000)
    oid = _create_order(client, token, qid).json()["id"]
    client.post(f"/api/orders/{oid}/payments", json={"amount": 54_000_000, "method": "bank"}, headers=_h(token))
    # draft → on_hold (không gated)
    r = client.post(f"/api/orders/{oid}/transition", json={"to_status": "on_hold"}, headers=_h(token))
    assert r.status_code == 200
    # on_hold → ordered PHẢI qua gate đặc thù (chưa duyệt) → chặn, KHÔNG lách.
    r = client.post(f"/api/orders/{oid}/transition", json={"to_status": "ordered"}, headers=_h(token))
    assert r.status_code == 422
    assert "Giám đốc" in r.json()["detail"]
