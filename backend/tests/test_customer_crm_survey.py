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


def test_create_kind_then_set_credit_via_financial(client):
    """Redesign spec-06 v2: create chỉ ĐỊNH DANH (Loại); hạn mức đặt qua /financial riêng.
    (Điều khoản thanh toán đã BỎ theo yêu cầu.)"""
    token = _admin_token(client)
    body = _create(client, token, name="Cty Điều Khoản", customer_kind="cong_ty")
    cid = body["customer"]["id"]
    assert body["customer"]["customer_kind"] == "cong_ty"
    r = client.put(f"/api/customers/{cid}/financial", json={
        "credit_limit": 25_000_000, "discount_max_pct": 8,
    }, headers=_h(token))
    assert r.status_code == 200, r.text
    c = r.json()["customer"]
    assert c["credit_limit"] == 25_000_000
    assert c["discount_max_pct"] == 8


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


# Rào chiết khấu/biên + gate /financial: xem test_credit_terms_gate.py (đầy đủ).


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
    assert att["file_url"].startswith(f"/api/files/crm/{cid}/")

    items = client.get(f"/api/customers/{cid}/attachments", headers=_h(token)).json()["items"]
    assert len(items) == 1
    assert client.delete(
        f"/api/customers/{cid}/attachments/{att['id']}", headers=_h(token)
    ).status_code == 204


# --- #23 import / export -----------------------------------------------------------


_CSV = (
    "Tên khách hàng,Loại,MST,Điện thoại,Email,Địa chỉ,Người liên hệ\n"
    "Cty Import Một,Công ty,0101234567,0911,imp1@x.vn,HN,Anh A\n"
    "Cty Import Hai,Cá nhân,,0912,,HCM,\n"
    ",Công ty,0100000000,,,,\n"  # thiếu tên → error
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
    # Import chỉ nạp ĐỊNH DANH; Loại tiếng Việt map đúng (Cá nhân → ca_nhan).
    listing = client.get("/api/customers?size=200", headers=_h(token)).json()
    hai = next((c for c in listing["items"] if c["name"] == "Cty Import Hai"), None)
    assert hai is not None and hai["customer_kind"] == "ca_nhan"


def test_import_template_and_export(client):
    token = _admin_token(client)
    r = client.get("/api/customers/import-template.csv", headers=_h(token))
    assert r.status_code == 200
    tmpl = r.content.decode("utf-8-sig")
    assert "Tên khách hàng" in tmpl and "Loại" in tmpl

    _create(client, token, name="Cty Xuất File", discount_max_pct=8)
    r = client.get("/api/customers/export.csv", headers=_h(token))
    assert r.status_code == 200
    text = r.content.decode("utf-8-sig")
    # Redesign spec-06 v2: export có cột rào chiết khấu/biên (ai cũng xem).
    assert "CK tối đa (%)" in text and "Cty Xuất File" in text


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


# --- Nhóm B: chăm sóc khách hàng (#20/#27/#28) --------------------------------


def test_care_log_and_timeline_merge(client):
    token = _admin_token(client)
    cid = _create(client, token, name="Cty Cham Soc")["customer"]["id"]

    r = client.post(f"/api/customers/{cid}/care", json={
        "kind": "goi_dien", "note": "Gọi hỏi nhu cầu quý 3, khách hẹn gửi maquette.",
    }, headers=_h(token))
    assert r.status_code == 201, r.text
    assert r.json()["kind"] == "goi_dien"

    # Nội dung trống → 422.
    r = client.post(f"/api/customers/{cid}/care", json={"kind": "email", "note": "  "},
                    headers=_h(token))
    assert r.status_code == 422

    items = client.get(f"/api/customers/{cid}/care", headers=_h(token)).json()["items"]
    assert len(items) == 1 and items[0]["actor_name"]

    # Gộp vào timeline Nhật ký (kind=care, số thật).
    audit = client.get(f"/api/customers/{cid}/audit", headers=_h(token)).json()["items"]
    care_rows = [a for a in audit if a["kind"] == "care"]
    assert len(care_rows) == 1 and care_rows[0]["title"] == "Gọi điện"


def test_care_task_lifecycle_and_remind_levels(client):
    from datetime import datetime, timedelta, timezone

    token = _admin_token(client)
    cid = _create(client, token, name="Cty Follow Up")["customer"]["id"]
    now = datetime.now(timezone.utc)

    def mk(days_offset: int) -> dict:
        r = client.post(f"/api/customers/{cid}/care-tasks", json={
            "note": f"Gọi lại ({days_offset:+d} ngày)",
            "due_date": (now + timedelta(days=days_offset)).isoformat(),
        }, headers=_h(token))
        assert r.status_code == 201, r.text
        return r.json()

    future = mk(+3)   # chưa đến hạn → nhắc 0
    due_now = mk(0)   # đến hạn hôm nay → nhắc 1
    late2 = mk(-3)    # quá 3 ngày → nhắc 2
    late3 = mk(-7)    # quá 7 ngày → nhắc 3
    assert future["remind_level"] == 0
    assert due_now["remind_level"] == 1
    assert late2["remind_level"] == 2 and late2["overdue_days"] == 3
    assert late3["remind_level"] == 3

    # Panel "Cần chăm sóc": chỉ các việc đã đến hạn (3 việc, sớm nhất trước).
    fu = client.get("/api/customers/care-followups", headers=_h(token)).json()["items"]
    fu_cid = [f for f in fu if f["customer_id"] == cid]
    assert [f["remind_level"] for f in fu_cid] == [3, 2, 1]

    # Hoàn thành việc quá hạn kèm ghi log chăm sóc trong cùng thao tác.
    r = client.put(
        f"/api/customers/{cid}/care-tasks/{late3['id']}/status",
        json={"status": "done", "log_kind": "goi_dien", "log_note": "Đã gọi, khách chốt."},
        headers=_h(token),
    )
    assert r.status_code == 200
    assert r.json()["status"] == "done" and r.json()["done_at"]

    tasks = client.get(f"/api/customers/{cid}/care-tasks", headers=_h(token)).json()
    # Đánh giá #28: 1 việc xong (trễ — done sau due 7 ngày), 2 việc đang quá hạn.
    assert tasks["done_late"] == 1 and tasks["done_on_time"] == 0
    assert tasks["overdue_open"] == 2
    # Log đi kèm đã vào nhật ký chăm sóc.
    care = client.get(f"/api/customers/{cid}/care", headers=_h(token)).json()["items"]
    assert any("khách chốt" in e["note"] for e in care)


def test_care_recurrence_calendar(client):
    from datetime import datetime, timedelta, timezone

    token = _admin_token(client)
    cid = _create(client, token, name="Cty Lich Hen")["customer"]["id"]
    today = datetime.now(timezone.utc).date()
    start = datetime.combine(today, datetime.min.time(), tzinfo=timezone.utc)

    def dt(offset):    # ISO datetime — dùng trong JSON body
        return (start + timedelta(days=offset)).isoformat()

    def day(offset):   # 'YYYY-MM-DD' — dùng trong query from/to (tránh '+' của timezone)
        return (today + timedelta(days=offset)).isoformat()

    # Hẹn lặp MỖI TUẦN, đến +30 ngày.
    r = client.post(f"/api/customers/{cid}/care-tasks", json={
        "note": "Gọi hỏi tiến độ đơn", "due_date": dt(0),
        "repeat_freq": "week", "repeat_interval": 1, "repeat_until": dt(30),
    }, headers=_h(token))
    assert r.status_code == 201, r.text
    head = r.json()
    assert head["repeat_freq"] == "week" and head["repeat_interval"] == 1

    def cal(a=-1, b=30):
        return client.get(
            f"/api/customers/{cid}/care-calendar?from={day(a)}&to={day(b)}", headers=_h(token)
        ).json()["items"]

    # Lịch [today-1, +30]: bung head (today) + 4 lần tuần tương lai (7/14/21/28) là ẢO.
    occ = cal()
    assert sorted(o["due_date"][:10] for o in occ) == [day(0), day(7), day(14), day(21), day(28)]
    assert sum(not o["is_virtual"] for o in occ) == 1    # chỉ head là dòng cụ thể
    assert sum(o["is_virtual"] for o in occ) == 4

    # Hoàn thành LẦN hôm nay → materialize 'done' + head tiến sang tuần kế (+7).
    r = client.post(
        f"/api/customers/{cid}/care-tasks/{head['id']}/occurrence?from={day(-1)}&to={day(30)}",
        json={"action": "complete", "occurrence_date": dt(0), "log_note": "Đã gọi xong."},
        headers=_h(token),
    )
    assert r.status_code == 200, r.text
    m = {o["due_date"][:10]: o for o in r.json()["items"]}
    assert m[day(0)]["status"] == "done" and not m[day(0)]["is_virtual"]   # lần cũ đã xong
    assert m[day(7)]["status"] == "open" and not m[day(7)]["is_virtual"]   # head tiến sang +7
    assert m[day(14)]["is_virtual"]                                        # tương lai vẫn ảo

    # Log đi kèm vào nhật ký chăm sóc.
    care = client.get(f"/api/customers/{cid}/care", headers=_h(token)).json()["items"]
    assert any("Đã gọi xong" in e["note"] for e in care)


def test_care_followups_scoped_to_caller(client):
    from datetime import datetime, timedelta, timezone

    _seed_demo()
    admin = _admin_token(client)
    db = SessionLocal()
    try:
        sale1 = UserRepository(db).get_by_username("sale1")
        sale2 = UserRepository(db).get_by_username("sale2")
    finally:
        db.close()

    cid = _create(client, admin, name="Cty Cua Sale1", sale_user_id=sale1.id)["customer"]["id"]
    client.post(f"/api/customers/{cid}/care-tasks", json={
        "note": "Gọi chốt hợp đồng",
        "due_date": (datetime.now(timezone.utc) - timedelta(days=1)).isoformat(),
    }, headers=_h(admin))

    # sale1 (scope own) thấy việc trên khách của mình; sale2 không thấy.
    t1 = create_access_token(str(sale1.id))
    t2 = create_access_token(str(sale2.id))
    fu1 = client.get("/api/customers/care-followups", headers=_h(t1)).json()["items"]
    fu2 = client.get("/api/customers/care-followups", headers=_h(t2)).json()["items"]
    assert any(f["customer_name"] == "Cty Cua Sale1" for f in fu1)
    assert not any(f["customer_name"] == "Cty Cua Sale1" for f in fu2)
    # Việc mặc định gán cho Sale phụ trách khách.
    assert fu1[0]["assignee_name"]


# --- Nhãn thủ công (#7: sales gán tay) -----------------------------------------


def test_tags_manual_assign_dedup_filter(client):
    token = _admin_token(client)
    cid = _create(client, token, name="Cty Gan Nhan")["customer"]["id"]
    cid2 = _create(client, token, name="Cty Khong Nhan")["customer"]["id"]

    # Gán 2 nhãn; gán lại nhãn cũ (khác hoa thường) → không tạo đúp.
    r = client.post(f"/api/customers/{cid}/tags", json={"label": "Đại lý"}, headers=_h(token))
    assert r.status_code == 201
    tag_id = r.json()["id"]
    client.post(f"/api/customers/{cid}/tags", json={"label": "Khách sự kiện"}, headers=_h(token))
    r = client.post(f"/api/customers/{cid}/tags", json={"label": "đại lý"}, headers=_h(token))
    assert r.json()["id"] == tag_id  # trả nhãn có sẵn, không đúp

    tags = client.get(f"/api/customers/{cid}/tags", headers=_h(token)).json()["items"]
    assert sorted(t["label"] for t in tags) == ["Khách sự kiện", "Đại lý"] or len(tags) == 2

    # Nhãn trống → 422.
    r = client.post(f"/api/customers/{cid}/tags", json={"label": "   "}, headers=_h(token))
    assert r.status_code == 422

    # Chips trong danh bạ + lọc theo nhãn (case-insensitive).
    rows = client.get("/api/customers", params={"tag": "ĐẠI LÝ", "size": 200},
                      headers=_h(token)).json()["items"]
    ids = {c["id"] for c in rows}
    assert cid in ids and cid2 not in ids
    me = next(c for c in rows if c["id"] == cid)
    assert "Đại lý" in me["tags"]

    # Gợi ý nhãn đã dùng trong scope.
    labels = client.get("/api/customers/tags", headers=_h(token)).json()
    assert "Đại lý" in labels and "Khách sự kiện" in labels

    # Gỡ nhãn + audit ghi vào Nhật ký.
    assert client.delete(
        f"/api/customers/{cid}/tags/{tag_id}", headers=_h(token)
    ).status_code == 204
    audit = client.get(f"/api/customers/{cid}/audit", headers=_h(token)).json()["items"]
    details = " | ".join(a["detail"] for a in audit if a["kind"] == "profile")
    assert "Gán nhãn: Đại lý" in details and "Gỡ nhãn: Đại lý" in details


# --- Kho nhãn dùng chung: THÊM và XOÁ được (16/08/2026) -------------------------
# Trước đó kho nhãn là mảng 13 chuỗi viết cứng trong `KhachHangPage.tsx`: gán thêm thì được, mà
# XOÁ thì không đường nào — gỡ nhãn khỏi mọi khách xong, mở hộp ra nó vẫn nằm đấy vì nó nằm trong
# code. Ba test dưới ghim đúng ba mắt xích làm cho "xoá" thành thật.


def test_kho_nhan_them_roi_xoa_hop_le(client):
    """(Hạt mồi 13 nhãn của mg `0204` kiểm ở `test_kho_nhan_migration.py` — fixture `db` chỉ
    `create_all`, không chạy migration, nên đừng chờ nhãn mồi có mặt ở đây.)"""
    token = _admin_token(client)

    # Thêm nhãn mới.
    r = client.post("/api/customers/tag-kho", json={"label": "Giao tỉnh"}, headers=_h(token))
    assert r.status_code == 201
    moi_id = r.json()["id"]

    # Thêm lại y hệt (khác hoa-thường) → trả nhãn cũ, KHÔNG đẻ dòng thứ hai.
    r2 = client.post("/api/customers/tag-kho", json={"label": "giao tỉnh"}, headers=_h(token))
    assert r2.json()["id"] == moi_id

    # Xoá → biến mất THẬT khỏi kho (đây là thứ bản viết cứng không làm được).
    assert client.delete(
        f"/api/customers/tag-kho/{moi_id}", headers=_h(token)
    ).json()["so_khach_da_go"] == 0
    con_lai = {r["label"] for r in
               client.get("/api/customers/tag-kho", headers=_h(token)).json()["items"]}
    assert "Giao tỉnh" not in con_lai


def test_xoa_nhan_kho_go_luon_khoi_khach_dang_mang(client):
    """Xoá nhãn thì chip trên khách phải rơi theo.

    Để lại chip mà nhãn đã khỏi kho là tạo ra một chip KHÔNG GỠ ĐƯỢC: hộp Gắn thẻ chỉ bày nhãn
    có trong kho, nên không còn ô nào để bỏ tick."""
    token = _admin_token(client)
    cid = _create(client, token, name="Cty Mang Nhan")["customer"]["id"]
    client.post(f"/api/customers/{cid}/tags", json={"label": "Hay đổi ý"}, headers=_h(token))

    kho = client.get("/api/customers/tag-kho", headers=_h(token)).json()["items"]
    dong = next(r for r in kho if r["label"] == "Hay đổi ý")
    assert dong["so_khach"] == 1, "phải đếm được số khách đang mang để cảnh báo trước khi xoá"

    assert client.delete(
        f"/api/customers/tag-kho/{dong['id']}", headers=_h(token)
    ).json()["so_khach_da_go"] == 1
    con = client.get(f"/api/customers/{cid}/tags", headers=_h(token)).json()["items"]
    assert [t["label"] for t in con] == []


def test_go_nhan_tay_tu_vao_kho(client):
    """Nhãn gõ tay ở hộp Gắn thẻ phải tự vào kho — không thì lần sau người khác gõ lại từ đầu
    và sinh ra hai biến thể của cùng một ý, làm ô lọc tách đôi kết quả."""
    token = _admin_token(client)
    cid = _create(client, token, name="Cty Go Tay")["customer"]["id"]
    client.post(f"/api/customers/{cid}/tags", json={"label": "In gấp"}, headers=_h(token))

    kho = {r["label"] for r in
           client.get("/api/customers/tag-kho", headers=_h(token)).json()["items"]}
    assert "In gấp" in kho


# --- Pha B: nhắc lịch hẹn real-time (SSE "ting") --------------------------------


def test_care_assigned_pings_other_assignee(client, monkeypatch):
    """Giao hẹn cho NGƯỜI KHÁC (mặc định = Sale phụ trách ≠ người tạo) → publish 'care_assigned'."""
    from app.realtime import hub

    _seed_demo()
    events: list = []
    monkeypatch.setattr(hub, "publish", lambda uid, e: events.append((uid, e)))
    admin = _admin_token(client)
    db = SessionLocal()
    try:
        sale1 = UserRepository(db).get_by_username("sale1")
    finally:
        db.close()

    cid = _create(client, admin, name="Cty Cua Sale1", sale_user_id=sale1.id)["customer"]["id"]
    r = client.post(f"/api/customers/{cid}/care-tasks", json={
        "note": "Gọi chốt hợp đồng", "due_date": "2030-01-01T09:00:00+00:00",
    }, headers=_h(admin))
    assert r.status_code == 201, r.text
    assigned = [(uid, e) for uid, e in events if e["type"] == "care_assigned"]
    assert len(assigned) == 1 and assigned[0][0] == sale1.id
    assert assigned[0][1]["customer"] == "Cty Cua Sale1"
    assert assigned[0][1]["note"] == "Gọi chốt hợp đồng"


def test_care_no_ping_when_self_assigned(client, monkeypatch):
    """Tự nhận việc (assignee = người tạo) → KHÔNG ting (không tự báo mình)."""
    from app.realtime import hub

    events: list = []
    monkeypatch.setattr(hub, "publish", lambda uid, e: events.append((uid, e)))
    token = _admin_token(client)
    cid = _create(client, token, name="Cty Tu Lam")["customer"]["id"]  # sale mặc định = admin
    r = client.post(f"/api/customers/{cid}/care-tasks", json={
        "note": "Tự làm", "due_date": "2030-01-01T09:00:00+00:00",
    }, headers=_h(token))
    assert r.status_code == 201, r.text
    assert not [e for _, e in events if e["type"] == "care_assigned"]


def test_care_reminder_window_pings_due_once(client, monkeypatch):
    """Ticker quét cửa sổ (after, until]: hẹn tới giờ ting ĐÚNG 1 LẦN; quét lại (hở-trái) không lặp."""
    from datetime import datetime, timedelta, timezone

    from app.care_reminders import _scan_once
    from app.realtime import hub

    events: list = []
    monkeypatch.setattr(hub, "publish", lambda uid, e: events.append((uid, e)))
    token = _admin_token(client)
    cid = _create(client, token, name="Cty Ting")["customer"]["id"]
    now = datetime.now(timezone.utc)
    r = client.post(f"/api/customers/{cid}/care-tasks", json={
        "note": "Gọi khách", "due_date": now.isoformat(),
    }, headers=_h(token))
    assert r.status_code == 201, r.text

    # Cửa sổ chứa giờ hẹn → ting đúng 1 lần.
    n = _scan_once(now - timedelta(minutes=1), now + timedelta(minutes=1))
    due = [e for _, e in events if e["type"] == "care_due"]
    assert n == 1 and len(due) == 1
    assert due[0]["customer"] == "Cty Ting" and due[0]["note"] == "Gọi khách"

    # Cửa sổ SAU đó (after = now): due_date = now KHÔNG > now → không nhắc lại.
    events.clear()
    assert _scan_once(now, now + timedelta(minutes=2)) == 0
    assert not [e for _, e in events if e["type"] == "care_due"]
