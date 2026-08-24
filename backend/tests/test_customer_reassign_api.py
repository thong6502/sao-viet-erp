"""Điều chuyển khách hàng giữa các Sale (trưởng phòng KD) — POST /api/customers/reassign."""
from __future__ import annotations

from app.db import SessionLocal
from app.repositories.customer_repo import CustomerRepository
from app.repositories.rbac_repo import DepartmentRepository, RoleRepository
from app.repositories.user_repo import UserRepository
from app.security import create_access_token, hash_password


def _mk_user(username: str, role_name: str, dept_name: str) -> int:
    db = SessionLocal()
    try:
        users = UserRepository(db)
        u = users.get_by_username(username)
        if u is None:
            dept = DepartmentRepository(db).get_by_name(dept_name)
            role = RoleRepository(db).get_by_name_and_department(role_name, dept.id)
            u = users.create(username=username, name=username, password_hash=hash_password("x"))
            users.set_assignment(
                u, department_id=dept.id, role_id=role.id if role else None, is_active=True
            )
        return u.id
    finally:
        db.close()


def _token(uid: int) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(str(uid))}"}


def _mk_customer(name: str, sale_user_id: int) -> int:
    db = SessionLocal()
    try:
        c = CustomerRepository(db).create(
            name=name,
            tax_code=None,
            phone=None,
            email=None,
            address=None,
            contact_name=None,
            credit_limit=0,
            sale_user_id=sale_user_id,
            status="active",
        )
        return c.id
    finally:
        db.close()


def _owner(customer_id: int) -> int | None:
    db = SessionLocal()
    try:
        return CustomerRepository(db).get_by_id(customer_id).sale_user_id
    finally:
        db.close()


def test_tpkd_reassigns_all_customers_of_a_sale(client):
    tp = _mk_user("t-tpkd", "Trưởng phòng KD", "Kinh doanh")
    s1 = _mk_user("t-sale1", "NV Sales", "Kinh doanh")
    s2 = _mk_user("t-sale2", "NV Sales", "Kinh doanh")
    c1 = _mk_customer("KH X", s1)
    c2 = _mk_customer("KH Y", s1)

    r = client.post(
        "/api/customers/reassign",
        json={"from_sale_user_id": s1, "to_sale_user_id": s2},
        headers=_token(tp),
    )
    assert r.status_code == 200, r.text
    assert r.json()["moved"] == 2
    assert _owner(c1) == s2
    assert _owner(c2) == s2


def test_nv_sales_cannot_reassign(client):
    s1 = _mk_user("t-sale1", "NV Sales", "Kinh doanh")
    s2 = _mk_user("t-sale2", "NV Sales", "Kinh doanh")
    _mk_customer("KH X", s1)
    # NV Sales has khach_hang scope=own → forbidden.
    r = client.post(
        "/api/customers/reassign",
        json={"from_sale_user_id": s1, "to_sale_user_id": s2},
        headers=_token(s1),
    )
    assert r.status_code == 403


def test_admin_reassigns_across_departments(client):
    admin = _mk_user("admin", "Giám đốc", "Ban giám đốc")  # already exists; returns id
    s1 = _mk_user("t-sale1", "NV Sales", "Kinh doanh")
    c1 = _mk_customer("KH X", s1)
    # Admin (scope all) may reassign to anyone, e.g. the admin themselves.
    r = client.post(
        "/api/customers/reassign",
        json={"from_sale_user_id": s1, "to_sale_user_id": admin},
        headers=_token(admin),
    )
    assert r.status_code == 200
    assert r.json()["moved"] == 1
    assert _owner(c1) == admin


def test_reassign_same_source_and_target_rejected(client):
    tp = _mk_user("t-tpkd", "Trưởng phòng KD", "Kinh doanh")
    s1 = _mk_user("t-sale1", "NV Sales", "Kinh doanh")
    r = client.post(
        "/api/customers/reassign",
        json={"from_sale_user_id": s1, "to_sale_user_id": s1},
        headers=_token(tp),
    )
    assert r.status_code == 422


def test_reassign_selected_customers(client):
    tp = _mk_user("t-tpkd", "Trưởng phòng KD", "Kinh doanh")
    s1 = _mk_user("t-sale1", "NV Sales", "Kinh doanh")
    s2 = _mk_user("t-sale2", "NV Sales", "Kinh doanh")
    c1 = _mk_customer("KH X", s1)
    c2 = _mk_customer("KH Y", s1)
    c3 = _mk_customer("KH Z", s1)
    r = client.post(
        "/api/customers/reassign",
        json={"customer_ids": [c1, c3], "to_sale_user_id": s2},
        headers=_token(tp),
    )
    assert r.status_code == 200, r.text
    assert r.json()["moved"] == 2
    assert _owner(c1) == s2
    assert _owner(c2) == s1  # not selected → untouched
    assert _owner(c3) == s2


def test_reassign_selected_skips_out_of_scope(client):
    tp = _mk_user("t-tpkd", "Trưởng phòng KD", "Kinh doanh")
    s1 = _mk_user("t-sale1", "NV Sales", "Kinh doanh")
    s2 = _mk_user("t-sale2", "NV Sales", "Kinh doanh")
    outsider = _mk_user("t-hcns", "Nhân viên", "Hành chính nhân sự")
    c_in = _mk_customer("KH in", s1)
    c_out = _mk_customer("KH out", outsider)
    r = client.post(
        "/api/customers/reassign",
        json={"customer_ids": [c_in, c_out], "to_sale_user_id": s2},
        headers=_token(tp),
    )
    assert r.status_code == 200
    body = r.json()
    assert body["moved"] == 1
    assert body["skipped"] == 1
    assert _owner(c_in) == s2
    assert _owner(c_out) == outsider  # outside KD scope → untouched


def test_reassign_writes_per_customer_audit(client):
    tp = _mk_user("t-tpkd", "Trưởng phòng KD", "Kinh doanh")
    s1 = _mk_user("t-sale1", "NV Sales", "Kinh doanh")
    s2 = _mk_user("t-sale2", "NV Sales", "Kinh doanh")
    c1 = _mk_customer("KH X", s1)
    client.post(
        "/api/customers/reassign",
        json={"customer_ids": [c1], "to_sale_user_id": s2},
        headers=_token(tp),
    )
    audit = client.get(f"/api/customers/{c1}/audit", headers=_token(tp)).json()
    assert any(it["action"] == "reassign_customer" for it in audit["items"])
    assert any(it["title"] == "Điều chuyển phụ trách" for it in audit["items"])


def test_export_default_on_for_read_users(client):
    # Xuất file MẶC ĐỊNH BẬT (24/08/2026): chỉ cần quyền Xem khách là tải được lịch sử mua của
    # khách trong tầm nhìn — công tắc chi tiết `export` đã gỡ khỏi ma trận phân quyền.
    s1 = _mk_user("t-sale1", "NV Sales", "Kinh doanh")
    c1 = _mk_customer("KH X", s1)
    assert client.get(f"/api/customers/{c1}/orders.csv", headers=_token(s1)).status_code == 200
    # Trưởng phòng KD cũng tải được (khách trong phòng).
    tp = _mk_user("t-tpkd", "Trưởng phòng KD", "Kinh doanh")
    assert client.get(f"/api/customers/{c1}/orders.csv", headers=_token(tp)).status_code == 200


def test_reassign_gated_by_reassign_not_update(client):
    # NV Sales CÓ quyền Sửa khách (update) nhưng KHÔNG có `reassign` → điều chuyển bị 403,
    # chứng minh reassign đã tách khỏi update (Cách B).
    s1 = _mk_user("t-sale1", "NV Sales", "Kinh doanh")
    s2 = _mk_user("t-sale2", "NV Sales", "Kinh doanh")
    _mk_customer("KH X", s1)
    r = client.post(
        "/api/customers/reassign",
        json={"from_sale_user_id": s1, "to_sale_user_id": s2},
        headers=_token(s1),
    )
    assert r.status_code == 403


def test_tpkd_cannot_target_other_department(client):
    tp = _mk_user("t-tpkd", "Trưởng phòng KD", "Kinh doanh")
    s1 = _mk_user("t-sale1", "NV Sales", "Kinh doanh")
    outsider = _mk_user("t-hcns", "Nhân viên", "Hành chính nhân sự")
    _mk_customer("KH X", s1)
    r = client.post(
        "/api/customers/reassign",
        json={"from_sale_user_id": s1, "to_sale_user_id": outsider},
        headers=_token(tp),
    )
    assert r.status_code == 400
