"""CRM-360 analytics API (spec-06) — KPIs, tier, dashboard, history, Excel.

Every figure MUST be computed from real orders/quotations; a customer with no history
returns honest zeros / has_data=False (never fabricated numbers).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.db import SessionLocal
from app.models.order import Order, OrderLine
from app.models.phieu_tinh_gia import PhieuThanhPhan, PhieuThanhPham, PhieuTinhGia
from app.models.quotation import Quote, QuoteVersion
from app.models.vat_lieu_kho import ChungLoaiGiay, GiayNguyen
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
                order_kind="moi",
                sale_user_id=sale.id if sale else None,
                status="ordered",
                created_at=now - timedelta(days=months_ago * 30 + 2),
            )
            o.lines.append(
                OrderLine(description=desc, qty=qty, unit_price_snapshot=unit, line_total=qty * unit)
            )
            db.add(o)
        q = Quote(
            quote_number="BGX1",
            customer_id=customer_id,
            salesperson_id=sale.id if sale else None,
            status="sent",
            created_at=now - timedelta(days=20),
        )
        db.add(q)
        db.flush()
        qv = QuoteVersion(
            quote_id=q.id, version_number=1, status="sent",
            total_cost_snapshot=20_000_000, subtotal_amount=25_000_000, discount_amount=0,
            vat_percent=0, vat_amount=0, final_amount=25_000_000,
            sent_at=now - timedelta(days=20), created_at=now - timedelta(days=20),
        )
        db.add(qv)
        db.flush()
        q.current_version_id = qv.id
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


# Redesign spec-06 v2: tier (loyal/partner) đã BỎ → test phân hạng gỡ; giữ test sort doanh số thật.


def test_revenue_sort(client):
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
    # SEAM-16 (Công nợ phải thu) ĐÃ ĐƯỢC NỐI ngày 10/08/2026 — `deps.py` tiêm
    # `AccountingReceivablePort` thật thay cho stub ném NotImplementedError. Trước đó dòng này
    # khẳng định `available is False` ("chưa xây"), và nó đỏ suốt từ hôm nối cho tới 11/08 vì
    # không ai cập nhật test theo.
    #
    # Ý ĐỒ GỐC vẫn giữ: KHÔNG bịa số. Khác ở chỗ nay số 0 là **số thật đọc được** (khách này chưa
    # có hoá đơn nào), chứ không phải số 0 bịa ra để lấp chỗ trống — nên `available` phải True.
    assert d["receivable"]["available"] is True
    # Đơn đã chốt vẫn chưa phải công nợ. Chỉ hóa đơn bán đã ghi nhận mới làm phát sinh dư nợ.
    assert d["receivable"]["balance"] == 0


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
    # Card "Thông số in thường đặt" cũng phải trống — trước đây nó hiện 5 dòng hardcode giống hệt
    # nhau cho MỌI khách (Couche 200gsm · 5 màu · A4/A5…) kể cả khách chưa có phiếu nào.
    assert d["print_specs"] == []
    assert d["print_specs_phieu"] == 0


# --- Thông số in thường đặt (đọc từ phiếu tính giá thật) ---------------------


def _add_ptg_with_specs(customer_id: int) -> None:
    """2 phiếu tính giá (3 sản phẩm) gắn báo giá của khách: giấy · mực · khổ · gia công thật."""
    db = SessionLocal()
    try:
        cl = ChungLoaiGiay(ma="COUCHE-T", ten="Couché")
        db.add(cl)
        db.flush()
        giay = GiayNguyen(
            ma="COUCHE-300-T", ten="Couché 300 65×86", chung_loai_giay_id=cl.id,
            kho_dai=860, kho_rong=650, gsm=300,
        )
        db.add(giay)
        db.flush()

        # (mực mặt A, mực mặt B, rộng×dài thành phẩm mm, các bước gia công)
        san_pham = [
            (["C", "M", "Y", "K"], ["C", "M", "Y", "K"], (210, 297), ["Cán màng bóng", "Đóng keo"]),
            (["C", "M", "Y", "K"], ["K", "185C"], (210, 297), ["Cán màng bóng"]),
            (["K"], [], (148, 210), []),
        ]
        for i, (muc_a, muc_b, (rong, dai), buoc) in enumerate(san_pham):
            ptg = PhieuTinhGia(ma=f"PTG-T{i}", ten_san_pham="Catalogue", so_luong=1000)
            db.add(ptg)
            db.flush()
            tp = PhieuThanhPhan(
                phieu_id=ptg.id, ten="Ruột", giay_id=giay.id, muc_a=muc_a, muc_b=muc_b,
                rong_thanh_pham=rong, dai_thanh_pham=dai,
            )
            db.add(tp)
            db.flush()
            for j, ten in enumerate(buoc):
                db.add(PhieuThanhPham(thanh_phan_id=tp.id, thu_tu=j, ten=ten))
            db.add(
                Quote(
                    quote_number=f"BGSPEC{i}",
                    customer_id=customer_id,
                    phieu_tinh_gia_id=ptg.id,
                    status="sent",
                )
            )
        db.commit()
    finally:
        db.close()


def test_print_specs_from_real_phieu_tinh_gia(client):
    """Giấy · số màu · gia công · khổ lấy từ phiếu tính giá gắn báo giá — không hardcode."""
    token = _admin_token(client)
    cid = client.post(
        "/api/customers", json={"name": "Khách Có Phiếu"}, headers=_h(token)
    ).json()["customer"]["id"]
    _add_ptg_with_specs(cid)

    d = client.get(f"/api/customers/{cid}/dashboard", headers=_h(token)).json()
    assert d["print_specs_phieu"] == 3
    by_key = {s["key"]: s for s in d["print_specs"]}
    # Giấy: gom theo chủng loại + định lượng, cả 3 sản phẩm dùng chung ⇒ 100%.
    assert by_key["giay"]["value"] == "Couché 300gsm"
    assert by_key["giay"]["pct"] == 100
    # Màu = số KẼM = |A ∪ B|: 4 màu CMYK gặp 1 lần, "5 màu (CMYK + 1 pha)" 1 lần, "1 màu" 1 lần
    # ⇒ mode nào cũng 33%, nhưng nhãn phải nằm trong ba nhãn tính đúng đó.
    assert by_key["mau"]["value"] in {"4 màu (CMYK)", "5 màu (CMYK + 1 pha)", "1 màu"}
    assert by_key["mau"]["pct"] == 33
    # Khổ: 2/3 sản phẩm là 210×297 ⇒ gọi tên A4, 67%.
    assert by_key["kho"]["value"] == "A4"
    assert by_key["kho"]["pct"] == 67
    # Gia công: 2 bước hay gặp nhất, % của bước đầu (2/3 sản phẩm có cán màng bóng).
    assert by_key["gia_cong"]["value"] == "Cán màng bóng · Đóng keo"
    assert by_key["gia_cong"]["pct"] == 67


def test_print_specs_bo_qua_bao_gia_da_huy(client):
    """Báo giá đã HUỶ không được kéo thông số của nó vào thói quen của khách."""
    token = _admin_token(client)
    cid = client.post(
        "/api/customers", json={"name": "Khách Huỷ Báo Giá"}, headers=_h(token)
    ).json()["customer"]["id"]
    db = SessionLocal()
    try:
        ptg = PhieuTinhGia(ma="PTG-HUY", ten_san_pham="Tờ rơi", so_luong=500)
        db.add(ptg)
        db.flush()
        db.add(
            PhieuThanhPhan(
                phieu_id=ptg.id, ten="Tờ rơi", kho_nguyen="Ford 70 65×86",
                muc_a=["C", "M", "Y", "K"], rong_thanh_pham=148, dai_thanh_pham=210,
            )
        )
        db.add(
            Quote(
                quote_number="BGHUY1", customer_id=cid,
                phieu_tinh_gia_id=ptg.id, status="cancelled",
            )
        )
        db.commit()
    finally:
        db.close()

    d = client.get(f"/api/customers/{cid}/dashboard", headers=_h(token)).json()
    assert d["print_specs"] == []
    assert d["print_specs_phieu"] == 0


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
