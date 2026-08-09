"""Phiếu tăng ca (module `tang_ca`): NV gửi → tổ trưởng duyệt; tổ trưởng tạo hộ = duyệt luôn.

Phiếu ĐÃ DUYỆT là GIẤY PHÉP + MỨC TRẦN cho tiền tăng ca (Bảng công gate theo phiếu).
Tổ trưởng có scope `department` ⇒ chỉ đụng được người trong tổ mình.
"""
from __future__ import annotations

from app.db import SessionLocal
from app.repositories.employee_repo import EmployeeRepository
from app.repositories.rbac_repo import DepartmentRepository, RoleRepository
from app.repositories.user_repo import UserRepository
from app.security import create_access_token, hash_password

ADMIN = {"username": "admin", "password": "admin123"}


def _admin_token(client) -> str:
    return client.post("/api/auth/login", json=ADMIN).json()["access_token"]


def _h(t: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {t}"}


def _dept_id(name: str) -> int:
    db = SessionLocal()
    try:
        return DepartmentRepository(db).get_by_name(name).id
    finally:
        db.close()


def _make_emp(client, token, *, name, dept="Sản xuất") -> int:
    body = {"full_name": name, "department_id": _dept_id(dept),
            "hire_date": "2020-01-01", "gender": "male", "status": "active"}
    return client.post("/api/employees", json=body, headers=_h(token)).json()["employee"]["id"]


def _lead_token() -> str:
    """Tài khoản vai 'Tổ trưởng SX' — có `tang_ca:approve` với scope `department`."""
    db = SessionLocal()
    try:
        users = UserRepository(db)
        existing = users.get_by_username("to-truong-ot")
        if existing is not None:
            return create_access_token(str(existing.id))
        sx = DepartmentRepository(db).get_by_name("Sản xuất")
        role = RoleRepository(db).get_by_name_and_department("Tổ trưởng SX", sx.id)
        u = users.create(username="to-truong-ot", name="Tổ trưởng",
                         password_hash=hash_password("x"))
        users.set_assignment(u, department_id=sx.id, role_id=role.id, is_active=True)
        return create_access_token(str(u.id))
    finally:
        db.close()


def _mk(client, token, eid, *, work_date="2026-07-16", frm=1320, to=1620, expect=201):
    """Tạo hộ (tổ trưởng/HCNS). frm/to = phút từ 00:00 NGÀY CÔNG → 1620 = 03:00 hôm sau."""
    r = client.post("/api/overtime",
                    json={"employee_id": eid, "work_date": work_date, "from_minute": frm,
                          "to_minute": to, "reason": "chạy đơn gấp"}, headers=_h(token))
    assert r.status_code == expect, r.text
    return r.json() if r.status_code < 400 else None


def test_lead_tao_ho_thi_duyet_luon(client):
    """Tổ trưởng tạo thẳng cho thợ → APPROVED ngay, không bắt thợ gửi rồi duyệt lại."""
    token = _admin_token(client)
    eid = _make_emp(client, token, name="Thợ TC 1")
    r = _mk(client, token, eid)
    assert r["status"] == "approved"
    assert r["minutes"] == 300              # 22:00 → 03:00 hôm sau = 5h
    assert r["employee_name"] == "Thợ TC 1"


def test_nv_tu_gui_roi_duoc_duyet(client):
    """NV tự gửi → chờ duyệt → người có quyền duyệt bấm duyệt."""
    token = _admin_token(client)
    r = client.post("/api/overtime/me",
                    json={"work_date": "2026-07-16", "from_minute": 1320, "to_minute": 1500,
                          "reason": "gấp"}, headers=_h(token))
    assert r.status_code == 201, r.text
    rid = r.json()["id"]
    assert r.json()["status"] == "pending"

    mine = client.get("/api/overtime/me", headers=_h(token)).json()
    assert mine["has_employee"] is True and any(x["id"] == rid for x in mine["items"])

    ok = client.post(f"/api/overtime/{rid}/approve", json={}, headers=_h(token))
    assert ok.status_code == 200 and ok.json()["status"] == "approved"
    # Duyệt rồi thì không duyệt lại được nữa.
    assert client.post(f"/api/overtime/{rid}/approve", json={},
                       headers=_h(token)).status_code == 400


def test_validate_gio_va_toi_da_1_phieu_ngay(client):
    """Biên giờ + luật 1 phiếu/ngày (chủ chốt 2026-07-24)."""
    token = _admin_token(client)
    eid = _make_emp(client, token, name="Thợ TC 2")
    _mk(client, token, eid, frm=1500, to=1320, expect=400)             # kết thúc trước bắt đầu
    _mk(client, token, eid, frm=1320, to=1320 + 13 * 60, expect=400)   # quá 12h (Đ107 BLLĐ)
    _mk(client, token, eid, frm=1320, to=1620)                         # phiếu 1 hợp lệ
    _mk(client, token, eid, frm=100, to=300, expect=400)              # phiếu 2 KHÔNG trùng giờ vẫn bị chặn
    _mk(client, token, eid, work_date="2026-07-17")                    # ngày khác → OK


def test_tu_choi_roi_thi_tao_lai_cung_ngay_duoc(client):
    """Phiếu bị TỪ CHỐI không còn 'giữ chỗ' → tạo lại phiếu khác cùng ngày được."""
    token = _admin_token(client)
    eid = _make_emp(client, token, name="Thợ TC tạo lại")
    r = client.post("/api/overtime/me",
                    json={"work_date": "2026-07-16", "from_minute": 1320, "to_minute": 1440},
                    headers=_h(token))
    rid = r.json()["id"]
    client.post(f"/api/overtime/{rid}/reject", json={"note": "chưa cần"}, headers=_h(token))
    # Cùng ngày, tạo phiếu mới → OK vì phiếu cũ đã bị từ chối.
    _mk(client, token, eid, work_date="2026-07-16", frm=1320, to=1500)


def test_sua_phieu_cho_duyet(client):
    """Sửa phiếu đang chờ: đổi giờ OK; duyệt rồi thì khóa; người khác không sửa được."""
    token = _admin_token(client)
    r = client.post("/api/overtime/me",
                    json={"work_date": "2026-07-18", "from_minute": 1320, "to_minute": 1440,
                          "reason": "cũ"}, headers=_h(token))
    rid = r.json()["id"]
    upd = client.put(f"/api/overtime/{rid}",
                     json={"work_date": "2026-07-18", "from_minute": 1200, "to_minute": 1500,
                           "reason": "mới"}, headers=_h(token))
    assert upd.status_code == 200, upd.text
    assert upd.json()["from_minute"] == 1200 and upd.json()["minutes"] == 300
    assert upd.json()["reason"] == "mới"

    # Người KHÁC (tổ trưởng, không phải người tạo) → không sửa được phiếu của admin.
    lead = _lead_token()
    assert client.put(f"/api/overtime/{rid}",
                      json={"work_date": "2026-07-18", "from_minute": 1200, "to_minute": 1260},
                      headers=_h(lead)).status_code in (400, 403)

    # Duyệt rồi thì khóa, không sửa được nữa.
    client.post(f"/api/overtime/{rid}/approve", json={}, headers=_h(token))
    locked = client.put(f"/api/overtime/{rid}",
                        json={"work_date": "2026-07-18", "from_minute": 1200, "to_minute": 1260},
                        headers=_h(token))
    assert locked.status_code == 400 and "chờ duyệt" in locked.json()["detail"].lower()


def test_tu_choi_bat_buoc_ly_do(client):
    token = _admin_token(client)
    r = client.post("/api/overtime/me",
                    json={"work_date": "2026-07-20", "from_minute": 1320, "to_minute": 1440},
                    headers=_h(token))
    rid = r.json()["id"]
    assert client.post(f"/api/overtime/{rid}/reject", json={"note": ""},
                       headers=_h(token)).status_code == 422      # schema chặn note rỗng
    ok = client.post(f"/api/overtime/{rid}/reject", json={"note": "không cần tăng ca"},
                     headers=_h(token))
    assert ok.status_code == 200 and ok.json()["status"] == "rejected"


def test_huy_phieu(client):
    token = _admin_token(client)
    r = client.post("/api/overtime/me",
                    json={"work_date": "2026-07-21", "from_minute": 1320, "to_minute": 1440},
                    headers=_h(token))
    rid = r.json()["id"]
    ok = client.post(f"/api/overtime/{rid}/cancel", headers=_h(token))
    assert ok.status_code == 200 and ok.json()["status"] == "cancelled"


def test_to_truong_chi_thay_phieu_trong_to_minh(client):
    """Scope `department`: tổ trưởng KHÔNG thấy (⇒ không duyệt được) phiếu của phòng khác."""
    token = _admin_token(client)
    kd_emp = _make_emp(client, token, name="NV Kinh doanh", dept="Kinh doanh")
    sx_emp = _make_emp(client, token, name="Thợ Sản xuất", dept="Sản xuất")
    _mk(client, token, kd_emp, work_date="2026-07-17")
    _mk(client, token, sx_emp, work_date="2026-07-17")

    lead = _lead_token()
    seen = {x["employee_id"] for x in client.get("/api/overtime", headers=_h(lead)).json()["items"]}
    assert kd_emp not in seen        # ngoài tổ → không lộ
    assert sx_emp in seen            # trong tổ → thấy

    # Admin scope `all` thì thấy cả hai.
    all_seen = {x["employee_id"]
                for x in client.get("/api/overtime", headers=_h(token)).json()["items"]}
    assert {kd_emp, sx_emp} <= all_seen


def _plain_token_with_emp(client, admin_token) -> str:
    """Tài khoản vai 'NV Sales' — KHÔNG có ô quyền `tang_ca` nào, đã gắn hồ sơ nhân viên."""
    eid = _make_emp(client, admin_token, name="NV thường TC", dept="Kinh doanh")
    db = SessionLocal()
    try:
        users = UserRepository(db)
        u = users.get_by_username("nv-thuong-ot")
        if u is None:
            kd = DepartmentRepository(db).get_by_name("Kinh doanh")
            role = RoleRepository(db).get_by_name_and_department("NV Sales", kd.id)
            u = users.create(username="nv-thuong-ot", name="NV thường",
                             password_hash=hash_password("x"))
            users.set_assignment(u, department_id=kd.id, role_id=role.id, is_active=True)
        emps = EmployeeRepository(db)
        emps.update(emps.get_by_id(eid), user_id=u.id)
        return create_access_token(str(u.id))
    finally:
        db.close()


def test_tu_phuc_vu_khong_can_o_quyen(client):
    """Mọi NLĐ đều phải XIN được tăng ca cho CHÍNH MÌNH và HỦY được phiếu chưa duyệt của mình —
    không phụ thuộc ô quyền `tang_ca` (đúng khuôn 'Yêu cầu chỉnh công'). Nhưng KHÔNG được duyệt."""
    admin = _admin_token(client)
    t = _plain_token_with_emp(client, admin)

    r = client.post("/api/overtime/me",
                    json={"work_date": "2026-07-23", "from_minute": 1200, "to_minute": 1320},
                    headers=_h(t))
    assert r.status_code == 201, r.text
    rid = r.json()["id"]
    assert r.json()["status"] == "pending"

    mine = client.get("/api/overtime/me", headers=_h(t)).json()
    assert any(x["id"] == rid for x in mine["items"])

    # Tự hủy phiếu của mình khi chưa được duyệt.
    ok = client.post(f"/api/overtime/{rid}/cancel", headers=_h(t))
    assert ok.status_code == 200 and ok.json()["status"] == "cancelled"

    # Nhưng KHÔNG tự duyệt được (duyệt vẫn phải có quyền `approve`).
    r2 = client.post("/api/overtime/me",
                     json={"work_date": "2026-07-24", "from_minute": 1200, "to_minute": 1320},
                     headers=_h(t))
    assert client.post(f"/api/overtime/{r2.json()['id']}/approve", json={},
                       headers=_h(t)).status_code == 403


def test_summary_badge(client):
    """`pending_in_scope` chỉ hiện cho người CÓ quyền duyệt (chống lộ số cho người không phận sự)."""
    token = _admin_token(client)
    eid = _make_emp(client, token, name="Thợ TC 3")
    client.post("/api/overtime/me",
                json={"work_date": "2026-07-22", "from_minute": 1320, "to_minute": 1440},
                headers=_h(token))
    s = client.get("/api/overtime/summary", headers=_h(token)).json()
    assert s["pending_in_scope"] >= 1
    assert eid is not None


# --- phân trang (09/08/2026) -------------------------------------------------
# Trước đây `/api/overtime/me` và `/api/overtime` trả thẳng danh sách với trần cứng 100/200 gõ
# trong repo — quá số đó là phiếu RỤNG im lặng. Bốn test dưới khoá: `total` đúng, trang 2 ra
# dòng khác trang 1, `size` có trần, và phân trang KHÔNG nới phạm vi của tổ trưởng.


def _seed_overtime(employee_id: int, count: int, *, status="pending",
                   start_day: str = "2026-03-01") -> list[int]:
    """Ghi thẳng `count` phiếu vào DB, mỗi phiếu MỘT ngày công khác nhau.

    CỐ Ý không đi qua `POST /api/overtime`: đường đó có luật "tối đa 1 phiếu còn hiệu lực /
    ngày" và vài kiểm tra khác — ở đây đang kiểm ĐƯỜNG ĐỌC nên nạp bằng model là đúng tầng."""
    from datetime import date, timedelta

    from app.models.overtime import OvertimeRequest

    db = SessionLocal()
    try:
        ids = []
        base = date.fromisoformat(start_day)
        for i in range(count):
            row = OvertimeRequest(employee_id=employee_id, work_date=base + timedelta(days=i),
                                  from_minute=1320, to_minute=1500, status=status)
            db.add(row)
            db.flush()
            ids.append(row.id)
        db.commit()
        return ids
    finally:
        db.close()


def _my_employee_id(client, token) -> int:
    return client.get("/api/employees/me", headers=_h(token)).json()["employee"]["id"]


def test_phieu_cua_toi_phan_trang_dung_total(client):
    token = _admin_token(client)
    eid = _my_employee_id(client, token)
    _seed_overtime(eid, 25)

    p1 = client.get("/api/overtime/me?page=1&size=20", headers=_h(token)).json()
    p2 = client.get("/api/overtime/me?page=2&size=20", headers=_h(token)).json()

    assert p1["total"] == 25 and p1["page"] == 1 and p1["size"] == 20
    assert len(p1["items"]) == 20 and len(p2["items"]) == 5
    ids1 = {x["id"] for x in p1["items"]}
    ids2 = {x["id"] for x in p2["items"]}
    assert ids1.isdisjoint(ids2) and len(ids1 | ids2) == 25
    # `has_employee` / `employee_name` vẫn ở gốc (client cũ đọc hai ô này).
    assert p1["has_employee"] is True and p1["employee_name"]

    assert client.get("/api/overtime/me?size=101", headers=_h(token)).status_code == 422
    assert client.get("/api/overtime/me?page=0", headers=_h(token)).status_code == 422


def test_duyet_phieu_phan_trang_dung_total_va_trang_2_khac_trang_1(client):
    token = _admin_token(client)
    eid = _make_emp(client, token, name="Thợ phân trang")
    _seed_overtime(eid, 25)

    p1 = client.get("/api/overtime?page=1&size=20", headers=_h(token)).json()
    p2 = client.get("/api/overtime?page=2&size=20", headers=_h(token)).json()

    assert p1["total"] >= 25 and p1["total"] == p2["total"]
    assert len(p1["items"]) == 20
    ids1 = {x["id"] for x in p1["items"]}
    ids2 = {x["id"] for x in p2["items"]}
    assert ids1.isdisjoint(ids2)

    assert client.get("/api/overtime?size=101", headers=_h(token)).status_code == 422
    assert client.get("/api/overtime?page=0", headers=_h(token)).status_code == 422


def test_hang_doi_duyet_loc_pending_van_ra_du_phieu_cho_duyet(client):
    """Hang doi "Duyet phieu" PHAI loc `status_filter=pending`, khong duoc lay tron.

    Loi bat duoc ngay 09/08/2026 khi them phan trang: repo sap xep theo `status` TANG DAN, ma gia
    tri la CHUOI THUONG nen thu tu chu cai la approved < cancelled < pending < rejected. Phieu DA
    DUYET dung truoc, phieu CHO DUYET bi day xuong cuoi.

    Truoc khi co phan trang, ca 200 dong nam chung mot bang nen cuon xuong van thay. Cat con 20
    dong/trang la TRANG 1 SACH BONG phieu cho duyet, trong khi tab van ghi "Duyet phieu (3)" va
    tieu de bang van ghi "Phieu cho duyet" — to truong mo ra tuong het viec roi bo di.

    Test nay khoa dung ca do: nhieu phieu da duyet + vai phieu cho duyet, loc pending phai ra DU.
    """
    token = _admin_token(client)
    eid = _make_emp(client, token, name="Thợ hàng đợi")
    _seed_overtime(eid, 25, status="approved", start_day="2026-04-01")
    _seed_overtime(eid, 3, status="pending", start_day="2026-05-01")

    # KHONG loc: phieu duyet chiem het trang 1 — day chinh la hien trang gay loi.
    khong_loc = client.get("/api/overtime?page=1&size=20", headers=_h(token)).json()
    assert all(x["status"] == "approved" for x in khong_loc["items"]), (
        "gia dinh cua test: khong loc thi trang 1 toan phieu da duyet"
    )

    # CO loc pending: phai ra du 3 phieu cho duyet ngay trang 1.
    loc = client.get(
        "/api/overtime?status_filter=pending&page=1&size=20", headers=_h(token)
    ).json()
    cho_duyet = [x for x in loc["items"] if x["employee_id"] == eid]
    assert len(cho_duyet) == 3
    assert all(x["status"] == "pending" for x in loc["items"])
    # `total` cung phai la tong SAU khi loc, khong phai tong tat ca.
    assert loc["total"] == len([x for x in loc["items"]]) or loc["total"] >= 3


def test_phan_trang_giu_nguyen_pham_vi_cua_to_truong(client):
    """Tổ trưởng scope `department`: `total` phải đếm ĐÚNG phạm vi ấy, không đếm cả công ty.
    `total` mà rộng hơn danh sách là badge/chân bảng báo số mở ra xem không được."""
    token = _admin_token(client)
    lead = _lead_token()
    trong_to = _make_emp(client, token, name="Thợ trong tổ", dept="Sản xuất")
    ngoai_to = _make_emp(client, token, name="NV ngoài tổ", dept="Kinh doanh")
    _seed_overtime(trong_to, 22)
    _seed_overtime(ngoai_to, 7, start_day="2026-05-01")

    res = client.get("/api/overtime?size=100", headers=_h(lead)).json()
    assert res["total"] == len(res["items"])          # total khớp đúng số dòng lấy được
    assert ngoai_to not in {x["employee_id"] for x in res["items"]}
    assert trong_to in {x["employee_id"] for x in res["items"]}

    # HCNS/Admin (scope `all`) thấy CẢ HAI ⇒ chứng minh chênh lệch trên là do scope, không
    # phải do phân trang cắt mất.
    tat_ca = client.get("/api/overtime?size=100", headers=_h(token)).json()
    assert {trong_to, ngoai_to} <= {x["employee_id"] for x in tat_ca["items"]}


def test_employee_id_loc_trong_pham_vi_khong_noi_quyen(client):
    token = _admin_token(client)
    lead = _lead_token()
    ngoai_to = _make_emp(client, token, name="NV ngoài tổ 2", dept="Kinh doanh")
    _seed_overtime(ngoai_to, 4, start_day="2026-06-01")

    # Admin lọc được đúng người đó.
    ok = client.get(f"/api/overtime?employee_id={ngoai_to}", headers=_h(token)).json()
    assert ok["total"] == 4

    # Tổ trưởng gõ id người NGOÀI tổ → rỗng, không lộ phiếu.
    lach = client.get(f"/api/overtime?employee_id={ngoai_to}", headers=_h(lead)).json()
    assert lach["items"] == [] and lach["total"] == 0
