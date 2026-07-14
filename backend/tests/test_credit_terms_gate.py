"""Quyền chi tiết `set_credit_terms` — CHÍNH SÁCH TÀI CHÍNH khách (redesign spec-06 v2).

Chính sách tài chính (hạn mức công nợ + điều khoản thanh toán + rào chiết khấu/biên min–max)
sửa qua endpoint RIÊNG `PUT /api/customers/{id}/financial`, gate `set_credit_terms`. KHÔNG có
bước duyệt. Form Thêm/Sửa (định danh) KHÔNG đụng tài chính. Ai cũng XEM (cho xem hết); chỉ
người có quyền mới SỬA (thiếu → 403). Chạy trên in-memory DB nên không đụng dữ liệu thật.
"""
from __future__ import annotations

from app.db import SessionLocal
from app.repositories.rbac_repo import DepartmentRepository, RoleRepository
from app.repositories.user_repo import UserRepository
from app.security import create_access_token, hash_password

ADMIN = {"username": "admin", "password": "admin123"}  # Giám đốc → _full (có quyền)


def _h(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _admin_token(client) -> str:
    return client.post("/api/auth/login", json=ADMIN).json()["access_token"]


def _role_token(username: str, role_name: str, dept_name: str = "Kinh doanh") -> tuple[str, int]:
    """Tạo (hoặc dùng lại) user với vai trò trong phòng, trả (token, user_id)."""
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


def _kh_capability(client, token: str) -> dict:
    body = client.get("/api/auth/permissions", headers=_h(token)).json()
    return next(p for p in body["permissions"] if p["module_key"] == "khach_hang")


def _create(client, token, **over) -> int:
    r = client.post("/api/customers", json={"name": "KH TC", **over}, headers=_h(token))
    assert r.status_code == 201, r.text
    return r.json()["customer"]["id"]


# --- capability (ai được bật) ------------------------------------------------


def test_manager_has_capability_sale_does_not(client):
    admin = _admin_token(client)
    sale, _ = _role_token("sale1", "NV Sales")
    assert _kh_capability(client, admin)["can_set_credit_terms"] is True
    assert _kh_capability(client, sale)["can_set_credit_terms"] is False


# --- khách MỚI = default tài chính an toàn (form Thêm không đụng tài chính) ---


def test_new_customer_safe_financial_default(client):
    token = _admin_token(client)
    # Form Thêm có gửi kèm financial (extra) cũng KHÔNG được nhận — về default.
    cid = _create(client, token, name="KH Mới", credit_limit=99_000_000)
    c = client.get(f"/api/customers/{cid}", headers=_h(token)).json()["customer"]
    assert c["credit_limit"] == 0
    assert c["discount_max_pct"] is None and c["margin_min_pct"] is None


# --- người CÓ quyền: set thẳng qua /financial, không bước duyệt --------------


def test_manager_can_set_financial(client):
    token = _admin_token(client)
    cid = _create(client, token, name="KH Có Quyền")
    r = client.put(
        f"/api/customers/{cid}/financial",
        json={
            "credit_limit": 30_000_000,
            "discount_min_pct": 0, "discount_max_pct": 10,
            "margin_min_pct": 15, "margin_max_pct": 40,
        },
        headers=_h(token),
    )
    assert r.status_code == 200, r.text
    c = r.json()["customer"]
    assert c["credit_limit"] == 30_000_000
    assert c["discount_max_pct"] == 10 and c["margin_min_pct"] == 15


def test_financial_validation(client):
    token = _admin_token(client)
    cid = _create(client, token, name="KH Validate")
    # chiết khấu min > max → 422.
    r = client.put(f"/api/customers/{cid}/financial", json={
        "credit_limit": 0, "discount_min_pct": 20, "discount_max_pct": 10,
    }, headers=_h(token))
    assert r.status_code == 422
    # biên min > max → 422.
    r = client.put(f"/api/customers/{cid}/financial", json={
        "credit_limit": 0, "margin_min_pct": 40, "margin_max_pct": 15,
    }, headers=_h(token))
    assert r.status_code == 422


# --- người THIẾU quyền: 403 trên /financial, nhưng VẪN xem + sửa định danh ----


def test_sale_forbidden_on_financial_but_can_view_and_edit_identity(client):
    admin = _admin_token(client)
    sale, sale_id = _role_token("sale1", "NV Sales")
    # Quản lý lập khách giao sale1 + đặt rào.
    cid = _create(client, admin, name="KH Của Sale", sale_user_id=sale_id)
    client.put(f"/api/customers/{cid}/financial", json={
        "credit_limit": 50_000_000, "discount_max_pct": 10, "margin_min_pct": 15,
    }, headers=_h(admin))

    sale_token = create_access_token(str(sale_id))
    # Sale SỬA tài chính → 403.
    r = client.put(f"/api/customers/{cid}/financial", json={"credit_limit": 0}, headers=_h(sale_token))
    assert r.status_code == 403

    # Nhưng sale VẪN XEM được (cho xem hết).
    c = client.get(f"/api/customers/{cid}", headers=_h(sale_token)).json()["customer"]
    assert c["credit_limit"] == 50_000_000
    assert c["discount_max_pct"] == 10 and c["margin_min_pct"] == 15

    # Sale SỬA ĐỊNH DANH (đổi tên) được, và KHÔNG đụng tài chính (không bị xóa).
    r = client.put(f"/api/customers/{cid}", json={"name": "KH Của Sale (đổi tên)"}, headers=_h(sale_token))
    assert r.status_code == 200
    after = client.get(f"/api/customers/{cid}", headers=_h(admin)).json()["customer"]
    assert after["name"] == "KH Của Sale (đổi tên)"
    assert after["credit_limit"] == 50_000_000          # tài chính GIỮ NGUYÊN
    assert after["discount_max_pct"] == 10
