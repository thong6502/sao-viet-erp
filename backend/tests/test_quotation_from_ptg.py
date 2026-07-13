"""BG-1 — Báo giá dựng lại nguồn: 1 Phiếu tính giá (PTG) → 1 Báo giá.

Kiểm: tạo báo giá TỪ 1 PTG (dòng = mỗi sản phẩm PhieuThanhPhan, giá vốn khóa = gia_von_tp, markup mặc
định 20% → giá bán); guard 1 PTG → 1 BG đang hiệu lực (409); endpoint /by-phieu tra báo giá của PTG.
"""
from __future__ import annotations

from app.db import SessionLocal
from app.models.customer import Customer, CustomerAddress, CustomerContact
from app.models.phieu_tinh_gia import PhieuThanhPhan, PhieuTinhGia
from app.repositories.user_repo import UserRepository

ADMIN = {"username": "admin", "password": "admin123"}


def _token(client) -> str:
    return client.post("/api/auth/login", json=ADMIN).json()["access_token"]


def _h(t: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {t}"}


def _seed_ptg(*, so_luong=10_000, products: list[tuple[str, int, int]] | None = None) -> int:
    """Tạo 1 Phiếu tính giá với các sản phẩm (ten, so_luong, gia_von_tp). Trả id.
    products=[] (rỗng) KHÁC None: rỗng = phiếu không có sản phẩm (test chặn)."""
    if products is None:
        products = [("Tờ rơi A5", 10_000, 8_000_000)]
    db = SessionLocal()
    try:
        n = db.query(PhieuTinhGia).count() + 1
        p = PhieuTinhGia(
            ma=f"PTG-TEST-{n:04d}", ten_san_pham=(products[0][0] if products else "PTG rỗng"), so_luong=so_luong,
            tong_gia_von=sum(x[2] for x in products), gia_von_don=0, ktv="KTV Test",
        )
        db.add(p)
        db.flush()
        for i, (ten, sl, von) in enumerate(products):
            db.add(PhieuThanhPhan(
                phieu_id=p.id, thu_tu=i, ten=ten, so_luong=sl, gia_von_tp=von,
                loai_thanh_phan="to_roi",
            ))
        db.commit()
        return p.id
    finally:
        db.close()


def test_create_quote_from_ptg_one_line_per_product(client):
    token = _token(client)
    # 2 sản phẩm trong 1 PTG → 2 dòng báo giá.
    pid = _seed_ptg(products=[("Ruột", 5_000, 8_000_000), ("Bìa", 5_000, 2_000_000)])
    r = client.post("/api/quotations", json={"phieu_tinh_gia_id": pid}, headers=_h(token))
    assert r.status_code == 201, r.text
    d = r.json()
    assert len(d["items"]) == 2
    # Giá vốn KHÓA = gia_von_tp; markup mặc định 20% → giá bán = giá vốn / 0.8 = ×1.25.
    ruot = next(it for it in d["items"] if it["product_name"] == "Ruột")
    assert ruot["total_cost_snapshot"] == 8_000_000
    assert ruot["quantity"] == 5_000
    assert round(ruot["selling_price"]) == 10_000_000   # 8tr / (1-0.20)
    assert round(ruot["margin_percent"]) == 20


def test_one_ptg_one_active_quote(client):
    token = _token(client)
    pid = _seed_ptg()
    r1 = client.post("/api/quotations", json={"phieu_tinh_gia_id": pid}, headers=_h(token))
    assert r1.status_code == 201
    # PTG đã có báo giá đang hiệu lực → tạo cái thứ 2 bị chặn 409.
    r2 = client.post("/api/quotations", json={"phieu_tinh_gia_id": pid}, headers=_h(token))
    assert r2.status_code == 409
    assert "hiệu lực" in r2.json()["detail"].lower()


def test_by_phieu_lookup(client):
    token = _token(client)
    pid = _seed_ptg()
    # Chưa có báo giá → null.
    r0 = client.get(f"/api/quotations/by-phieu/{pid}", headers=_h(token))
    assert r0.status_code == 200 and r0.json()["quote_id"] is None
    # Tạo rồi → trả về id + mã.
    created = client.post("/api/quotations", json={"phieu_tinh_gia_id": pid}, headers=_h(token)).json()
    r1 = client.get(f"/api/quotations/by-phieu/{pid}", headers=_h(token))
    assert r1.json()["quote_id"] == created["id"]
    assert r1.json()["quote_number"].startswith("BG")


def test_ptg_no_products_rejected(client):
    token = _token(client)
    pid = _seed_ptg(products=[])
    r = client.post("/api/quotations", json={"phieu_tinh_gia_id": pid}, headers=_h(token))
    assert r.status_code == 422
    assert "sản phẩm" in r.json()["detail"].lower()


# --- P2 (redesign-bao-gia §4/§5): auto-fill liên hệ chính + ĐC giao mặc định + MÃ PO ------

def _seed_customer_full() -> int:
    """Khách có 2 liên hệ (1 is_primary) + 2 điểm giao (1 is_default)."""
    db = SessionLocal()
    try:
        n = db.query(Customer).count() + 1
        c = Customer(code=f"KHT-{n:04d}", name="Cty Auto-fill Test")
        db.add(c)
        db.flush()
        db.add(CustomerContact(customer_id=c.id, name="Chị Lan", title="Kế toán",
                               phone="0900000000", is_primary=False))
        db.add(CustomerContact(customer_id=c.id, name="Anh Thanh", title="Mua hàng",
                               phone="0379897367", is_primary=True))
        db.add(CustomerAddress(customer_id=c.id, label="Khác", address="ĐC khác", is_default=False))
        db.add(CustomerAddress(customer_id=c.id, label="Kho Bến Cầu",
                               address="Lô A5, KCN Hiệp Thành, Tây Ninh", phone="08", is_default=True))
        db.commit()
        return c.id
    finally:
        db.close()


def test_create_quote_autofills_contact_and_delivery(client):
    token = _token(client)
    cid = _seed_customer_full()
    pid = _seed_ptg()
    r = client.post("/api/quotations",
                    json={"phieu_tinh_gia_id": pid, "customer_id": cid}, headers=_h(token))
    assert r.status_code == 201, r.text
    d = r.json()
    # Auto-fill người liên hệ CHÍNH (is_primary) — không lấy nhầm liên hệ đầu danh sách.
    assert d["contact_name_snapshot"] == "Anh Thanh"
    assert d["contact_phone_snapshot"] == "0379897367"
    assert d["contact_title_snapshot"] == "Mua hàng"
    # Auto-fill ĐC giao MẶC ĐỊNH (is_default).
    assert d["delivery_address"] == "Lô A5, KCN Hiệp Thành, Tây Ninh"


def test_delivery_address_explicit_not_overridden(client):
    token = _token(client)
    cid = _seed_customer_full()
    pid = _seed_ptg()
    r = client.post("/api/quotations",
                    json={"phieu_tinh_gia_id": pid, "customer_id": cid,
                          "delivery_address": "Giao tận xưởng B"}, headers=_h(token))
    assert r.status_code == 201, r.text
    # Caller cung cấp ĐC giao → KHÔNG bị auto-fill đè.
    assert r.json()["delivery_address"] == "Giao tận xưởng B"


def test_item_po_code_roundtrip(client):
    token = _token(client)
    pid = _seed_ptg()
    q = client.post("/api/quotations", json={"phieu_tinh_gia_id": pid}, headers=_h(token)).json()
    item_id = q["items"][0]["id"]
    r = client.put(f"/api/quotations/{q['id']}",
                   json={"items": [{"id": item_id, "margin_percent": 20, "po_code": "PO-40/06"}]},
                   headers=_h(token))
    assert r.status_code == 200, r.text
    assert r.json()["items"][0]["po_code"] == "PO-40/06"


def test_send_freezes_ptg_cost_snapshot(client):
    """B5 (redesign-bao-gia §8): gửi khách đường PTG → freeze phân rã giá vốn (source=phieu_tinh_gia)."""
    from app.models.quotation import Quote, QuoteVersion
    token = _token(client)
    pid = _seed_ptg(products=[("Ruột", 5_000, 8_000_000)])
    q = client.post("/api/quotations", json={"phieu_tinh_gia_id": pid}, headers=_h(token)).json()
    r = client.post(f"/api/quotations/{q['id']}/transition",
                    json={"to_status": "sent"}, headers=_h(token))
    assert r.status_code == 200, r.text
    db = SessionLocal()
    try:
        quote = db.query(Quote).filter(Quote.id == q["id"]).one()
        v = db.get(QuoteVersion, quote.current_version_id)
        assert v.internal_cost_snapshot_json is not None
        assert v.internal_cost_snapshot_json["source"] == "phieu_tinh_gia"
        assert v.internal_cost_snapshot_json["lines"][0]["total_cost_snapshot"] == 8_000_000
    finally:
        db.close()
