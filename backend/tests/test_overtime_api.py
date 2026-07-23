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


def test_validate_gio_va_chan_trung_phieu(client):
    token = _admin_token(client)
    eid = _make_emp(client, token, name="Thợ TC 2")
    _mk(client, token, eid, frm=1500, to=1320, expect=400)             # kết thúc trước bắt đầu
    _mk(client, token, eid, frm=1320, to=1320 + 13 * 60, expect=400)   # quá 12h (Đ107 BLLĐ)
    _mk(client, token, eid, frm=1320, to=1620)                         # hợp lệ
    _mk(client, token, eid, frm=1500, to=1700, expect=400)             # GIAO phiếu đã có


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
