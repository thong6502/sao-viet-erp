"""BG-2 — GĐ duyệt "báo giá đặc thù" + đơn hàng "tự thông".

Báo giá đặc thù (giá trị cao ≥100tr…) → chặn "gửi khách"/"khách duyệt" tới khi được duyệt; sales bình
thường gửi thẳng. Đơn hàng tạo từ báo giá đã duyệt → A2 TỰ THÔNG (không hỏi duyệt lại). RBAC (cập nhật
sau P7): NV Sales soạn + tự TRÌNH DUYỆT (có manage_status) + thấy số biên; DUYỆT đặc thù = TP KD HOẶC
Giám đốc Kinh doanh (approve_exception); NV Sales không được duyệt.
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
    # giá vốn 1 tỷ, markup 20% → giá bán (subtotal) 1.25 tỷ ≥ 1 tỷ → "giá trị đơn cao".
    pid = _seed_ptg(gia_von_tp=1_000_000_000)
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
    # Sales TRÌNH DUYỆT: draft → Chờ duyệt (pending_approval).
    rs = client.post(f"/api/quotations/{q['id']}/transition",
                     json={"to_status": "pending_approval"}, headers=_h(token))
    assert rs.status_code == 200, rs.text
    assert rs.json()["status"] == "pending_approval"
    # GĐ Kinh doanh duyệt → báo giá sang "Đã duyệt" (sent, gộp đã-gửi-khách).
    r = client.post(f"/api/quotations/{q['id']}/approval",
                    json={"decision": "approved", "note": "khách lớn"}, headers=_h(token))
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "sent"
    assert r.json()["exception_status"] == "approved"
    assert r.json()["exception_cleared"] is True


def test_gd_reject_blocks_send(client):
    token = _token(client)
    q = _make_high_value_quote(client, token)
    client.post(f"/api/quotations/{q['id']}/transition",
                json={"to_status": "pending_approval"}, headers=_h(token))
    # GĐ Kinh doanh TỪ CHỐI duyệt → quay về Nháp (Q4) + ghi lý do.
    r = client.post(f"/api/quotations/{q['id']}/approval",
                    json={"decision": "rejected", "note": "giá quá cao"}, headers=_h(token))
    assert r.status_code == 200
    assert r.json()["status"] == "draft"
    assert r.json()["exception_status"] == "rejected"
    # Gửi khách vẫn bị chặn (đặc thù — phải trình duyệt lại).
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


def test_giam_doc_kinh_doanh_can_approve(client):
    admin = _token(client)
    gdkd = _role_token("gdkd_bg2", "Giám đốc Kinh doanh")
    q = _make_high_value_quote(client, admin)
    client.post(f"/api/quotations/{q['id']}/transition",
                json={"to_status": "pending_approval"}, headers=_h(admin))
    r = client.post(f"/api/quotations/{q['id']}/approval",
                    json={"decision": "approved", "note": "GĐ KD duyệt"}, headers=_h(gdkd))
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "sent"


def test_truong_phong_kd_can_approve_exception(client):
    _token(client)  # đảm bảo roles đã seed
    # Luồng thật: NV Sales cùng phòng Kinh doanh soạn + trình duyệt; TP KD (scope phòng) duyệt.
    sales = _role_token("sale_for_tpkd", "NV Sales")
    tpkd = _role_token("tpkd_bg2", "Trưởng phòng KD")
    pid = _seed_ptg(gia_von_tp=1_000_000_000)
    q = client.post("/api/quotations", json={"phieu_tinh_gia_id": pid}, headers=_h(sales)).json()
    client.post(f"/api/quotations/{q['id']}/transition",
                json={"to_status": "pending_approval"}, headers=_h(sales))
    # TP KD cũng có approve_exception (cùng GĐ KD) → duyệt được đặc thù (chủ đầu tư chốt sau P7).
    r = client.post(f"/api/quotations/{q['id']}/approval",
                    json={"decision": "approved", "note": "TP KD duyệt"}, headers=_h(tpkd))
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "sent"


def test_sales_can_submit_own_quote_for_approval(client):
    """NV Sales tự soạn báo giá đặc thù + tự TRÌNH DUYỆT (có manage_status), NHƯNG không tự duyệt."""
    _token(client)  # đảm bảo roles đã seed
    sales = _role_token("nv_sales_submit", "NV Sales")
    pid = _seed_ptg(gia_von_tp=1_000_000_000)  # giá bán 1.25 tỷ → đặc thù (giá trị cao)
    q = client.post("/api/quotations", json={"phieu_tinh_gia_id": pid}, headers=_h(sales)).json()
    assert q["exception_required"] is True
    # NV Sales tự set biên khi soạn → thấy số biên (không còn giấu).
    assert q["margin_pct"] is not None
    # Có manage_status → tự Trình duyệt (draft → pending_approval).
    r = client.post(f"/api/quotations/{q['id']}/transition",
                    json={"to_status": "pending_approval"}, headers=_h(sales))
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "pending_approval"
    # Nhưng KHÔNG tự duyệt được (thiếu approve_exception).
    r2 = client.post(f"/api/quotations/{q['id']}/approval",
                     json={"decision": "approved"}, headers=_h(sales))
    assert r2.status_code == 403


def test_sales_can_accept_own_normal_quote(client):
    """NV Sales tự đánh dấu 'Khách hàng đồng ý' cho báo giá THƯỜNG của mình (can_approve, scope own)."""
    _token(client)  # đảm bảo roles đã seed
    sales = _role_token("nv_sales_accept", "NV Sales")
    pid = _seed_ptg(gia_von_tp=1_000_000)  # giá bán 1.25tr → KHÔNG đặc thù
    q = client.post("/api/quotations", json={"phieu_tinh_gia_id": pid}, headers=_h(sales)).json()
    assert q["exception_required"] is False
    # Gửi khách (manage_status) rồi khách chốt (approve) — cả hai đều là quyền của NV Sales.
    client.post(f"/api/quotations/{q['id']}/transition", json={"to_status": "sent"}, headers=_h(sales))
    r = client.post(f"/api/quotations/{q['id']}/transition", json={"to_status": "accepted"}, headers=_h(sales))
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "accepted"


def test_approval_requires_reason(client):
    """Người duyệt đặc thù PHẢI nêu lý do — dù đồng ý hay từ chối (chủ đầu tư chốt sau P8)."""
    admin = _token(client)
    q = _make_high_value_quote(client, admin)
    client.post(f"/api/quotations/{q['id']}/transition",
                json={"to_status": "pending_approval"}, headers=_h(admin))
    # Duyệt mà bỏ trống lý do → 422.
    r = client.post(f"/api/quotations/{q['id']}/approval",
                    json={"decision": "approved"}, headers=_h(admin))
    assert r.status_code == 422
    assert "lý do" in r.json()["detail"].lower()


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
    # Trình duyệt → GĐ Kinh doanh duyệt (→ Đã duyệt/sent) → khách chốt (accepted).
    client.post(f"/api/quotations/{q['id']}/transition", json={"to_status": "pending_approval"}, headers=_h(token))
    client.post(f"/api/quotations/{q['id']}/approval", json={"decision": "approved", "note": "OK khách lớn"}, headers=_h(token))
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
