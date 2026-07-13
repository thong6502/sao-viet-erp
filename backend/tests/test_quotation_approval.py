"""BG-2 — GĐ duyệt "báo giá đặc thù" + đơn hàng "tự thông".

Báo giá đặc thù (giá trị cao ≥100tr…) → chặn "gửi khách"/"khách duyệt" tới khi GĐ duyệt; sales bình
thường gửi thẳng. Đơn hàng tạo từ báo giá đã GĐ duyệt → A2 TỰ THÔNG (không hỏi duyệt lại). RBAC: chỉ
GĐ duyệt; Sales không thấy số biên.
"""
from __future__ import annotations

from app.db import SessionLocal
from app.models.phieu_tinh_gia import PhieuThanhPhan, PhieuTinhGia
from app.repositories.rbac_repo import DepartmentRepository, RoleRepository
from app.repositories.user_repo import UserRepository
from app.security import create_access_token, hash_password

ADMIN = {"username": "admin", "password": "admin123"}   # GĐ: có approve_exception trên bao_gia + don_hang_ban


def _token(client) -> str:
    return client.post("/api/auth/login", json=ADMIN).json()["access_token"]


def _h(t: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {t}"}


def _role_token(username: str, role_name: str, dept="Kinh doanh") -> str:
    db = SessionLocal()
    try:
        users = UserRepository(db)
        ex = users.get_by_username(username)
        if ex is not None:
            return create_access_token(str(ex.id))
        d = DepartmentRepository(db).get_by_name(dept)
        role = RoleRepository(db).get_by_name_and_department(role_name, d.id)
        u = users.create(username=username, name=username, password_hash=hash_password("x"))
        users.set_assignment(u, department_id=d.id, role_id=role.id, is_active=True)
        return create_access_token(str(u.id))
    finally:
        db.close()


def _seed_ptg(*, gia_von_tp: int, so_luong=1_000) -> int:
    db = SessionLocal()
    try:
        n = db.query(PhieuTinhGia).count() + 1
        p = PhieuTinhGia(ma=f"PTG-BG2-{n:04d}", ten_san_pham="SP đặc thù", so_luong=so_luong,
                         tong_gia_von=gia_von_tp, gia_von_don=0, ktv="KTV")
        db.add(p)
        db.flush()
        db.add(PhieuThanhPhan(phieu_id=p.id, thu_tu=0, ten="SP", so_luong=so_luong,
                              gia_von_tp=gia_von_tp, loai_thanh_phan="to_roi"))
        db.commit()
        return p.id
    finally:
        db.close()


def _make_high_value_quote(client, token) -> dict:
    # giá vốn 100tr, markup 20% → giá bán (subtotal) 125tr ≥ 100tr → "giá trị đơn cao".
    pid = _seed_ptg(gia_von_tp=100_000_000)
    return client.post("/api/quotations", json={"phieu_tinh_gia_id": pid}, headers=_h(token)).json()


# --- cổng đặc thù chặn gửi khách + chặn cả đường tắt draft→accepted -----------

def test_high_value_quote_requires_gd_and_blocks_send(client):
    token = _token(client)
    q = _make_high_value_quote(client, token)
    assert q["exception_required"] is True
    assert q["exception_status"] == "pending"
    assert {e["key"] for e in q["exceptions"]} == {"high_value"}
    # Gửi khách bị chặn (chưa GĐ duyệt).
    r = client.post(f"/api/quotations/{q['id']}/transition", json={"to_status": "sent"}, headers=_h(token))
    assert r.status_code == 422
    assert "Giám đốc" in r.json()["detail"]
    # Đường tắt draft→accepted cũng bị chặn (không lách được).
    r2 = client.post(f"/api/quotations/{q['id']}/transition", json={"to_status": "accepted"}, headers=_h(token))
    assert r2.status_code == 422


def test_gd_approve_unlocks_send(client):
    token = _token(client)
    q = _make_high_value_quote(client, token)
    r = client.post(f"/api/quotations/{q['id']}/approval",
                    json={"decision": "approved", "note": "khách lớn"}, headers=_h(token))
    assert r.status_code == 200, r.text
    assert r.json()["exception_status"] == "approved"
    assert r.json()["exception_cleared"] is True
    # Giờ gửi khách được.
    r2 = client.post(f"/api/quotations/{q['id']}/transition", json={"to_status": "sent"}, headers=_h(token))
    assert r2.status_code == 200
    assert r2.json()["status"] == "sent"


def test_gd_reject_blocks_send(client):
    token = _token(client)
    q = _make_high_value_quote(client, token)
    r = client.post(f"/api/quotations/{q['id']}/approval",
                    json={"decision": "rejected", "note": "giá quá cao"}, headers=_h(token))
    assert r.status_code == 200 and r.json()["exception_status"] == "rejected"
    r2 = client.post(f"/api/quotations/{q['id']}/transition", json={"to_status": "sent"}, headers=_h(token))
    assert r2.status_code == 422


def test_approve_rejects_non_exceptional(client):
    token = _token(client)
    # giá vốn 1tr → giá bán 1.25tr, biên 20%, không giá trị cao → không đặc thù.
    pid = _seed_ptg(gia_von_tp=1_000_000)
    q = client.post("/api/quotations", json={"phieu_tinh_gia_id": pid}, headers=_h(token)).json()
    assert q["exception_required"] is False
    r = client.post(f"/api/quotations/{q['id']}/approval", json={"decision": "approved"}, headers=_h(token))
    assert r.status_code == 422
    assert "đặc thù" in r.json()["detail"].lower()


# --- RBAC + không rò số ------------------------------------------------------

def test_sales_cannot_approve_quote(client):
    _token(client)
    sales = _role_token("nv_sales_bg2", "NV Sales")
    admin = _token(client)
    q = _make_high_value_quote(client, admin)
    r = client.post(f"/api/quotations/{q['id']}/approval", json={"decision": "approved"}, headers=_h(sales))
    assert r.status_code == 403


def test_gd_sees_margin_number(client):
    token = _token(client)
    q = _make_high_value_quote(client, token)
    # GĐ có approve_exception → thấy số biên.
    assert q["margin_pct"] is not None
    assert {e["key"] for e in q["exceptions"]} == {"high_value"}


# --- đơn hàng TỰ THÔNG từ báo giá đã duyệt -----------------------------------

def test_order_auto_clears_from_approved_quote(client):
    token = _token(client)
    q = _make_high_value_quote(client, token)
    # GĐ duyệt → gửi khách → khách duyệt (accepted).
    client.post(f"/api/quotations/{q['id']}/approval", json={"decision": "approved"}, headers=_h(token))
    client.post(f"/api/quotations/{q['id']}/transition", json={"to_status": "sent"}, headers=_h(token))
    ra = client.post(f"/api/quotations/{q['id']}/transition", json={"to_status": "accepted"}, headers=_h(token))
    assert ra.status_code == 200, ra.text
    # Tạo đơn từ báo giá đã duyệt.
    body = {"quotation_id": q["id"], "order_type": "theo_yc", "order_kind": "moi",
            "parent_order_id": None, "has_customer_paper": False, "vat_pct_estimate": 8}
    o = client.post("/api/orders", json=body, headers=_h(token))
    assert o.status_code == 201, o.text
    gate = o.json()["gate"]
    # Đơn vẫn thuộc diện đặc thù (giá trị cao) NHƯNG TỰ THÔNG (không hỏi GĐ lại).
    assert gate["exception_required"] is True
    assert gate["exception_cleared"] is True
    assert gate["exception_status"] == "approved"
