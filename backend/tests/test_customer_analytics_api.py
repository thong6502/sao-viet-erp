"""CRM-360 analytics API (spec-06) — KPIs, tier, dashboard, history, Excel.

Every figure MUST be computed from real orders/quotations; a customer with no history
returns honest zeros / has_data=False (never fabricated numbers).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.db import SessionLocal
from app.models.order import Order, OrderLine
from app.models.quotation import Quotation
from app.repositories.rbac_repo import DepartmentRepository, RoleRepository
from app.repositories.user_repo import UserRepository
from app.security import create_access_token, hash_password
from app.seed import seed_customers, seed_kd_staff

ADMIN = {"username": "admin", "password": "admin123"}


def _admin_token(client) -> str:
    return client.post("/api/auth/login", json=ADMIN).json()["access_token"]


def _h(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _seed_staff_customers() -> None:
    db = SessionLocal()
    try:
        seed_kd_staff(db)
        seed_customers(db)
    finally:
        db.close()


def _customer_id_by_name(fragment: str) -> int:
    from app.repositories.customer_repo import CustomerRepository

    db = SessionLocal()
    try:
        from app.seed import _SeedActor

        for c in CustomerRepository(db).list_scoped_all(scope="all", actor=_SeedActor()):
            if fragment in c.name:
                return c.id
    finally:
        db.close()
    raise AssertionError(f"no customer matching {fragment!r}")


def _add_orders(customer_id: int, sale_username: str) -> None:
    """Add two priced orders (one this month, one ~2 months ago) + a sent quotation."""
    db = SessionLocal()
    try:
        sale = UserRepository(db).get_by_username(sale_username)
        now = datetime.now(timezone.utc)
        for months_ago, desc, qty, unit in [
            (0, "Catalogue A4", 2, 12_000_000),
            (2, "Name card", 5000, 900),
        ]:
            o = Order(
                order_no=f"DHX{months_ago}",
                customer_id=customer_id,
                order_type="theo_yc",
                order_kind="moi",
                sale_user_id=sale.id if sale else None,
                status="ordered",
                created_at=now - timedelta(days=months_ago * 30 + 2),
            )
            o.lines.append(
                OrderLine(description=desc, qty=qty, unit_price_snapshot=unit, line_total=qty * unit)
            )
            db.add(o)
        db.add(
            Quotation(
                code="BGX1",
                version=1,
                customer_id=customer_id,
                total=25_000_000,
                margin=5_000_000,
                discount=0,
                sale_user_id=sale.id if sale else None,
                status="sent",
                row_version=1,
                created_at=now - timedelta(days=20),
            )
        )
        db.commit()
    finally:
        db.close()


# --- KPI strip + tier from real orders --------------------------------------


def test_list_returns_kpis_and_derived_tier(client):
    _seed_staff_customers()
    token = _admin_token(client)
    cid = _customer_id_by_name("An Phát")
    _add_orders(cid, "sale1")

    body = client.get("/api/customers?size=200", headers=_h(token)).json()
    assert "kpis" in body
    kpis = body["kpis"]
    assert kpis["total_customers"] >= 1
    # An Phát got 2×12tr + 5000×900 = 28.5tr < 50tr in 12m → not "loyal", but has orders.
    row = next(c for c in body["items"] if c["id"] == cid)
    assert row["orders_total"] == 2
    assert row["revenue_12m"] == 2 * 12_000_000 + 5000 * 900
    # avg order value is computed from real orders, non-negative
    assert kpis["avg_order_value"] >= 0


def test_loyal_tier_from_high_spend(client):
    """A customer with ≥ LOYAL_REVENUE_VND in 12m is classified 'loyal' (VIP theo chi tiêu)."""
    _seed_staff_customers()
    token = _admin_token(client)
    cid = _customer_id_by_name("An Phát")
    # One big order this month → over the 50tr loyal threshold.
    db = SessionLocal()
    try:
        sale = UserRepository(db).get_by_username("sale1")
        o = Order(
            order_no="DHBIG",
            customer_id=cid,
            order_type="theo_yc",
            order_kind="moi",
            sale_user_id=sale.id,
            status="ordered",
            created_at=datetime.now(timezone.utc) - timedelta(days=2),
        )
        o.lines.append(
            OrderLine(description="In lịch", qty=1, unit_price_snapshot=60_000_000, line_total=60_000_000)
        )
        db.add(o)
        db.commit()
    finally:
        db.close()
    body = client.get("/api/customers?tier=loyal&size=200", headers=_h(token)).json()
    assert any(c["id"] == cid for c in body["items"])
    assert body["kpis"]["loyal_count"] >= 1


def test_tier_filter_and_revenue_sort(client):
    _seed_staff_customers()
    token = _admin_token(client)
    cid = _customer_id_by_name("An Phát")
    _add_orders(cid, "sale1")
    # Sort by revenue desc → the customer with orders is at/near the top.
    body = client.get("/api/customers?sort=-revenue&size=200", headers=_h(token)).json()
    assert body["items"][0]["revenue_12m"] >= body["items"][-1]["revenue_12m"]


# --- Dashboard computed from real data --------------------------------------


def test_dashboard_computes_from_real_orders(client):
    _seed_staff_customers()
    token = _admin_token(client)
    cid = _customer_id_by_name("An Phát")
    _add_orders(cid, "sale1")

    d = client.get(f"/api/customers/{cid}/dashboard", headers=_h(token)).json()
    assert d["has_data"] is True
    assert d["orders_total"] == 2
    assert len(d["months"]) == 12
    # Revenue appears in the correct month buckets.
    total_series = sum(m["revenue"] for m in d["months"])
    assert total_series == 2 * 12_000_000 + 5000 * 900
    # Product mix (donut) has both descriptions.
    labels = {s["label"] for s in d["product_mix"]}
    assert "Catalogue A4" in labels and "Name card" in labels
    # Heatmap has at least one cell.
    assert len(d["heatmap"]) >= 1
    # Công nợ still SEAM-16 unavailable (no fake 0).
    assert d["receivable"]["available"] is False


def test_dashboard_empty_state_no_fake_numbers(client):
    """A customer with NO orders → has_data=False, zeros — never fabricated."""
    token = _admin_token(client)
    created = client.post(
        "/api/customers", json={"name": "Khách Chưa Mua"}, headers=_h(token)
    ).json()["customer"]
    d = client.get(f"/api/customers/{created['id']}/dashboard", headers=_h(token)).json()
    assert d["has_data"] is False
    assert d["orders_total"] == 0
    assert d["revenue_12m"] == 0
    assert d["avg_order_value"] is None
    assert d["product_mix"] == []


# --- History tables wired from real orders/quotations -----------------------


def test_order_and_quote_history_are_real(client):
    _seed_staff_customers()
    token = _admin_token(client)
    cid = _customer_id_by_name("An Phát")
    _add_orders(cid, "sale1")

    orders = client.get(f"/api/customers/{cid}/orders", headers=_h(token)).json()
    assert len(orders["items"]) == 2
    assert all(o["total"] is not None for o in orders["items"])

    quotes = client.get(f"/api/customers/{cid}/quotations", headers=_h(token)).json()
    assert len(quotes["items"]) == 1
    assert quotes["items"][0]["code"] == "BGX1"


def test_order_history_csv_export(client):
    _seed_staff_customers()
    token = _admin_token(client)
    cid = _customer_id_by_name("An Phát")
    _add_orders(cid, "sale1")
    resp = client.get(f"/api/customers/{cid}/orders.csv", headers=_h(token))
    assert resp.status_code == 200
    assert "text/csv" in resp.headers["content-type"]
    assert "attachment" in resp.headers["content-disposition"]
    text = resp.content.decode("utf-8")
    assert "Mã đơn" in text and "Catalogue A4" in text


# --- Nhật ký (unified activity timeline) ------------------------------------


def test_customer_audit_merges_profile_and_documents(client):
    """Nhật ký = profile edits (audit log) + REAL order/quote events, newest first,
    with drill refs on document rows."""
    _seed_staff_customers()
    token = _admin_token(client)
    cid = _customer_id_by_name("An Phát")
    _add_orders(cid, "sale1")
    # A profile edit → an audit-log row targeting this customer.
    client.put(
        f"/api/customers/{cid}",
        json={"name": "An Phát", "credit_limit": 99_000_000, "status": "active"},
        headers=_h(token),
    )

    body = client.get(f"/api/customers/{cid}/audit", headers=_h(token)).json()
    items = body["items"]
    kinds = {r["kind"] for r in items}
    assert "order" in kinds and "quote" in kinds and "profile" in kinds
    # Document rows drill through; profile rows do not.
    order_rows = [r for r in items if r["kind"] == "order"]
    assert order_rows and all(r["ref_type"] == "order" and r["ref_id"] for r in order_rows)
    quote_rows = [r for r in items if r["kind"] == "quote"]
    assert quote_rows and all(r["ref_type"] == "quotation" for r in quote_rows)
    assert all(r["ref_type"] is None for r in items if r["kind"] == "profile")
    # Newest-first ordering.
    times = [r["at"] for r in items]
    assert times == sorted(times, reverse=True)


def test_customer_audit_out_of_scope_404(client):
    _seed_staff_customers()

    def _role_token(username: str, role_name: str) -> str:
        db = SessionLocal()
        try:
            users = UserRepository(db)
            dept = DepartmentRepository(db).get_by_name("Kinh doanh")
            role = RoleRepository(db).get_by_name_and_department(role_name, dept.id)
            u = users.create(username=username, name=username, password_hash=hash_password("x"))
            users.set_assignment(u, department_id=dept.id, role_id=role.id, is_active=True)
            return create_access_token(str(u.id))
        finally:
            db.close()

    sale2 = _role_token("sale2audit", "NV Sales")
    cid = _customer_id_by_name("An Phát")  # owned by sale1
    resp = client.get(f"/api/customers/{cid}/audit", headers=_h(sale2))
    assert resp.status_code == 404


# --- Scope guard on analytics -----------------------------------------------


def test_dashboard_out_of_scope_404(client):
    _seed_staff_customers()

    def _role_token(username: str, role_name: str) -> str:
        db = SessionLocal()
        try:
            users = UserRepository(db)
            dept = DepartmentRepository(db).get_by_name("Kinh doanh")
            role = RoleRepository(db).get_by_name_and_department(role_name, dept.id)
            u = users.create(username=username, name=username, password_hash=hash_password("x"))
            users.set_assignment(u, department_id=dept.id, role_id=role.id, is_active=True)
            return create_access_token(str(u.id))
        finally:
            db.close()

    # sale1's customer, opened by sale2 → 404 (scope guard, not leaked).
    admin = _admin_token(client)
    sale2 = _role_token("sale2b", "NV Sales")
    cid = _customer_id_by_name("An Phát")  # owned by sale1
    resp = client.get(f"/api/customers/{cid}/dashboard", headers=_h(sale2))
    assert resp.status_code == 404
