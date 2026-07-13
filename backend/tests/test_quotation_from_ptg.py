"""BG-1 — Báo giá dựng lại nguồn: 1 Phiếu tính giá (PTG) → 1 Báo giá.

Kiểm: tạo báo giá TỪ 1 PTG (dòng = mỗi sản phẩm PhieuThanhPhan, giá vốn khóa = gia_von_tp, markup mặc
định 20% → giá bán); guard 1 PTG → 1 BG đang hiệu lực (409); endpoint /by-phieu tra báo giá của PTG.
"""
from __future__ import annotations

from app.db import SessionLocal
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
