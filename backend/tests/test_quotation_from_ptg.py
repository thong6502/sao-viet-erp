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

def _seed_customer_full(*, name="Cty Auto-fill Test", primary="Anh Thanh", title="Mua hàng",
                        phone="0379897367", addr="Lô A5, KCN Hiệp Thành, Tây Ninh") -> int:
    """Khách có 2 liên hệ (1 is_primary) + 2 điểm giao (1 is_default)."""
    db = SessionLocal()
    try:
        n = db.query(Customer).count() + 1
        c = Customer(code=f"KHT-{n:04d}", name=name)
        db.add(c)
        db.flush()
        db.add(CustomerContact(customer_id=c.id, name="Chị Lan", title="Kế toán",
                               phone="0900000000", is_primary=False))
        db.add(CustomerContact(customer_id=c.id, name=primary, title=title,
                               phone=phone, is_primary=True))
        db.add(CustomerAddress(customer_id=c.id, label="Khác", address="ĐC khác", is_default=False))
        db.add(CustomerAddress(customer_id=c.id, label="Kho chính",
                               address=addr, phone="08", is_default=True))
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


def test_detail_exposes_ptg_ref(client):
    """P3 (link PTG): detail trả phieu_tinh_gia_id + ma để FE render link mở phiếu."""
    token = _token(client)
    pid = _seed_ptg()
    q = client.post("/api/quotations", json={"phieu_tinh_gia_id": pid}, headers=_h(token)).json()
    assert q["phieu_tinh_gia_id"] == pid
    assert q["phieu_tinh_gia_ma"] and q["phieu_tinh_gia_ma"].startswith("PTG-TEST-")


def test_change_customer_refreshes_contact_and_delivery(client):
    """P3 (customer picker): đổi khách → làm mới liên hệ chính + ĐC giao mặc định của khách mới."""
    token = _token(client)
    cid_a = _seed_customer_full()  # Anh Thanh · Lô A5...
    pid = _seed_ptg()
    q = client.post("/api/quotations",
                    json={"phieu_tinh_gia_id": pid, "customer_id": cid_a}, headers=_h(token)).json()
    assert q["contact_name_snapshot"] == "Anh Thanh"
    cid_b = _seed_customer_full(name="Cty B", primary="Chị Mai", title="Kho",
                                phone="0911222333", addr="KCN Sóng Thần, Bình Dương")
    r = client.put(f"/api/quotations/{q['id']}",
                   json={"customer_id": cid_b, "delivery_address": None}, headers=_h(token))
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["customer_id"] == cid_b
    assert d["contact_name_snapshot"] == "Chị Mai"
    assert d["contact_phone_snapshot"] == "0911222333"
    assert d["delivery_address"] == "KCN Sóng Thần, Bình Dương"


# --- Phương án A: PTG đổi số → ĐỒNG BỘ sang báo giá (resync-from-ptg) ------------
# Nháp = cập nhật TẠI CHỖ (giữ markup); đã chốt = tạo PHIÊN BẢN MỚI.

def _edit_ptg_first_product(pid: int, *, gia_von_tp: int, so_luong: int) -> None:
    """Giả lập người dùng quay về PTG tính lại: sửa giá vốn + SL của 'sản phẩm' đầu."""
    db = SessionLocal()
    try:
        tp = (
            db.query(PhieuThanhPhan)
            .filter(PhieuThanhPhan.phieu_id == pid)
            .order_by(PhieuThanhPhan.thu_tu)
            .first()
        )
        tp.gia_von_tp = gia_von_tp
        tp.so_luong = so_luong
        db.commit()
    finally:
        db.close()


def _version_count(quote_id: int) -> int:
    from app.models.quotation import QuoteVersion
    db = SessionLocal()
    try:
        return db.query(QuoteVersion).filter(QuoteVersion.quote_id == quote_id).count()
    finally:
        db.close()


def _first_tp_id(pid: int) -> int:
    db = SessionLocal()
    try:
        t = (db.query(PhieuThanhPhan)
             .filter(PhieuThanhPhan.phieu_id == pid)
             .order_by(PhieuThanhPhan.thu_tu).first())
        return t.id
    finally:
        db.close()


def _replace_ptg_products(pid: int, products: list[tuple[str, int, int]]) -> None:
    """Mô phỏng ĐÚNG `_replace_children` (phieu_tinh_gia.py) khi user bấm Tính giá: THÊM thanh_phan
    mới (chiếm id cao hơn) RỒI xóa cũ → id thật sự ĐỔI (giống Postgres prod, không tái dùng id)."""
    db = SessionLocal()
    try:
        old = db.query(PhieuThanhPhan).filter(PhieuThanhPhan.phieu_id == pid).all()
        for i, (ten, sl, von) in enumerate(products):
            db.add(PhieuThanhPhan(phieu_id=pid, thu_tu=i, ten=ten, so_luong=sl,
                                  gia_von_tp=von, loai_thanh_phan="to_roi"))
        db.flush()
        for t in old:
            db.delete(t)
        db.commit()
    finally:
        db.close()


def test_resync_draft_updates_in_place(client):
    token = _token(client)
    pid = _seed_ptg(products=[("Ruột", 5_000, 8_000_000)])
    q = client.post("/api/quotations", json={"phieu_tinh_gia_id": pid}, headers=_h(token)).json()
    # Tính lại PTG: giá vốn 8tr→12tr, SL 5.000→7.000.
    _edit_ptg_first_product(pid, gia_von_tp=12_000_000, so_luong=7_000)
    r = client.post(f"/api/quotations/resync-from-ptg/{pid}", headers=_h(token))
    assert r.status_code == 200, r.text
    assert r.json()["mode"] == "draft_synced"
    assert r.json()["quote_id"] == q["id"]
    assert _version_count(q["id"]) == 1          # KHÔNG đẻ phiên bản
    d = client.get(f"/api/quotations/{q['id']}", headers=_h(token)).json()
    it = d["items"][0]
    assert it["total_cost_snapshot"] == 12_000_000    # giá vốn mới
    assert it["quantity"] == 7_000                     # SL mới
    assert round(it["selling_price"]) == 15_000_000    # 12tr / (1-0.20)


def test_resync_preserves_user_margin_on_draft(client):
    token = _token(client)
    pid = _seed_ptg(products=[("Ruột", 5_000, 8_000_000)])
    q = client.post("/api/quotations", json={"phieu_tinh_gia_id": pid}, headers=_h(token)).json()
    item_id = q["items"][0]["id"]
    # Sales đặt markup riêng 40%.
    client.put(f"/api/quotations/{q['id']}",
               json={"items": [{"id": item_id, "margin_percent": 40}]}, headers=_h(token))
    _edit_ptg_first_product(pid, gia_von_tp=12_000_000, so_luong=5_000)
    r = client.post(f"/api/quotations/resync-from-ptg/{pid}", headers=_h(token))
    assert r.status_code == 200, r.text
    it = client.get(f"/api/quotations/{q['id']}", headers=_h(token)).json()["items"][0]
    assert it["total_cost_snapshot"] == 12_000_000
    assert round(it["margin_percent"]) == 40           # GIỮ markup người dùng
    assert round(it["selling_price"]) == 20_000_000    # 12tr / (1-0.40)


def test_resync_preserves_margin_across_tp_recreate(client):
    """Bấm Tính giá lại tạo thanh_phan id MỚI (prod không tái dùng id). Markup phải GIỮ theo VỊ TRÍ
    dòng — regression cho bug 'giữ theo phieu_thanh_phan_id → mất markup trên Postgres'."""
    token = _token(client)
    pid = _seed_ptg(products=[("Ruột", 5_000, 8_000_000)])
    q = client.post("/api/quotations", json={"phieu_tinh_gia_id": pid}, headers=_h(token)).json()
    item_id = q["items"][0]["id"]
    client.put(f"/api/quotations/{q['id']}",
               json={"items": [{"id": item_id, "margin_percent": 40}]}, headers=_h(token))
    old_tp = _first_tp_id(pid)
    _replace_ptg_products(pid, [("Ruột", 5_000, 12_000_000)])   # id đổi + giá vốn mới
    assert _first_tp_id(pid) != old_tp                           # xác nhận id THẬT SỰ đổi
    r = client.post(f"/api/quotations/resync-from-ptg/{pid}", headers=_h(token))
    assert r.status_code == 200, r.text
    it = client.get(f"/api/quotations/{q['id']}", headers=_h(token)).json()["items"][0]
    assert round(it["margin_percent"]) == 40                     # GIỮ markup dù tp_id đổi
    assert it["total_cost_snapshot"] == 12_000_000
    assert round(it["selling_price"]) == 20_000_000              # 12tr / (1-0.40)


def test_resync_committed_creates_new_version(client):
    token = _token(client)
    pid = _seed_ptg(products=[("Ruột", 5_000, 8_000_000)])
    q = client.post("/api/quotations", json={"phieu_tinh_gia_id": pid}, headers=_h(token)).json()
    # Chốt = gửi khách (sent).
    sent = client.post(f"/api/quotations/{q['id']}/transition",
                       json={"to_status": "sent"}, headers=_h(token))
    assert sent.status_code == 200, sent.text
    _edit_ptg_first_product(pid, gia_von_tp=12_000_000, so_luong=5_000)
    r = client.post(f"/api/quotations/resync-from-ptg/{pid}", headers=_h(token))
    assert r.status_code == 200, r.text
    assert r.json()["mode"] == "new_version"
    assert _version_count(q["id"]) == 2                # ĐẺ phiên bản mới
    d = client.get(f"/api/quotations/{q['id']}", headers=_h(token)).json()
    assert d["status"] == "draft"                      # về nháp để chỉnh
    assert d["items"][0]["total_cost_snapshot"] == 12_000_000


def test_resync_no_active_quote_conflict(client):
    token = _token(client)
    pid = _seed_ptg()
    # PTG chưa có báo giá đang hiệu lực → 409 (màn PTG sẽ đi đường tạo mới).
    r = client.post(f"/api/quotations/resync-from-ptg/{pid}", headers=_h(token))
    assert r.status_code == 409
