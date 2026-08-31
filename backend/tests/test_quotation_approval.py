"""BG-2 — GĐ duyệt "báo giá đặc thù" + đơn hàng "tự thông".

Báo giá đặc thù (giá trị cao ≥100tr…) → chặn "gửi khách"/"khách duyệt" tới khi được duyệt; sales bình
thường gửi thẳng. Đơn hàng tạo từ báo giá đã duyệt → A2 TỰ THÔNG (không hỏi duyệt lại). RBAC (cập nhật
sau P7): NV Sales soạn + tự TRÌNH DUYỆT (có manage_status) + thấy số biên; DUYỆT đặc thù = TP KD HOẶC
Giám đốc Kinh doanh (approve_exception); NV Sales không được duyệt.

Cổng theo RÀO CỦA KHÁCH soi trục **MARKUP** (lợi nhuận / GIÁ VỐN — đúng ô "Markup %" Sale gõ),
KHÔNG phải biên trên giá bán (chủ đầu tư chốt 29/08/2026).
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
    # giá vốn 1 tỷ, markup 20% → giá bán (subtotal) 1.2 tỷ ≥ 1 tỷ → "giá trị đơn cao".
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


def test_gd_approve_then_sale_sends(client):
    """TÁCH duyệt/gửi (chủ đầu tư chốt): GĐ DUYỆT → 'Đã duyệt' (approved, CHƯA gửi); SALE tự
    'Gửi khách' → 'Đã gửi khách' (sent)."""
    token = _token(client)
    q = _make_high_value_quote(client, token)
    # Sales TRÌNH DUYỆT: draft → Chờ duyệt (pending_approval).
    rs = client.post(f"/api/quotations/{q['id']}/transition",
                     json={"to_status": "pending_approval"}, headers=_h(token))
    assert rs.status_code == 200, rs.text
    assert rs.json()["status"] == "pending_approval"
    # GĐ Kinh doanh DUYỆT → "Đã duyệt" (approved) — CHƯA gửi khách.
    r = client.post(f"/api/quotations/{q['id']}/approval",
                    json={"decision": "approved", "note": "khách lớn"}, headers=_h(token))
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "approved"
    assert r.json()["exception_status"] == "approved"
    assert r.json()["exception_cleared"] is True
    # SALE tự Gửi khách: approved → sent.
    rsend = client.post(f"/api/quotations/{q['id']}/transition",
                        json={"to_status": "sent"}, headers=_h(token))
    assert rsend.status_code == 200, rsend.text
    assert rsend.json()["status"] == "sent"


def test_gd_reject_blocks_send(client):
    token = _token(client)
    q = _make_high_value_quote(client, token)
    client.post(f"/api/quotations/{q['id']}/transition",
                json={"to_status": "pending_approval"}, headers=_h(token))
    # GĐ Kinh doanh TỪ CHỐI duyệt → báo giá "Bị từ chối" (rejected) + ghi lý do; sale tạo phiên bản mới.
    r = client.post(f"/api/quotations/{q['id']}/approval",
                    json={"decision": "rejected", "note": "giá quá cao"}, headers=_h(token))
    assert r.status_code == 200
    assert r.json()["status"] == "rejected"
    assert r.json()["exception_decision"] == "rejected"
    # Gửi khách bị chặn (từ 'rejected' không gửi thẳng — phải Tạo phiên bản mới rồi trình/gửi lại).
    r2 = client.post(f"/api/quotations/{q['id']}/transition", json={"to_status": "sent"}, headers=_h(token))
    assert r2.status_code == 409
    # Tạo phiên bản mới hợp lệ từ 'rejected'.
    r3 = client.post(f"/api/quotations/{q['id']}/requote",
                     json={"change_reason": "sửa theo góp ý GĐ"}, headers=_h(token))
    assert r3.status_code == 201, r3.text
    assert r3.json()["version"] == 2


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
    assert r.json()["status"] == "approved"   # tách duyệt/gửi: duyệt xong = "Đã duyệt", chưa gửi


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
    assert r.json()["status"] == "approved"   # tách duyệt/gửi


def test_sales_can_submit_own_quote_for_approval(client):
    """NV Sales tự soạn báo giá đặc thù + tự TRÌNH DUYỆT (có manage_status), NHƯNG không tự duyệt."""
    _token(client)  # đảm bảo roles đã seed
    sales = _role_token("nv_sales_submit", "NV Sales")
    pid = _seed_ptg(gia_von_tp=1_000_000_000)  # giá bán 1.25 tỷ → đặc thù (giá trị cao)
    q = client.post("/api/quotations", json={"phieu_tinh_gia_id": pid}, headers=_h(sales)).json()
    assert q["exception_required"] is True
    # NV Sales tự set biên khi soạn → thấy số biên (không còn giấu).
    assert q["markup_pct"] is not None
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


def test_pending_approval_count_scoped(client):
    """Badge nav: người CÓ quyền duyệt thấy số 'chờ tôi duyệt'; NV Sales (không quyền) = 0."""
    admin = _token(client)  # GĐ: approve_exception, scope all
    q = _make_high_value_quote(client, admin)
    client.post(f"/api/quotations/{q['id']}/transition",
                json={"to_status": "pending_approval"}, headers=_h(admin))
    c = client.get("/api/quotations/pending-approval-count", headers=_h(admin))
    assert c.status_code == 200 and c.json()["count"] >= 1
    # Tab "Chờ duyệt" đọc từ stats.pending_approval.
    assert client.get("/api/quotations/stats", headers=_h(admin)).json()["pending_approval"] >= 1
    sales = _role_token("nv_sales_count", "NV Sales")
    c2 = client.get("/api/quotations/pending-approval-count", headers=_h(sales))
    assert c2.status_code == 200 and c2.json()["count"] == 0   # không quyền duyệt → 0


def test_detail_shows_salesperson_and_approver(client):
    """Người duyệt biết báo giá của NV nào; sau khi duyệt, NV biết AI đã duyệt + khi nào."""
    _token(client)  # seed roles
    sales = _role_token("nv_sales_names", "NV Sales")
    admin = _token(client)
    pid = _seed_ptg(gia_von_tp=1_000_000_000)
    q = client.post("/api/quotations", json={"phieu_tinh_gia_id": pid}, headers=_h(sales)).json()
    d0 = client.get(f"/api/quotations/{q['id']}", headers=_h(admin)).json()
    assert d0["salesperson_name"] == "nv_sales_names"          # người duyệt thấy NV soạn
    client.post(f"/api/quotations/{q['id']}/transition",
                json={"to_status": "pending_approval"}, headers=_h(sales))
    client.post(f"/api/quotations/{q['id']}/approval",
                json={"decision": "approved", "note": "OK"}, headers=_h(admin))
    d = client.get(f"/api/quotations/{q['id']}", headers=_h(sales)).json()
    assert d["exception_decision"] == "approved"
    assert d["exception_decided_by_name"] == "Admin"           # NV biết ai duyệt
    assert d["exception_decided_at"] is not None


def test_double_approval_locked(client):
    """1 người đã duyệt → rời 'Chờ duyệt' → người thứ 2 KHÔNG duyệt lại (chống duyệt trùng)."""
    admin = _token(client)
    gdkd = _role_token("gdkd_double", "Giám đốc Kinh doanh")
    q = _make_high_value_quote(client, admin)
    client.post(f"/api/quotations/{q['id']}/transition",
                json={"to_status": "pending_approval"}, headers=_h(admin))
    r1 = client.post(f"/api/quotations/{q['id']}/approval",
                     json={"decision": "approved", "note": "duyet 1"}, headers=_h(admin))
    assert r1.status_code == 200 and r1.json()["status"] == "approved"
    r2 = client.post(f"/api/quotations/{q['id']}/approval",
                     json={"decision": "approved", "note": "duyet 2"}, headers=_h(gdkd))
    assert r2.status_code == 422 and "Chờ duyệt" in r2.json()["detail"]


def test_gd_sees_markup_number(client):
    token = _token(client)
    q = _make_high_value_quote(client, token)
    # GĐ có approve_exception → thấy số markup.
    assert q["markup_pct"] is not None
    assert {e["key"] for e in q["exceptions"]} == {"high_value"}


# --- cổng theo RÀO CỦA KHÁCH: trục MARKUP (không phải biên) -------------------

def _customer_with_markup_bounds(client, token, *, name: str, mmin=None, mmax=None) -> int:
    cid = client.post("/api/customers", json={"name": name}, headers=_h(token)).json()["customer"]["id"]
    r = client.put(f"/api/customers/{cid}/financial",
                   json={"credit_limit": 0, "markup_min_pct": mmin, "markup_max_pct": mmax},
                   headers=_h(token))
    assert r.status_code == 200, r.text
    return cid


def _quote(client, token, *, customer_id: int, markup: float, cost=10_000_000) -> dict:
    pid = _seed_ptg(gia_von_tp=cost)
    r = client.post("/api/quotations",
                    json={"phieu_tinh_gia_id": pid, "customer_id": customer_id, "margin_percent": markup},
                    headers=_h(token))
    assert r.status_code == 201, r.text
    return r.json()


def test_markup_bang_dung_san_thi_khong_dac_thu(client):
    """Rào khách 10–20%: Sale gõ Markup 10% → ĐẠT, KHÔNG phải trình duyệt.
    (Trục biên cũ sẽ ra 9,1% và bắt trình duyệt oan — đây là ca chốt của lần sửa này.)"""
    token = _token(client)
    cid = _customer_with_markup_bounds(client, token, name="KH Rào Markup", mmin=10, mmax=20)
    q = _quote(client, token, customer_id=cid, markup=10)
    assert q["markup_pct"] == 10
    assert q["exception_required"] is False
    assert q["exceptions"] == []


def test_markup_duoi_san_va_vuot_tran_deu_dac_thu(client):
    token = _token(client)
    cid = _customer_with_markup_bounds(client, token, name="KH Rào 2 Chiều", mmin=10, mmax=20)
    duoi = _quote(client, token, customer_id=cid, markup=9)
    assert duoi["markup_pct"] == 9
    assert duoi["exception_required"] is True
    assert {e["key"] for e in duoi["exceptions"]} == {"markup_out"}
    tren = _quote(client, token, customer_id=cid, markup=25)
    assert tren["markup_pct"] == 25
    assert {e["key"] for e in tren["exceptions"]} == {"markup_out"}
    # Trần đúng bằng 20% → vẫn ĐẠT (biên giới tính vào trong khoảng).
    dung_tran = _quote(client, token, customer_id=cid, markup=20)
    assert dung_tran["exception_required"] is False


def test_khach_chua_dat_rao_thi_khong_soi_markup(client):
    token = _token(client)
    cid = _customer_with_markup_bounds(client, token, name="KH Không Rào")
    q = _quote(client, token, customer_id=cid, markup=3)
    assert q["markup_pct"] == 3
    assert q["exception_required"] is False


def test_ha_markup_sau_khi_duyet_thi_het_bao_phu(client):
    """Báo giá đã duyệt MỞ LẠI được qua "đồng bộ từ phiếu tính giá" (→ về Nháp, bản duyệt cũ còn
    nguyên). Hạ markup 9% → 2% thì bản duyệt cũ KHÔNG còn bao phủ: trạng thái phải là `stale`
    ("đã đổi so với lần duyệt trước"), không được hiện "đã duyệt" chỉ vì tổng tiền giảm.

    Gửi khách vốn đã bị chặn ở tầng khác (`exception_required`) — test này giữ cho BẢNG BÁO nói
    đúng sự thật, chứ không phải chặn thay."""
    token = _token(client)
    cid = _customer_with_markup_bounds(client, token, name="KH Bao Phu", mmin=10, mmax=20)
    pid = _seed_ptg(gia_von_tp=10_000_000)
    qid = client.post("/api/quotations",
                      json={"phieu_tinh_gia_id": pid, "customer_id": cid, "margin_percent": 9},
                      headers=_h(token)).json()["id"]
    client.post(f"/api/quotations/{qid}/transition",
                json={"to_status": "pending_approval"}, headers=_h(token))
    r = client.post(f"/api/quotations/{qid}/approval",
                    json={"decision": "approved", "note": "khách quen"}, headers=_h(token))
    assert r.status_code == 200 and r.json()["exception_status"] == "approved"
    # Sửa thẳng khi ĐÃ DUYỆT: KHÓA (chỉ sửa được ở Nháp).
    assert client.put(f"/api/quotations/{qid}", json={"customer_id": cid, "items": []},
                      headers=_h(token)).status_code == 409
    # Đồng bộ lại từ phiếu tính giá → đẻ phiên bản mới, báo giá về Nháp (markup giữ nguyên 9%).
    assert client.post(f"/api/quotations/resync-from-ptg/{pid}", headers=_h(token)).status_code == 200
    d = client.get(f"/api/quotations/{qid}", headers=_h(token)).json()
    assert d["status"] == "draft" and d["markup_pct"] == 9
    assert d["exception_status"] == "approved"      # chưa đổi gì → bản duyệt cũ còn bao phủ
    # HẠ markup 9% → 2%: tổng tiền GIẢM (qua được cap quy mô) nhưng lợi nhuận tụt.
    it = d["items"][0]
    assert client.put(f"/api/quotations/{qid}",
                      json={"customer_id": cid,
                            "items": [{"id": it["id"], "margin_percent": 2.0, "vat_percent": 10.0}]},
                      headers=_h(token)).status_code == 200
    d2 = client.get(f"/api/quotations/{qid}", headers=_h(token)).json()
    assert d2["markup_pct"] == 2
    assert d2["exception_status"] == "stale"
    assert d2["exception_cleared"] is False
