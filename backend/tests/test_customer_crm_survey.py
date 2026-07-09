"""CRM đợt khảo sát (câu 7–29) — nhóm A + #12/#14/#26.

Covers: người liên hệ + địa chỉ giao hàng (CRUD, bất biến một primary/default), check
trùng mở rộng MST+tên+email (soft — vẫn tạo), điều khoản thanh toán (#12 validate theo
kiểu mốc), chiết khấu riêng gate quyền `view_discount` (#14 — ẩn số + PUT bị bỏ qua),
khách tiềm năng (lead), import CSV dry-run→commit + export, và scope `department` =
subtree (#26: trưởng phòng cha thấy khách của team con).
"""
from __future__ import annotations

import io

from app.db import SessionLocal
from app.repositories.rbac_repo import DepartmentRepository, RoleRepository
from app.repositories.user_repo import UserRepository
from app.security import create_access_token, hash_password
from app.seed import seed_customers, seed_kd_staff

ADMIN = {"username": "admin", "password": "admin123"}


def _admin_token(client) -> str:
    return client.post("/api/auth/login", json=ADMIN).json()["access_token"]


def _h(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _seed_demo() -> None:
    db = SessionLocal()
    try:
        seed_kd_staff(db)
        seed_customers(db)
    finally:
        db.close()


def _role_token(username: str, role_name: str, dept_name: str = "Kinh doanh") -> str:
    db = SessionLocal()
    try:
        users = UserRepository(db)
        existing = users.get_by_username(username)
        if existing is not None:
            return create_access_token(str(existing.id))
        dept = DepartmentRepository(db).get_by_name(dept_name)
        role = RoleRepository(db).get_by_name_and_department(role_name, dept.id)
        u = users.create(username=username, name=username, password_hash=hash_password("x"))
        users.set_assignment(u, department_id=dept.id, role_id=role.id, is_active=True)
        return create_access_token(str(u.id))
    finally:
        db.close()


def _create(client, token, **over) -> dict:
    payload = {"name": "Công ty TNHH Kiểm Thử", **over}
    resp = client.post("/api/customers", json=payload, headers=_h(token))
    assert resp.status_code == 201, resp.text
    return resp.json()


# --- #12 điều khoản thanh toán ------------------------------------------------


def test_create_with_payment_terms_and_lead_status(client):
    body = _create(
        client, _admin_token(client),
        name="Cty Điều Khoản", status="lead",
        payment_term_type="net_eom", payment_term_days=30,
    )
    c = body["customer"]
    assert c["status"] == "lead"
    assert c["payment_term_type"] == "net_eom"
    assert c["payment_term_days"] == 30
    # Admin (full) thấy chiết khấu (chưa khai → None, không phải 0 giả) + không bị ẩn.
    assert c["discount_hidden"] is False


def test_payment_term_validation(client):
    token = _admin_token(client)
    # prepay thiếu tỷ lệ % → 422.
    r = client.post("/api/customers", json={
        "name": "Cty A", "payment_term_type": "prepay",
    }, headers=_h(token))
    assert r.status_code == 422
    # net_delivery thiếu số ngày → 422.
    r = client.post("/api/customers", json={
        "name": "Cty B", "payment_term_type": "net_delivery",
    }, headers=_h(token))
    assert r.status_code == 422
    # Kiểu mốc lạ → 422.
    r = client.post("/api/customers", json={
        "name": "Cty C", "payment_term_type": "whenever",
    }, headers=_h(token))
    assert r.status_code == 422


# --- #8/#15 check trùng mở rộng -------------------------------------------------


def test_duplicate_name_and_email_soft_warn_still_creates(client):
    token = _admin_token(client)
    _create(client, token, name="Cty Trùng Tên", email="dup@x.vn", tax_code="0101234567")
    # Trùng cả tên lẫn email với khách trên → mỗi khách chỉ báo MỘT lần, theo tiêu chí
    # mạnh nhất (name > email vì không trùng MST) — và VẪN tạo (soft warn, §34).
    body = _create(client, token, name="cty trùng tên", email="DUP@x.vn", tax_code="0107654321")
    fields = [d["field"] for d in body["duplicates"]]
    assert fields == ["name"]
    assert body["customer"]["code"].startswith("KH")

    # Khách thứ ba chỉ trùng email → báo theo email (cả 2 khách trước cùng email đó).
    body3 = _create(client, token, name="Cty Khác Hẳn", email="dup@x.vn")
    assert {d["field"] for d in body3["duplicates"]} == {"email"}
    assert len(body3["duplicates"]) == 2


def test_check_duplicate_endpoint(client):
    token = _admin_token(client)
    created = _create(client, token, name="Cty Check Trùng", tax_code="0101234567")
    r = client.get(
        "/api/customers/check-duplicate",
        params={"tax_code": "0101234567", "name": "khác hẳn"},
        headers=_h(token),
    )
    assert r.status_code == 200
    warns = r.json()
    assert warns and warns[0]["field"] == "tax_code"
    # exclude_id: chính nó không tự báo trùng (form Sửa).
    r = client.get(
        "/api/customers/check-duplicate",
        params={"tax_code": "0101234567", "exclude_id": created["customer"]["id"]},
        headers=_h(token),
    )
    assert r.json() == []


# --- #14 chiết khấu gate quyền ---------------------------------------------------


def test_discount_hidden_and_update_ignored_without_permission(client):
    _seed_demo()
    admin = _admin_token(client)
    body = _create(client, admin, name="Cty Chiết Khấu",
                   discount_trade_pct=10, discount_buyer_pct=2.5)
    cid = body["customer"]["id"]
    assert body["customer"]["discount_trade_pct"] == 10

    # NV Sales không có quyền chi tiết view_discount → số bị ẩn, không phải 0 giả.
    db = SessionLocal()
    try:
        users = UserRepository(db)
        admin_u = users.get_by_username("admin")
        # Gán khách cho sale1 để scope own nhìn thấy.
        sale1 = users.get_by_username("sale1")
    finally:
        db.close()
    client.put(f"/api/customers/{cid}", json={
        "name": "Cty Chiết Khấu", "sale_user_id": sale1.id,
    }, headers=_h(admin))

    sale_token = create_access_token(str(sale1.id))
    detail = client.get(f"/api/customers/{cid}", headers=_h(sale_token)).json()
    assert detail["customer"]["discount_hidden"] is True
    assert detail["customer"]["discount_trade_pct"] is None

    # PUT của sale kèm chiết khấu → bị BỎ QUA (giữ 10/2.5), không phải lỗi.
    r = client.put(f"/api/customers/{cid}", json={
        "name": "Cty Chiết Khấu", "discount_trade_pct": 99, "discount_buyer_pct": 99,
    }, headers=_h(sale_token))
    assert r.status_code == 200
    after = client.get(f"/api/customers/{cid}", headers=_h(admin)).json()
    assert after["customer"]["discount_trade_pct"] == 10
    assert after["customer"]["discount_buyer_pct"] == 2.5


# --- #10/#11 người liên hệ + #9 địa chỉ giao hàng -----------------------------------


def test_contacts_crud_single_primary(client):
    token = _admin_token(client)
    cid = _create(client, token, name="Cty Liên Hệ")["customer"]["id"]

    r1 = client.post(f"/api/customers/{cid}/contacts", json={
        "name": "Chị Lan", "title": "Kế toán", "duty": "Đối chiếu công nợ",
        "phone": "0911", "is_primary": True,
    }, headers=_h(token))
    assert r1.status_code == 201
    r2 = client.post(f"/api/customers/{cid}/contacts", json={
        "name": "Anh Bình", "title": "Mua hàng", "is_primary": True,
    }, headers=_h(token))
    assert r2.status_code == 201

    items = client.get(f"/api/customers/{cid}/contacts", headers=_h(token)).json()["items"]
    assert len(items) == 2
    primaries = [c for c in items if c["is_primary"]]
    # Bất biến: chỉ MỘT liên hệ chính — người sau lấy cờ của người trước.
    assert len(primaries) == 1 and primaries[0]["name"] == "Anh Bình"

    # Sửa + xóa.
    c1 = next(c for c in items if c["name"] == "Chị Lan")
    r = client.put(f"/api/customers/{cid}/contacts/{c1['id']}", json={
        "name": "Chị Lan", "title": "KT trưởng", "is_primary": False,
    }, headers=_h(token))
    assert r.json()["title"] == "KT trưởng"
    assert client.delete(
        f"/api/customers/{cid}/contacts/{c1['id']}", headers=_h(token)
    ).status_code == 204
    items = client.get(f"/api/customers/{cid}/contacts", headers=_h(token)).json()["items"]
    assert len(items) == 1


def test_addresses_crud_single_default(client):
    token = _admin_token(client)
    cid = _create(client, token, name="Cty Địa Chỉ")["customer"]["id"]

    a1 = client.post(f"/api/customers/{cid}/addresses", json={
        "label": "Trụ sở", "address": "Số 1 Hà Nội", "is_default": True,
    }, headers=_h(token))
    assert a1.status_code == 201
    a2 = client.post(f"/api/customers/{cid}/addresses", json={
        "label": "Nhà máy", "address": "KCN Bắc Ninh", "is_default": True,
    }, headers=_h(token))
    assert a2.status_code == 201

    items = client.get(f"/api/customers/{cid}/addresses", headers=_h(token)).json()["items"]
    defaults = [a for a in items if a["is_default"]]
    assert len(items) == 2 and len(defaults) == 1 and defaults[0]["label"] == "Nhà máy"

    # Thiếu label/địa chỉ → 422.
    r = client.post(f"/api/customers/{cid}/addresses", json={
        "label": "X", "address": "  ",
    }, headers=_h(token))
    assert r.status_code == 422


# --- #21 tài liệu đính kèm --------------------------------------------------------


def test_attachment_upload_and_delete(client):
    token = _admin_token(client)
    cid = _create(client, token, name="Cty Tài Liệu")["customer"]["id"]

    r = client.post(
        f"/api/customers/{cid}/attachments",
        files={"file": ("hop-dong.pdf", b"%PDF-fake", "application/pdf")},
        data={"doc_kind": "hop_dong"},
        headers=_h(token),
    )
    assert r.status_code == 201, r.text
    att = r.json()
    assert att["doc_kind"] == "hop_dong"
    assert att["file_url"].startswith(f"/static/crm/{cid}/")

    items = client.get(f"/api/customers/{cid}/attachments", headers=_h(token)).json()["items"]
    assert len(items) == 1
    assert client.delete(
        f"/api/customers/{cid}/attachments/{att['id']}", headers=_h(token)
    ).status_code == 204


# --- #23 import / export -----------------------------------------------------------


_CSV = (
    "Tên khách hàng,MST,Điện thoại,Email,Địa chỉ,Người liên hệ,Hạn mức (VND),Trạng thái\n"
    "Cty Import Một,0101234567,0911,imp1@x.vn,HN,Anh A,100000000,Đang giao dịch\n"
    "Cty Import Hai,,0912,,HCM,,50000000,Tiềm năng\n"
    ",0100000000,,,,,,\n"  # thiếu tên → error
)


def _upload_csv(client, token, dry_run: bool):
    return client.post(
        "/api/customers/import",
        files={"file": ("kh.csv", ("﻿" + _CSV).encode("utf-8"), "text/csv")},
        data={"dry_run": "true" if dry_run else "false"},
        headers=_h(token),
    )


def test_import_dry_run_then_commit(client):
    token = _admin_token(client)
    # Dry-run: báo từng dòng, KHÔNG ghi.
    r = _upload_csv(client, token, dry_run=True)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["dry_run"] is True and body["total"] == 3
    assert body["errors"] == 1 and body["created"] == 0
    before = client.get("/api/customers", headers=_h(token)).json()["total"]

    # Commit: 2 dòng hợp lệ được tạo, dòng lỗi bị bỏ qua.
    r = _upload_csv(client, token, dry_run=False)
    body = r.json()
    assert body["created"] == 2 and body["errors"] == 1
    after = client.get("/api/customers", headers=_h(token)).json()["total"]
    assert after == before + 2
    # Trạng thái tiếng Việt map đúng (Tiềm năng → lead).
    leads = client.get(
        "/api/customers", params={"status": "lead"}, headers=_h(token)
    ).json()
    assert any(c["name"] == "Cty Import Hai" for c in leads["items"])


def test_import_template_and_export(client):
    token = _admin_token(client)
    r = client.get("/api/customers/import-template.csv", headers=_h(token))
    assert r.status_code == 200
    assert "Tên khách hàng" in r.content.decode("utf-8-sig")

    _create(client, token, name="Cty Xuất File", discount_trade_pct=7)
    r = client.get("/api/customers/export.csv", headers=_h(token))
    assert r.status_code == 200
    text = r.content.decode("utf-8-sig")
    # Admin có view_discount → cột chiết khấu xuất hiện kèm số thật.
    assert "CK thương mại (%)" in text and "Cty Xuất File" in text


# --- #26 scope department = subtree -------------------------------------------------


def test_parent_dept_head_sees_child_team_customers(client):
    _seed_demo()
    admin = _admin_token(client)

    # Dựng team con của Kinh doanh + một sale thuộc team sở hữu 1 khách.
    db = SessionLocal()
    try:
        depts = DepartmentRepository(db)
        roles = RoleRepository(db)
        users = UserRepository(db)
        kd = depts.get_by_name("Kinh doanh")
        team = depts.get_by_name("KD - Team 1") or depts.create(
            name="KD - Team 1", parent_id=kd.id
        )
        # Role NV Sales của team (scope own trên khach_hang là đủ cho sale).
        role = roles.get_by_name_and_department("NV Sales", kd.id)
        sale_team = users.get_by_username("sale_team1")
        if sale_team is None:
            sale_team = users.create(
                username="sale_team1", name="Sale Team 1",
                password_hash=hash_password("x"),
            )
        users.set_assignment(
            sale_team, department_id=team.id, role_id=role.id, is_active=True
        )
        sale_team_id = sale_team.id
    finally:
        db.close()

    # Khách của sale team con.
    _create(client, admin, name="Cty Của Team Con", sale_user_id=sale_team_id)

    # TPKD (scope department, thuộc phòng KD CHA) phải thấy khách của team con.
    tp = _role_token("tpkd_subtree", "Trưởng phòng KD")
    names = {c["name"] for c in client.get(
        "/api/customers", params={"size": 200}, headers=_h(tp)
    ).json()["items"]}
    assert "Cty Của Team Con" in names

    # Sale thường (scope own) vẫn không thấy khách của người khác.
    other = _role_token("sale_khac", "NV Sales")
    names_other = {c["name"] for c in client.get(
        "/api/customers", headers=_h(other)
    ).json()["items"]}
    assert "Cty Của Team Con" not in names_other
