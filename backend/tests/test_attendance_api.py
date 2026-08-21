"""Chấm công GPS (module `nhan_su`, lát Chấm công).

Work-location config (HR-gated), Haversine geofence with hard block outside the radius,
auto VÀO/RA toggling, self check-in gated on a linked employee, and the RBAC boundary.
"""
from __future__ import annotations

import calendar
from datetime import date, datetime, timedelta, timezone

import pytest

import app.services.attendance_service as _att_svc
from app.db import SessionLocal
from app.repositories.attendance_repo import AttendanceRepository
from app.repositories.employee_repo import EmployeeRepository
from app.repositories.rbac_repo import DepartmentRepository, RoleRepository
from app.repositories.user_repo import UserRepository
from app.security import create_access_token, hash_password

ADMIN = {"username": "admin", "password": "admin123"}


def _ngay_cuoi_thang() -> date:
    t = date.today()
    return date(t.year, t.month, calendar.monthrange(t.year, t.month)[1])


@pytest.fixture(autouse=True)
def _ghim_hom_nay(monkeypatch):
    """Ghim "hôm nay" về NGÀY CUỐI của tháng hiện tại.

    Luật "không chấm công cho ngày chưa tới" (`_require_not_future`) làm mọi test hạn mức chỉnh
    công phụ thuộc NGÀY CHẠY: `_this_month(1..11)` là quá khứ khi chạy cuối tháng nhưng là tương
    lai khi chạy mùng 3. Ghim lại để suite xanh/đỏ vì CODE chứ không vì hôm nay là ngày mấy.

    Phải là ngày CUỐI tháng chứ không phải một ngày cố định giữa tháng: nhiều test chấm công/chấm
    bù dùng NGÀY THẬT (`_vn_today_str`), ghim vào ngày sớm hơn là chính ngày thật hoá "tương lai".
    Ngày cuối tháng thoả cả hai đầu: ≥ mọi ngày thật, và > mọi ngày `_this_month` (kẹp ≤ 28).
    "Ngày mai" trong test = mùng 1 tháng sau.
    Seam này CHỈ chi phối `_require_not_future`; lượt chấm thật vẫn ghi theo giờ thực."""
    monkeypatch.setattr(_att_svc, "_today_vn", _ngay_cuoi_thang)


def _vai_cham_bu_pham_vi(pham_vi: str, ten_vai: str) -> str:
    """Tao mot vai CO quyen cham bu nhung PHAM VI hep, tra token.

    Dung cho test chot ky: hom nay chi Giam doc va TP HCNS co `adjust`, ca hai deu pham vi ca cong
    ty — nen khong the dung tai khoan seed de kiem hang rao pham vi."""
    from app.models.role import SCOPE_ALL  # noqa: F401  (giu import gan cho de doc)

    db = SessionLocal()
    try:
        depts, roles, users = DepartmentRepository(db), RoleRepository(db), UserRepository(db)
        dept = depts.get_by_name("Sản xuất")
        role = roles.get_by_name_and_department(ten_vai, dept.id)
        if role is None:
            role = roles.create(name=ten_vai, department_id=dept.id)
        # Màn Chấm công có khoá RIÊNG từ 10/08/2026 (`cham_cong`), và CHỐT KỲ tách sang ô
        # `can_lock` chứ không còn đi kèm `can_adjust` — cấp cả hai để test kiểm đúng hàng rào
        # PHẠM VI chứ không vô tình kiểm nhầm hàng rào "chưa cấp ô nào".
        roles.set_permission(
            role_id=role.id, module_key="cham_cong",
            can_read=True, can_adjust=True, can_lock=True, scope=pham_vi,
        )
        uname = f"probe-{ten_vai.lower().replace(' ', '-')}"
        u = users.get_by_username(uname)
        if u is None:
            u = users.create(username=uname, name=ten_vai, password_hash=hash_password("x"))
        users.set_assignment(u, department_id=dept.id, role_id=role.id, is_active=True)
        db.commit()
        return create_access_token(str(u.id))
    finally:
        db.close()


def test_chot_ky_cong_doi_pham_vi_toan_cong_ty(client):
    """CHOT KY / MO LAI KY la viec TOAN CONG TY — pham vi hep phai bi chan.

    Lo hong do duoc ngay 10/08/2026: endpoint chi hoi "co quyen cham bu khong", KHONG hoi nguoi bam
    quan ai. Vai pham vi `own` bam Chot ky ⇒ CHOT DUOC, va anh chup ra 2 dong thuoc 2 phong ban —
    tuc dong bang dau vao luong cua CA NHA MAY. `Mo lai ky` con nang hon: no XOA SACH anh chup do.

    Hom nay chua ai no vi chi Giam doc va TP HCNS co quyen cham bu, ca hai deu pham vi ca cong ty.
    Test nay giu hang rao cho ngay phan quyen hep lai.
    """
    thang_truoc = date.today().replace(day=1) - timedelta(days=1)
    kỳ = {"year": thang_truoc.year, "month": thang_truoc.month}

    for pham_vi, ten in (("own", "Probe Chot Own"), ("department", "Probe Chot Dept")):
        tok = _vai_cham_bu_pham_vi(pham_vi, ten)
        r = client.post("/api/attendance/period/lock", json=kỳ, headers=_h(tok))
        assert r.status_code == 403, f"pham vi {pham_vi} KHONG duoc chot ky: {r.text}"
        assert "cả công ty" in r.json()["detail"]

        r2 = client.post("/api/attendance/period/reopen", json=kỳ, headers=_h(tok))
        assert r2.status_code == 403, f"pham vi {pham_vi} KHONG duoc mo lai ky: {r2.text}"

    # Nguoi pham vi CA CONG TY van chot binh thuong — hang rao khong duoc chan nham nguoi dung that.
    admin = _admin_token(client)
    ok = client.post("/api/attendance/period/lock", json=kỳ, headers=_h(admin))
    assert ok.status_code == 200, ok.text


def _admin_token(client) -> str:
    return client.post("/api/auth/login", json=ADMIN).json()["access_token"]


def _h(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _uid(username: str) -> int:
    db = SessionLocal()
    try:
        return UserRepository(db).get_by_username(username).id
    finally:
        db.close()


def _dept_id(name: str) -> int:
    db = SessionLocal()
    try:
        return DepartmentRepository(db).get_by_name(name).id
    finally:
        db.close()


def _sales_token() -> str:
    db = SessionLocal()
    try:
        users = UserRepository(db)
        existing = users.get_by_username("sales-att")
        if existing is not None:
            return create_access_token(str(existing.id))
        kd = DepartmentRepository(db).get_by_name("Kinh doanh")
        role = RoleRepository(db).get_by_name_and_department("NV Sales", kd.id)
        u = users.create(username="sales-att", name="S", password_hash=hash_password("x"))
        users.set_assignment(u, department_id=kd.id, role_id=role.id, is_active=True)
        return create_access_token(str(u.id))
    finally:
        db.close()


def _make_location(client, token, *, lat=10.0, lng=106.0, radius=200) -> int:
    return client.post(
        "/api/attendance/locations",
        json={"name": "Xưởng demo", "latitude": lat, "longitude": lng, "radius_m": radius},
        headers=_h(token),
    ).json()["id"]


def _ensure_test_shift(client, token) -> int:
    items = client.get("/api/attendance/shifts", headers=_h(token)).json()["items"]
    existing = next((s for s in items if s["name"] == "Ca kiểm thử chấm công"), None)
    if existing is not None:
        return existing["id"]
    return client.post(
        "/api/attendance/shifts",
        json={"name": "Ca kiểm thử chấm công", "start_time": "00:00", "end_time": "23:59"},
        headers=_h(token),
    ).json()["id"]


def _assign_test_shift(client, token, employee_id: int) -> int:
    shift_id = _ensure_test_shift(client, token)
    response = client.put(
        f"/api/employees/{employee_id}/shift",
        json={"default_shift_id": shift_id},
        headers=_h(token),
    )
    assert response.status_code == 200
    return shift_id


def _link_admin_employee(client, token, *, assign_shift: bool = True) -> int:
    """Hồ sơ của admin để tự chấm công.

    LUẬT: mọi tài khoản ĐỀU có hồ sơ (`backfill_employee_profiles`) — admin không còn là ngoại lệ.
    Nên KHÔNG tạo hồ sơ thứ 2 rồi gán (link tài khoản 1–1 sẽ chối): lấy hồ sơ SẴN CÓ của admin rồi
    nắn phòng ban / ngày vào làm cho khớp kịch bản test.
    """
    me = client.get("/api/employees/me", headers=_h(token)).json()
    eid = me["employee"]["id"]
    client.put(
        f"/api/employees/{eid}",
        json={"full_name": "NV Admin", "department_id": _dept_id("Hành chính nhân sự"),
              "hire_date": "2020-01-01"},
        headers=_h(token),
    )
    if assign_shift:
        _assign_test_shift(client, token, eid)
    return eid


# --- work locations ---------------------------------------------------------


def test_location_crud_and_validation(client):
    token = _admin_token(client)
    lid = _make_location(client, token)
    assert lid > 0
    listed = client.get("/api/attendance/locations", headers=_h(token)).json()["items"]
    assert any(l["id"] == lid for l in listed)

    # invalid latitude → 422 (schema)
    bad = client.post(
        "/api/attendance/locations",
        json={"name": "x", "latitude": 999, "longitude": 10, "radius_m": 100},
        headers=_h(token),
    )
    assert bad.status_code == 422
    # zero radius → 422
    bad2 = client.post(
        "/api/attendance/locations",
        json={"name": "x", "latitude": 10, "longitude": 10, "radius_m": 0},
        headers=_h(token),
    )
    assert bad2.status_code == 422


# --- geofenced self check-in ------------------------------------------------


def test_check_in_out_toggle_and_hard_block(client):
    token = _admin_token(client)
    _make_location(client, token, lat=10.0, lng=106.0, radius=200)
    _link_admin_employee(client, token)

    status = client.get("/api/attendance/me/status", headers=_h(token)).json()
    assert status["has_employee"] is True
    assert status["next_action"] == "in"

    # AT the location → check VÀO
    r1 = client.post("/api/attendance/check", json={"latitude": 10.0, "longitude": 106.0}, headers=_h(token)).json()
    assert r1["success"] is True and r1["within_range"] is True and r1["check_type"] == "in"
    assert r1["log"] is not None

    # again → auto toggle to RA
    r2 = client.post("/api/attendance/check", json={"latitude": 10.0, "longitude": 106.0}, headers=_h(token)).json()
    assert r2["success"] is True and r2["check_type"] == "out"

    # far away (~150km) → hard block, no log
    r3 = client.post("/api/attendance/check", json={"latitude": 11.0, "longitude": 107.0}, headers=_h(token)).json()
    assert r3["success"] is False and r3["within_range"] is False
    assert r3["log"] is None and r3["distance_m"] > 200

    logs = client.get("/api/attendance/me/logs", headers=_h(token)).json()["items"]
    assert len(logs) == 2  # only the two in-range checks were recorded
    assert {l["check_type"] for l in logs} == {"in", "out"}


def test_check_in_out_is_blocked_without_an_effective_shift(client):
    token = _admin_token(client)
    _make_location(client, token, lat=10.0, lng=106.0, radius=200)
    employee_id = _link_admin_employee(client, token, assign_shift=False)

    # Ghi mốc bỏ ca hôm nay để bảo đảm cả dữ liệu cũ/default cũng không còn hiệu lực.
    removed = client.put(
        f"/api/employees/{employee_id}/shift",
        json={"default_shift_id": None},
        headers=_h(token),
    )
    assert removed.status_code == 200

    status = client.get("/api/attendance/me/status", headers=_h(token)).json()
    assert status["shift"] is None and status["next_action"] is None

    preview = client.post(
        "/api/attendance/me/preview",
        json={"latitude": 10.0, "longitude": 106.0},
        headers=_h(token),
    )
    check_in = client.post(
        "/api/attendance/check",
        json={"latitude": 10.0, "longitude": 106.0},
        headers=_h(token),
    )
    assert preview.status_code == 400 and "chưa được gán ca" in preview.json()["detail"]
    assert check_in.status_code == 400 and "chưa được gán ca" in check_in.json()["detail"]
    assert client.get("/api/attendance/me/logs", headers=_h(token)).json()["items"] == []

    today = _vn_today_str()
    manual = client.post(
        "/api/attendance/adjust",
        json={"employee_id": employee_id, "date": today, "check_type": "in",
              "time": "08:00", "reason": "Kiểm tra không có ca"},
        headers=_h(token),
    )
    request = client.post(
        "/api/attendance/me/adjust-request",
        json={"date": today, "check_type": "in", "suggested_time": "08:00",
              "reason": "Kiểm tra không có ca"},
        headers=_h(token),
    )
    assert manual.status_code == 400 and "chưa được gán ca" in manual.json()["detail"]
    assert request.status_code == 400 and "chưa được gán ca" in request.json()["detail"]

    # Có ca thì chấm VÀO được; bỏ ca sau đó thì lượt RA cũng bị chặn và không sinh log mới.
    _assign_test_shift(client, token, employee_id)
    checked_in = client.post(
        "/api/attendance/check",
        json={"latitude": 10.0, "longitude": 106.0},
        headers=_h(token),
    )
    assert checked_in.status_code == 200 and checked_in.json()["check_type"] == "in"
    client.put(
        f"/api/employees/{employee_id}/shift",
        json={"default_shift_id": None},
        headers=_h(token),
    )
    check_out = client.post(
        "/api/attendance/check",
        json={"latitude": 10.0, "longitude": 106.0},
        headers=_h(token),
    )
    assert check_out.status_code == 400 and "chưa được gán ca" in check_out.json()["detail"]
    assert len(client.get("/api/attendance/me/logs", headers=_h(token)).json()["items"]) == 1


def test_me_preview_dry_run(client):
    token = _admin_token(client)
    _make_location(client, token, lat=10.0, lng=106.0, radius=200)
    _link_admin_employee(client, token)
    # trong vùng
    p = client.post("/api/attendance/me/preview", json={"latitude": 10.0, "longitude": 106.0}, headers=_h(token)).json()
    assert p["within_range"] is True and p["meters_out"] == 0.0 and p["next_action"] == "in"
    # ngoài vùng
    p2 = client.post("/api/attendance/me/preview", json={"latitude": 11.0, "longitude": 107.0}, headers=_h(token)).json()
    assert p2["within_range"] is False and p2["meters_out"] > 0
    # preview KHÔNG ghi log
    assert client.get("/api/attendance/me/logs", headers=_h(token)).json()["items"] == []


def _orphan_admin_account() -> None:
    """Gỡ hồ sơ khỏi tài khoản admin ở tầng DB.

    LUẬT hiện tại: mọi tài khoản đều có hồ sơ (`backfill_employee_profiles`), tài khoản chỉ sinh ra
    TỪ hồ sơ, và không có endpoint gỡ liên kết ⇒ API KHÔNG còn đường dựng tài khoản mồ côi. Nhánh
    400 dưới đây là phòng thủ cho dữ liệu cũ/nhập ngoài, nên tiền đề phải dựng thẳng ở DB.
    """
    db = SessionLocal()
    try:
        emp = EmployeeRepository(db).get_by_user_id(UserRepository(db).get_by_username("admin").id)
        if emp is not None:
            emp.user_id = None
            db.commit()
    finally:
        db.close()


def test_check_without_linked_employee_is_400(client):
    token = _admin_token(client)
    _make_location(client, token)
    _orphan_admin_account()   # tài khoản KHÔNG hồ sơ (dữ liệu cũ) → chấm công bị chối
    r = client.post("/api/attendance/check", json={"latitude": 10.0, "longitude": 106.0}, headers=_h(token))
    assert r.status_code == 400
    assert client.get("/api/attendance/me/status", headers=_h(token)).json()["has_employee"] is False


def test_check_with_no_location_configured(client):
    token = _admin_token(client)
    _link_admin_employee(client, token)
    r = client.post("/api/attendance/check", json={"latitude": 10.0, "longitude": 106.0}, headers=_h(token)).json()
    assert r["success"] is False and "Chưa cấu hình" in r["message"]


def test_hr_logs_list_shows_employee_name(client):
    token = _admin_token(client)
    _make_location(client, token, lat=10.0, lng=106.0, radius=200)
    _link_admin_employee(client, token)
    client.post("/api/attendance/check", json={"latitude": 10.0, "longitude": 106.0}, headers=_h(token))

    logs = client.get("/api/attendance/logs", headers=_h(token)).json()["items"]
    assert len(logs) == 1
    assert logs[0]["employee_name"] == "NV Admin"
    assert logs[0]["location_name"] == "Xưởng demo"


# --- bảng công tháng --------------------------------------------------------


def _vn_year_month() -> tuple[int, int]:
    from datetime import datetime, timedelta, timezone

    vn = datetime.now(timezone(timedelta(hours=7)))
    return vn.year, vn.month


def test_monthly_timesheet_and_csv(client):
    token = _admin_token(client)
    _make_location(client, token, lat=10.0, lng=106.0, radius=200)
    _link_admin_employee(client, token)
    # VÀO rồi RA cùng ngày (VN) → 1 ngày công có đủ giờ vào/ra
    client.post("/api/attendance/check", json={"latitude": 10.0, "longitude": 106.0}, headers=_h(token))
    client.post("/api/attendance/check", json={"latitude": 10.0, "longitude": 106.0}, headers=_h(token))

    year, month = _vn_year_month()
    ts = client.get(f"/api/attendance/timesheet?year={year}&month={month}", headers=_h(token)).json()
    assert ts["year"] == year and ts["month"] == month
    assert ts["days_in_month"] in (28, 29, 30, 31)
    row = next(r for r in ts["rows"] if r["employee_name"] == "NV Admin")
    assert row["total_days"] == 1
    # đúng 1 ô ngày có giờ vào + giờ ra
    day = next(iter(row["days"].values()))
    assert day["first_in"] and day["last_out"] and day["hours"] is not None

    # CSV: 200 + text/csv + có tên nhân viên
    csv_resp = client.get(f"/api/attendance/timesheet.csv?year={year}&month={month}", headers=_h(token))
    assert csv_resp.status_code == 200
    assert "text/csv" in csv_resp.headers["content-type"]
    assert "NV Admin" in csv_resp.text


def test_timesheet_forbidden_without_permission(client):
    token = _sales_token()
    year, month = _vn_year_month()
    assert client.get(f"/api/attendance/timesheet?year={year}&month={month}", headers=_h(token)).status_code == 403


# --- self-service "Công của tôi" + scope theo phòng -------------------------


def _make_worker(username: str, dept_id: int) -> int:
    """Thợ: vai TRỐNG TRƠN (không ô quản trị nào) — chỉ tự phục vụ sau khi nối hồ sơ NV.

    Từ 10/08/2026 tự phục vụ là MỘT Ô QUYỀN chứ không còn là luật ngầm "ai đăng nhập cũng làm
    được". Vai mới sinh ra đã có sẵn ô đó (xem `RoleRepository.O_MAC_DINH`), nên ở đây chỉ cần gán
    một vai trống — giống ngoài đời, mọi người lao động đều thuộc một vai nào đó.

    Trước đây fixture để `role_id=None` (không vai): nay không vai = không ô nào = không tự chấm
    công được, đúng ý đồ Luật 1."""
    db = SessionLocal()
    try:
        users, roles = UserRepository(db), RoleRepository(db)
        vai = roles.get_by_name_and_department("Thợ trống quyền", dept_id)
        if vai is None:
            vai = roles.create(name="Thợ trống quyền", department_id=dept_id)
            # Từ 15/08/2026 (mg 0194): ô `self_service` đã bỏ, phần "của tôi" đi theo ô của CHÍNH
            # màn đó. Thợ phải được cấp `cham_cong` mới bấm giờ được — `can_read` mở màn + ba tab
            # của mình, `can_create` là ô Thao tác (ghi thì phải có ô, kể cả ghi đơn của mình).
            # KHÔNG có `can_view_timesheet` ⇒ vẫn không thấy lưới công cả xưởng.
            roles.set_permission(role_id=vai.id, module_key="cham_cong", scope="own",
                                 can_read=True, can_create=True)
        u = users.get_by_username(username) or users.create(
            username=username, name=username, password_hash=hash_password("x"))
        users.set_assignment(u, department_id=dept_id, role_id=vai.id, is_active=True)
        return u.id
    finally:
        db.close()


def _dept_hr_token(dept_name: str) -> str:
    """User trong phòng `dept_name` với nhan_su READ scope=department (HR của phòng đó)."""
    db = SessionLocal()
    try:
        dept = DepartmentRepository(db).get_by_name(dept_name)
        roles = RoleRepository(db)
        role = roles.get_by_name_and_department("HR-scope", dept.id) or roles.create(
            name="HR-scope", department_id=dept.id)
        # Đọc nhật ký + bảng công là màn Chấm công ⇒ khoá `cham_cong`.
        # `can_view_log`: tab Nhật ký chấm công tách thành ô riêng 11/08/2026 — HR của phòng
        # vẫn phải đọc được nhật ký của phòng mình.
        # `can_view_timesheet`: Bảng công tháng tách thành ô riêng 15/08/2026 (mg 0194) — `can_read`
        # nay chỉ mở màn + ba tab CỦA TÔI; muốn xem lưới cả phòng phải có ô này.
        roles.set_permission(role_id=role.id, module_key="cham_cong", can_read=True,
                             can_view_log=True, can_view_timesheet=True, scope="department")
        users = UserRepository(db)
        u = users.get_by_username(f"hr-{dept.id}") or users.create(
            username=f"hr-{dept.id}", name="HR", password_hash=hash_password("x"))
        users.set_assignment(u, department_id=dept.id, role_id=role.id, is_active=True)
        return create_access_token(str(u.id))
    finally:
        db.close()


def _link_employee(client, token, *, full_name, dept_id, user_id, assign_shift: bool = True) -> int:
    emp = client.post(
        "/api/employees",
        json={"full_name": full_name, "department_id": dept_id, "hire_date": "2020-01-01"},
        headers=_h(token),
    ).json()["employee"]
    client.post(f"/api/employees/{emp['id']}/account", json={"user_id": user_id}, headers=_h(token))
    if assign_shift:
        _assign_test_shift(client, token, emp["id"])
    return emp["id"]


def test_me_timesheet_self_service(client):
    token = _admin_token(client)
    _make_location(client, token, lat=10.0, lng=106.0, radius=200)
    dept_a = _dept_id("Hành chính nhân sự")
    worker = _make_worker("worker-me", dept_a)
    _link_employee(client, token, full_name="NV Worker", dept_id=dept_a, user_id=worker)
    wt = create_access_token(str(worker))
    assert client.post("/api/attendance/check", json={"latitude": 10.0, "longitude": 106.0}, headers=_h(wt)).json()["success"]

    year, month = _vn_year_month()
    # NV thường (KHÔNG có quyền nhan_su) vẫn xem được công CỦA MÌNH
    mine = client.get(f"/api/attendance/me/timesheet?year={year}&month={month}", headers=_h(wt))
    assert mine.status_code == 200
    rows = mine.json()["rows"]
    assert len(rows) == 1 and rows[0]["employee_name"] == "NV Worker"
    # nhưng KHÔNG xem được bảng công toàn xưởng
    assert client.get(f"/api/attendance/timesheet?year={year}&month={month}", headers=_h(wt)).status_code == 403
    # tài khoản KHÔNG nối hồ sơ NV (dữ liệu cũ) gọi /me/timesheet → 400
    _orphan_admin_account()
    assert client.get(f"/api/attendance/me/timesheet?year={year}&month={month}", headers=_h(token)).status_code == 400


def test_logs_and_timesheet_department_scope(client):
    token = _admin_token(client)
    _make_location(client, token, lat=10.0, lng=106.0, radius=200)
    dept_a = _dept_id("Hành chính nhân sự")
    dept_b = _dept_id("Kinh doanh")

    ua = _make_worker("wa", dept_a)
    _link_employee(client, token, full_name="NV A", dept_id=dept_a, user_id=ua)
    client.post("/api/attendance/check", json={"latitude": 10.0, "longitude": 106.0}, headers=_h(create_access_token(str(ua))))

    ub = _make_worker("wb", dept_b)
    eb_id = _link_employee(client, token, full_name="NV B", dept_id=dept_b, user_id=ub)
    client.post("/api/attendance/check", json={"latitude": 10.0, "longitude": 106.0}, headers=_h(create_access_token(str(ub))))

    year, month = _vn_year_month()
    hr = _dept_hr_token("Hành chính nhân sự")  # HR phòng A, scope=department

    # /logs: chỉ thấy NV phòng A
    names = {l["employee_name"] for l in client.get("/api/attendance/logs", headers=_h(hr)).json()["items"]}
    assert "NV A" in names and "NV B" not in names
    # chỉ định employee_id ngoài scope cũng KHÔNG rò
    assert client.get(f"/api/attendance/logs?employee_id={eb_id}", headers=_h(hr)).json()["items"] == []
    # /timesheet: chỉ thấy NV phòng A
    ts_names = {r["employee_name"] for r in client.get(f"/api/attendance/timesheet?year={year}&month={month}", headers=_h(hr)).json()["rows"]}
    assert "NV A" in ts_names and "NV B" not in ts_names

    # admin (scope=all) thấy cả hai
    all_names = {l["employee_name"] for l in client.get("/api/attendance/logs", headers=_h(token)).json()["items"]}
    assert {"NV A", "NV B"} <= all_names


def _vn_today_str() -> str:
    from datetime import datetime, timedelta, timezone
    return datetime.now(timezone(timedelta(hours=7))).strftime("%Y-%m-%d")


def test_adjust_punch_recompute_and_rbac(client):
    token = _admin_token(client)
    _make_location(client, token, lat=10.0, lng=106.0, radius=200)
    shift = client.post("/api/attendance/shifts",
                        json={"name": "HC", "start_time": "00:00", "end_time": "23:59"},
                        headers=_h(token)).json()
    emp_id = _link_admin_employee(client, token)
    client.put(f"/api/employees/{emp_id}/shift", json={"default_shift_id": shift["id"]}, headers=_h(token))
    client.post("/api/attendance/check", json={"latitude": 10.0, "longitude": 106.0}, headers=_h(token))  # VÀO, thiếu RA

    today = _vn_today_str()
    d = client.get(f"/api/attendance/day?employee_id={emp_id}&date={today}", headers=_h(token)).json()
    assert len(d["punches"]) == 1  # chỉ có VÀO thật

    # HCNS (admin) chấm bù RA 17:00 với fault_party
    adj = client.post("/api/attendance/adjust", json={
        "employee_id": emp_id, "date": today, "check_type": "out", "time": "17:00",
        "reason": "NV quên chấm ra", "fault_party": "nv_quen"}, headers=_h(token)).json()
    manual = [p for p in adj["punches"] if p["is_manual"]]
    assert len(adj["punches"]) == 2 and len(manual) == 1
    assert manual[0]["fault_party"] == "nv_quen" and manual[0]["adjust_reason"] == "NV quên chấm ra"

    # reason bắt buộc → bị chặn (422 schema / 400 service)
    assert client.post("/api/attendance/adjust", json={
        "employee_id": emp_id, "date": today, "check_type": "out", "time": "18:00",
        "reason": ""}, headers=_h(token)).status_code in (400, 422)

    # RBAC: user không có quyền adjust → 403
    st = _sales_token()
    assert client.post("/api/attendance/adjust", json={
        "employee_id": emp_id, "date": today, "check_type": "out", "time": "17:00",
        "reason": "x"}, headers=_h(st)).status_code == 403

    # xóa punch bù → còn 1 punch
    dele = client.delete(f"/api/attendance/logs/{manual[0]['id']}?employee_id={emp_id}&date={today}", headers=_h(token))
    assert dele.status_code == 200 and len(dele.json()["punches"]) == 1
    # không xóa được punch GPS gốc (không phải manual) → 400
    gps_id = dele.json()["punches"][0]["id"]
    assert client.delete(f"/api/attendance/logs/{gps_id}?employee_id={emp_id}&date={today}", headers=_h(token)).status_code == 400


def test_adjust_request_flow_and_kpi(client):
    token = _admin_token(client)
    _make_location(client, token, lat=10.0, lng=106.0, radius=200)
    dept_a = _dept_id("Hành chính nhân sự")
    worker = _make_worker("wreq", dept_a)
    emp_id = _link_employee(client, token, full_name="NV Req", dept_id=dept_a, user_id=worker)
    wt = create_access_token(str(worker))
    today = _vn_today_str()

    # NV gửi yêu cầu chỉnh công (self-service, không cần quyền)
    r = client.post("/api/attendance/me/adjust-request", json={
        "date": today, "check_type": "out", "suggested_time": "17:00", "reason": "Quên chấm ra"}, headers=_h(wt))
    assert r.status_code == 200 and r.json()["status"] == "pending"
    req_id = r.json()["id"]
    assert any(x["id"] == req_id for x in client.get("/api/attendance/me/adjust-requests", headers=_h(wt)).json()["items"])

    # HCNS thấy trong danh sách chờ + KPI pending ≥ 1
    assert any(x["id"] == req_id for x in client.get("/api/attendance/adjust-requests", headers=_h(token)).json()["items"])
    assert client.get("/api/attendance/kpi", headers=_h(token)).json()["pending_requests"] >= 1

    # NV không có quyền adjust → không duyệt được
    assert client.post(f"/api/attendance/adjust-requests/{req_id}/approve",
                       json={"fault_party": "nv_quen"}, headers=_h(wt)).status_code == 403

    # HCNS duyệt → sinh punch chấm bù, status approved
    ap = client.post(f"/api/attendance/adjust-requests/{req_id}/approve",
                     json={"fault_party": "nv_quen"}, headers=_h(token))
    assert ap.status_code == 200 and ap.json()["status"] == "approved"
    d = client.get(f"/api/attendance/day?employee_id={emp_id}&date={today}", headers=_h(token)).json()
    assert any(p["is_manual"] and p["check_type"] == "out" for p in d["punches"])
    assert client.get("/api/attendance/kpi", headers=_h(token)).json()["pending_requests"] == 0

    # duyệt lại yêu cầu đã xử lý → 400
    assert client.post(f"/api/attendance/adjust-requests/{req_id}/approve",
                       json={"fault_party": "nv_quen"}, headers=_h(token)).status_code == 400


# --- RBAC -------------------------------------------------------------------


def test_locations_config_forbidden_without_permission(client):
    token = _sales_token()
    assert client.get("/api/attendance/locations", headers=_h(token)).status_code == 403
    assert client.post(
        "/api/attendance/locations",
        json={"name": "x", "latitude": 10, "longitude": 10, "radius_m": 100},
        headers=_h(token),
    ).status_code == 403


# --- hạn mức chỉnh công (chủ 27/07/2026: tối đa N ngày/tháng) ----------------


def _shift_from_month_start(client, token, employee_id: int, *, eff: date | None = None) -> None:
    """Gán ca có hiệu lực từ NGÀY 1 tháng này — `_assign_test_shift` mặc định lấy hiệu lực từ
    HÔM NAY, nên các ngày đầu tháng sẽ 'chưa được gán ca' và yêu cầu chỉnh công bị chặn trước
    khi chạm tới luật hạn mức.

    `eff` để lùi mốc xa hơn khi kịch bản chạm sang tháng trước."""
    shift_id = _ensure_test_shift(client, token)
    today = date.today()
    eff = eff or date(today.year, today.month, 1)
    # Ép `hire_date` qua repo: mốc ca KHÔNG được trước ngày vào làm, mà hồ sơ admin do
    # `backfill_employee_profiles` sinh ra có ngày vào làm là hôm nay.
    db = SessionLocal()
    try:
        repo = EmployeeRepository(db)
        repo.update(repo.get_by_id(employee_id), hire_date=date(2020, 1, 1))
    finally:
        db.close()
    r = client.put(f"/api/employees/{employee_id}/shift",
                   json={"default_shift_id": shift_id, "effective_from": eff.isoformat()},
                   headers=_h(token))
    assert r.status_code == 200, r.text
    return eff


def _set_adjust_limit(client, token, n: int) -> None:
    r = client.put("/api/luong/params", json={"adjust_max_per_month": n}, headers=_h(token))
    assert r.status_code == 200, r.text
    assert r.json()["adjust_max_per_month"] == n


def _req_adjust(client, token, *, day: str, check_type: str = "in", expect=200):
    r = client.post("/api/attendance/me/adjust-request",
                    json={"date": day, "check_type": check_type,
                          "suggested_time": "08:00", "reason": "quên chấm"},
                    headers=_h(token))
    assert r.status_code == expect, r.text
    return r


def _quota(client, token) -> dict:
    return client.get("/api/attendance/me/adjust-requests", headers=_h(token)).json()["quota"]


def _this_month(day: int) -> str:
    """Ngày trong THÁNG HIỆN TẠI — hạn mức đếm theo tháng của `work_date`, và `/me/adjust-requests`
    trả quota của tháng hiện tại, nên test phải bám tháng hiện tại mới đọc được số."""
    today = date.today()
    return date(today.year, today.month, min(day, 28)).isoformat()


def test_han_muc_chinh_cong_chan_khi_het_luot(client):
    """5 ngày khác nhau thì OK; ngày thứ 6 bị chặn kèm SỐ cụ thể."""
    token = _admin_token(client)
    _shift_from_month_start(client, token, _link_admin_employee(client, token))
    _set_adjust_limit(client, token, 5)

    for d in (1, 2, 3, 4, 5):
        _req_adjust(client, token, day=_this_month(d))
    q = _quota(client, token)
    assert q["limit"] == 5 and q["used"] == 5 and q["remaining"] == 0

    r = _req_adjust(client, token, day=_this_month(6), expect=400)
    assert "5/5" in r.json()["detail"], r.json()["detail"]


def test_cung_mot_ngay_khong_ton_them_luot(client):
    """⭐ 1 NGÀY = 1 lượt. Quên cả giờ VÀO lẫn giờ RA phải gửi 2 đơn — vẫn chỉ tính 1 lượt,
    nếu không thì '5 lần' thực chất chỉ còn 2,5 ngày."""
    token = _admin_token(client)
    _shift_from_month_start(client, token, _link_admin_employee(client, token))
    _set_adjust_limit(client, token, 1)

    _req_adjust(client, token, day=_this_month(10), check_type="in")
    assert _quota(client, token)["used"] == 1
    # Hết hạn mức (1/1) nhưng CÙNG ngày đó vẫn gửi được lượt RA.
    _req_adjust(client, token, day=_this_month(10), check_type="out")
    assert _quota(client, token)["used"] == 1        # KHÔNG tăng
    # Ngày KHÁC thì mới bị chặn.
    _req_adjust(client, token, day=_this_month(11), expect=400)


def test_tu_choi_va_huy_tra_lai_luot(client):
    """Đơn bị TỪ CHỐI / ĐÃ HỦY nhả lại lượt; đơn ĐÃ DUYỆT thì vẫn giữ chỗ."""
    token = _admin_token(client)
    _shift_from_month_start(client, token, _link_admin_employee(client, token))
    _set_adjust_limit(client, token, 2)

    r1 = _req_adjust(client, token, day=_this_month(3)).json()
    r2 = _req_adjust(client, token, day=_this_month(4)).json()
    _req_adjust(client, token, day=_this_month(5), expect=400)

    # Từ chối r1 → nhả 1 lượt.
    assert client.post(f"/api/attendance/adjust-requests/{r1['id']}/reject",
                       json={"note": "không hợp lệ"}, headers=_h(token)).status_code == 200
    assert _quota(client, token)["used"] == 1
    r3 = _req_adjust(client, token, day=_this_month(5)).json()

    # Hủy r3 (NV tự hủy) → nhả tiếp.
    assert client.post(f"/api/attendance/me/adjust-requests/{r3['id']}/cancel",
                       headers=_h(token)).status_code == 200
    assert _quota(client, token)["used"] == 1

    # DUYỆT r2 → vẫn chiếm chỗ (không nhả).
    assert client.post(f"/api/attendance/adjust-requests/{r2['id']}/approve",
                       json={"fault_party": "nv_quen"}, headers=_h(token)).status_code == 200
    assert _quota(client, token)["used"] == 1
    _req_adjust(client, token, day=_this_month(6))          # còn đúng 1 lượt
    _req_adjust(client, token, day=_this_month(7), expect=400)


def test_han_muc_0_la_khong_gioi_han(client):
    """Đường thoát: đặt 0 ⇒ tắt luật (máy chấm công hỏng cả tuần thì mở khoá được)."""
    token = _admin_token(client)
    _shift_from_month_start(client, token, _link_admin_employee(client, token))
    _set_adjust_limit(client, token, 0)
    for d in range(1, 9):
        _req_adjust(client, token, day=_this_month(d))
    q = _quota(client, token)
    assert q["limit"] == 0 and q["remaining"] is None


def test_hcns_cham_bu_truc_tiep_khong_bi_gioi_han(client):
    """Chốt của chủ: chỉ giới hạn ĐƠN của NV. HCNS chấm bù tay không giới hạn và KHÔNG ăn lượt
    của NV — máy chấm hỏng cả ngày thì HCNS phải sửa được cho cả tổ."""
    token = _admin_token(client)
    eid = _link_admin_employee(client, token)
    _shift_from_month_start(client, token, eid)
    _set_adjust_limit(client, token, 1)
    _req_adjust(client, token, day=_this_month(2))           # NV dùng hết 1/1

    for d in range(10, 18):
        assert client.post("/api/attendance/adjust",
                           json={"employee_id": eid, "date": _this_month(d), "check_type": "in",
                                 "time": "08:00", "reason": "máy hỏng"},
                           headers=_h(token)).status_code == 200
    assert _quota(client, token)["used"] == 1                # lượt của NV không đổi


def test_han_muc_tinh_theo_thang_cua_ngay_cong(client):
    """Hạn mức gắn với THÁNG CỦA NGÀY CÔNG bị sửa, không phải tháng gửi đơn.

    Nếu đếm theo ngày gửi thì mùng 1 gửi bù cho tháng trước sẽ ăn mất lượt của tháng mới."""
    token = _admin_token(client)
    # Mốc ca phải bắt đầu từ THÁNG TRƯỚC — kịch bản dưới gửi đơn cho tháng trước, không có ca
    # ngày đó thì bị chặn ở `_require_shift_on_day` trước khi chạm luật hạn mức.
    thang_truoc = (date.today().replace(day=1) - timedelta(days=1)).replace(day=1)
    _shift_from_month_start(client, token, _link_admin_employee(client, token), eff=thang_truoc)
    _set_adjust_limit(client, token, 2)

    _req_adjust(client, token, day=_this_month(3))
    _req_adjust(client, token, day=_this_month(4))
    _req_adjust(client, token, day=_this_month(5), expect=400)   # tháng này hết lượt

    # Ngày thuộc THÁNG TRƯỚC vẫn gửi được — hạn mức riêng từng tháng.
    # (Trước 31/07/2026 test này dùng THÁNG SAU. Đó chính là cái vô lý chủ bắt được — không ai
    # "quên chấm" một ngày chưa tới — và `_require_not_future` nay chặn. Đổi sang tháng trước
    # đúng với kịch bản mà docstring vẫn luôn mô tả: mùng 1 gửi bù cho tháng trước.)
    _req_adjust(client, token, day=thang_truoc.replace(day=5).isoformat())


# --- Bảng công phải hiện ĐỦ NGƯỜI, không chỉ người đã chấm công -------------
#
# Trước 31/07/2026 `monthly_timesheet` chỉ dựng hàng cho ai có dấu vết (lượt bấm / đơn phép /
# phiếu giờ). Ai cả tháng không chấm buổi nào thì KHÔNG có hàng nào — chủ mở "Công của tôi" thấy
# trắng, HCNS không soi ra người vắng cả tháng, và họ mất luôn công lễ.


def _nv_trang(client, token, *, ten: str, dept: str = "Hành chính nhân sự") -> tuple[int, str]:
    """NV có hồ sơ + tài khoản nhưng KHÔNG lượt bấm, KHÔNG đơn gì. → (employee_id, token)."""
    did = _dept_id(dept)
    uid = _make_worker(f"u-{ten.lower().replace(' ', '-')}", did)
    eid = _link_employee(client, token, full_name=ten, dept_id=did, user_id=uid)
    return eid, create_access_token(str(uid))


def test_NV_khong_dau_vet_VAN_co_hang_tren_cong_cua_toi(client):
    """⭐ Đúng cái chủ báo: mở "Công của tôi" thấy trắng vì không bấm vân tay.

    Hàng này CHÍNH LÀ thứ mở khoá cả khối lịch bên FE (`ChamCongPage` chặn lịch sau `row`) — không
    có hàng thì không có ô ngày nào để bấm, mà nút xin chỉnh công lại nằm trên ô ngày: người quên
    chấm cả tháng thành người DUY NHẤT không xin sửa công được."""
    token = _admin_token(client)
    _nv_trang(client, token, ten="NV Chua Cham")
    _, wt = _nv_trang(client, token, ten="NV Trang")

    year, month = _vn_year_month()
    r = client.get(f"/api/attendance/me/timesheet?year={year}&month={month}", headers=_h(wt))
    assert r.status_code == 200
    rows = r.json()["rows"]
    assert len(rows) == 1 and rows[0]["employee_name"] == "NV Trang"
    assert rows[0]["total_days"] == 0     # vẫn nói thật: chưa chấm buổi nào
    assert r.json()["days_in_month"] in (28, 29, 30, 31)


def test_bang_cong_HCNS_hien_du_nguoi_va_loc_dung_phong(client):
    """HCNS phải soi ra được ai cả tháng không chấm công — trước đây họ biến mất khỏi bảng."""
    token = _admin_token(client)
    _nv_trang(client, token, ten="NV Ho So A", dept="Hành chính nhân sự")
    _nv_trang(client, token, ten="NV Kinh Doanh B", dept="Kinh doanh")

    year, month = _vn_year_month()
    tat_ca = client.get(f"/api/attendance/timesheet?year={year}&month={month}",
                        headers=_h(token)).json()["rows"]
    ten = {r["employee_name"] for r in tat_ca}
    assert {"NV Ho So A", "NV Kinh Doanh B"} <= ten

    # Lọc phòng vẫn phải kín: không rò người tổ khác.
    kd = client.get(f"/api/attendance/timesheet?year={year}&month={month}"
                    f"&department_id={_dept_id('Kinh doanh')}", headers=_h(token)).json()["rows"]
    ten_kd = {r["employee_name"] for r in kd}
    assert "NV Kinh Doanh B" in ten_kd and "NV Ho So A" not in ten_kd


def _cho_nghi_viec(employee_id: int, ngay: date) -> None:
    db = SessionLocal()
    try:
        repo = EmployeeRepository(db)
        repo.update(repo.get_by_id(employee_id), resign_date=ngay)
    finally:
        db.close()


def test_KHONG_lam_mat_hang_cua_NV_nghi_viec_con_log(client):
    """⭐ Tập hàng là phép HỢP, không phải phép THAY.

    NV đã nghỉ việc từ tháng trước mà còn lượt bấm sót lại trong tháng này thì VẪN phải giữ hàng.
    Đổi 'biên chế HỢP dấu vết' thành 'chỉ biên chế' là làm biến mất hàng đang thấy — đây là thứ
    canh cho tính thuần-cộng-thêm của thay đổi."""
    token = _admin_token(client)
    _make_location(client, token, lat=10.0, lng=106.0, radius=200)
    dept = _dept_id("Hành chính nhân sự")
    uid = _make_worker("u-nghi-con-log", dept)
    eid = _link_employee(client, token, full_name="NV Nghi Con Log", dept_id=dept, user_id=uid)
    wt = create_access_token(str(uid))
    assert client.post("/api/attendance/check", json={"latitude": 10.0, "longitude": 106.0},
                       headers=_h(wt)).json()["success"]

    year, month = _vn_year_month()
    # Nghỉ việc TRƯỚC ngày 1 tháng này ⇒ rơi khỏi biên chế, chỉ còn nhánh "có dấu vết" giữ lại.
    _cho_nghi_viec(eid, date(year, month, 1) - timedelta(days=1))

    rows = client.get(f"/api/attendance/timesheet?year={year}&month={month}",
                      headers=_h(token)).json()["rows"]
    assert any(r["employee_name"] == "NV Nghi Con Log" for r in rows), \
        "lượt bấm còn đó mà hàng biến mất = làm mất dữ liệu đang hiển thị"


def test_NV_nghi_viec_thang_truoc_KHONG_len_bang(client):
    """⭐ Không kéo người lạ vào Lương.

    `monthly_timesheet` nuôi `metrics_map` → bảng lương. NV nghỉ việc từ tháng trước, không dấu
    vết gì, phải KHÔNG có hàng — có hàng là `bool(m)` bên Lương thành true và họ bị lôi ngược vào
    kỳ lương đã đóng."""
    token = _admin_token(client)
    eid, _ = _nv_trang(client, token, ten="NV Da Nghi")
    year, month = _vn_year_month()
    _cho_nghi_viec(eid, date(year, month, 1) - timedelta(days=1))

    rows = client.get(f"/api/attendance/timesheet?year={year}&month={month}",
                      headers=_h(token)).json()["rows"]
    assert all(r["employee_name"] != "NV Da Nghi" for r in rows)


def test_cong_le_toi_tay_nguoi_khong_cham_cong(client):
    """Quyết định của chủ 31/07/2026: còn biên chế thì hưởng công lễ, KHÔNG cần bấm vân tay.

    Luật này (`_in_headcount_on`) vốn đã viết trong `monthly_timesheet`, nhưng nhánh `emp_holidays`
    chỉ chạy cho ai đã có hàng — nên người không chấm công buổi nào mất trắng công lễ. Đây là
    thay đổi chạm TIỀN, phải có test kẻo lần sau ai đó 'tối ưu' đi mất trong im lặng."""
    token = _admin_token(client)
    _, wt = _nv_trang(client, token, ten="NV Huong Le")

    # 02/09/2026 (thứ Tư) — Quốc khánh, có sẵn trong lịch seed.
    r = client.get("/api/attendance/me/timesheet?year=2026&month=9", headers=_h(wt)).json()
    row = r["rows"][0]
    assert row["total_days"] == 0                     # không bấm buổi nào
    o_le = row["days"]["2"]
    assert o_le["holiday"] is True and o_le["cong"] == 1.0
    assert row["total_cong"] == 1.0                   # công lễ tới tay, không phải None/0


# --- Ô ngày phải TỰ NÓI loại ngày: lễ · nghỉ tuần · off1x -------------------
#
# Chủ báo 17/08/2026: công nhân đi làm ngày lễ, mở "Lịch công của tôi" thấy đúng chữ "Công: 1" —
# y hệt một ngày thường — nên tưởng mình bị trả thiếu, trong khi Lương đang trả 4× cho ngày đó.
# Gốc là ô ngày chỉ mang MỘT cờ `holiday`, và nó chỉ được gắn ở nhánh KHÔNG chấm công; ngày nghỉ
# tuần / ngày `off1x` thì không có cờ nào cả. Ba cờ dưới đây là ĐẦU VÀO DUY NHẤT để màn hình phân
# biệt bốn loại ngày — mất một cờ là màn hình lại nói dối về tiền.

NAM_LN, THANG_LN = 2026, 6          # tháng 6/2026: mùng 1 là thứ Hai ⇒ 14 là Chủ nhật


def _nv_ca_hanh_chinh(client, token, *, ten: str) -> tuple[int, str]:
    """NV + tài khoản riêng, ca 08:00–17:00 hiệu lực từ 2020 ⇒ bấm 08:00→17:00 là TRÒN 1 công.

    Không dùng `_nv_trang`: ca kiểm thử mặc định là 00:00–23:59 (khung 1439') nên chấm 8h–17h
    ra công lẻ, che mất thứ đang đo."""
    did = _dept_id("Hành chính nhân sự")
    uid = _make_worker(f"u-{ten.lower().replace(' ', '-')}", did)
    eid = _link_employee(client, token, full_name=ten, dept_id=did, user_id=uid,
                         assign_shift=False)
    items = client.get("/api/attendance/shifts", headers=_h(token)).json()["items"]
    ca = next((s for s in items if s["name"] == "Ca giờ hành chính LN"), None)
    if ca is None:
        ca = client.post("/api/attendance/shifts",
                         json={"name": "Ca giờ hành chính LN", "start_time": "08:00",
                               "end_time": "17:00"}, headers=_h(token)).json()
    r = client.put(f"/api/employees/{eid}/shift",
                   json={"default_shift_id": ca["id"], "effective_from": "2020-01-01"},
                   headers=_h(token))
    assert r.status_code == 200, r.text
    return eid, create_access_token(str(uid))


def _bam_ca_chinh(eid: int, ngay: int) -> None:
    """Một cặp VÀO/RA 08:00–17:00 giờ VN ghi thẳng qua repo — API `check` chỉ chấm được 'bây giờ'."""
    db = SessionLocal()
    try:
        repo = AttendanceRepository(db)
        for kieu, gio_vn in (("in", 8), ("out", 17)):
            phut_utc = gio_vn * 60 - 7 * 60
            repo.create_log(employee_id=eid, check_type=kieu, within_range=True,
                            checked_at=datetime(NAM_LN, THANG_LN, ngay,
                                                phut_utc // 60, phut_utc % 60, tzinfo=timezone.utc))
    finally:
        db.close()


def _khai_ngay_dac_biet(client, token, ngay: int, *, kind: str, ten: str) -> None:
    r = client.post("/api/calendar/special-days",
                    json={"day": f"{NAM_LN}-{THANG_LN:02d}-{ngay:02d}", "kind": kind,
                          "name": ten, "is_paid": kind == "off"},
                    headers=_h(token))
    assert r.status_code in (200, 201), r.text


def test_o_ngay_mang_du_co_le_nghi_tuan_va_off1x(client):
    """⭐ Bốn loại ngày, bốn dấu khác nhau — và chúng LOẠI TRỪ NHAU.

    Thứ tự phải khớp đúng nhánh tính tiền (`plain > holiday > restday`): ngày `off1x` rơi vào
    Chủ nhật mà bị gắn `restday` là màn hình hứa 2× trong khi Lương trả 1×."""
    token = _admin_token(client)
    eid, wt = _nv_ca_hanh_chinh(client, token, ten="NV Loai Ngay")
    _khai_ngay_dac_biet(client, token, 10, kind="off", ten="Lễ thử")        # thứ Tư
    _khai_ngay_dac_biet(client, token, 11, kind="off1x", ten="Nghỉ 1x thử")  # thứ Năm
    for d in (9, 10, 11, 14):        # thường · lễ · off1x · Chủ nhật
        _bam_ca_chinh(eid, d)

    r = client.get(f"/api/attendance/me/timesheet?year={NAM_LN}&month={THANG_LN}", headers=_h(wt))
    assert r.status_code == 200, r.text
    row = r.json()["rows"][0]
    o = row["days"]

    def co(d: int) -> tuple[bool, bool, bool]:
        return (o[str(d)]["holiday"], o[str(d)]["restday"], o[str(d)]["plain"])

    assert o["9"]["cong"] == 1.0 and co(9) == (False, False, False), "ngày thường không đeo cờ nào"
    assert co(10) == (True, False, False), "ngày lễ ĐI LÀM phải mang cờ lễ (nhánh cũ chỉ gắn khi NGHỈ)"
    assert co(11) == (False, False, True), "ngày off1x đi làm: 1× phẳng, KHÔNG phải premium"
    assert co(14) == (False, True, False), "Chủ nhật đi làm phải nhận ra được, trước đây trắng trơn"

    # Ba cột tổng cũng phải ra tới API — cột "Công đặc biệt" của Bảng công tháng đọc thẳng chúng.
    assert row["holiday_cong"] == 1.0 and row["restday_cong"] == 1.0 and row["plain_cong"] == 1.0


def test_he_so_ngay_doc_tu_cau_hinh_luong_le_cong_1_chu_nhat_thi_khong(client):
    """⭐ Chỗ dễ sai nhất: LỄ = 1 + hệ số, NGHỈ TUẦN = hệ số (KHÔNG cộng 1).

    Vì tiền cố ý tính hai kiểu (`payroll_service._compute`): ngày lễ đã có sẵn 1 công lương Đ112
    dù nghỉ ở nhà nên Đ98.1.c cộng TRỌN 300% ⇒ 4×; Chủ nhật nghỉ ở nhà thì không đồng nào, phần 1×
    chính là tiền đi làm ⇒ chỉ 2×. Cộng 1 cho cả hai là màn hình hứa 3× mà phiếu lương trả 2×."""
    token = _admin_token(client)
    _, wt = _nv_trang(client, token, ten="NV He So")
    duong = f"/api/attendance/me/timesheet?year={NAM_LN}&month={THANG_LN}"

    mac_dinh = client.get(duong, headers=_h(wt)).json()["he_so_ngay"]
    assert mac_dinh == {"le": 4.0, "nghi_tuan": 2.0, "off1x": 1.0}

    # Đổi Cấu hình lương ⇒ số trên ô lịch phải đi theo (nếu ai đó viết cứng "4" thì đỏ ở đây).
    # Hai hệ số khác nhau + khác mặc định ⇒ nhầm công thức nào cũng lộ.
    r = client.put("/api/luong/params",
                   json={"holiday_work_multiplier": 4, "restday_work_multiplier": 2.5},
                   headers=_h(token))
    assert r.status_code == 200, r.text
    assert client.get(duong, headers=_h(wt)).json()["he_so_ngay"] == {
        "le": 5.0, "nghi_tuan": 2.5, "off1x": 1.0}


def test_giao_dien_that_su_doc_co_loai_ngay_va_he_so():
    """Máy chủ trả cờ mà giao diện quên đọc thì màn hình vẫn nói "Công: 1" — tức là bản vá này
    KHÔNG giải quyết gì cả. Khuôn sai "máy chủ đổi, giao diện quên" đã lặp nhiều vòng ở repo
    (xem `test_com_tang_ca.test_giao_dien_that_su_hien_va_khai_duoc`)."""
    from pathlib import Path

    fe = Path(__file__).resolve().parents[2] / "frontend" / "src"
    assert "he_so_ngay" in (fe / "api" / "client.ts").read_text(encoding="utf-8")
    tsx = (fe / "pages" / "ChamCongPage.tsx").read_text(encoding="utf-8")
    for chu in ("day.restday", "day.plain", "heSo.le", "heSo.nghi_tuan",
                "→ tính", "Công đặc biệt"):
        assert chu in tsx, f"giao diện chưa dùng {chu!r} — ô lịch vẫn không nói được số công"


# --- Không chấm công cho ngày CHƯA TỚI --------------------------------------
#
# Chủ phát hiện 31/07/2026: đang ngày 31/7 mà vẫn gửi được yêu cầu chỉnh công cho 02/8.
# "Xin chỉnh công" nghĩa là "tôi QUÊN chấm hôm đó" — không ai quên một ngày chưa xảy ra.
# `_ghim_hom_nay` ghim hôm nay = NGÀY CUỐI THÁNG ⇒ "ngày mai" = mùng 1 tháng sau.


def _hom_nay() -> str:
    return _ngay_cuoi_thang().isoformat()


def _ngay_mai() -> str:
    return (_ngay_cuoi_thang() + timedelta(days=1)).isoformat()


def test_xin_chinh_cong_ngay_MAI_bi_chan_va_KHONG_ton_han_muc(client):
    """⭐ Chặn phải đứng TRƯỚC `adjust_quota`.

    Thiệt hại thật của lỗi này không phải cái đơn vô nghĩa mà là HẠN MỨC: `adjust_quota` đếm cả
    đơn đang chờ, nên NV đốt sạch lượt của tháng bằng những ngày chưa tới rồi hết cửa sửa ngày
    quên thật. Chặn sau khi trừ hạn mức thì coi như không chặn."""
    token = _admin_token(client)
    _shift_from_month_start(client, token, _link_admin_employee(client, token))
    _set_adjust_limit(client, token, 5)
    truoc = _quota(client, token)["used"]

    r = _req_adjust(client, token, day=_ngay_mai(), expect=400)
    assert "chưa tới" in r.json()["detail"], r.json()["detail"]
    assert _quota(client, token)["used"] == truoc, "đơn bị chặn mà vẫn ăn mất một lượt"


def test_xin_chinh_cong_HOM_NAY_van_gui_duoc(client):
    """Canh cho việc chặn KHÔNG nới quá tay: quên chấm sáng nay, chiều xin sửa là chuyện thường."""
    token = _admin_token(client)
    _shift_from_month_start(client, token, _link_admin_employee(client, token))
    _set_adjust_limit(client, token, 5)
    _req_adjust(client, token, day=_hom_nay())     # đúng ngày đã ghim = hôm nay


def test_HCNS_cham_bu_ngay_MAI_bi_chan(client):
    """Punch tương lai nặng hơn đơn tương lai: nó RA CÔNG THẬT khi tới ngày."""
    token = _admin_token(client)
    eid = _link_admin_employee(client, token)
    _shift_from_month_start(client, token, eid)
    r = client.post("/api/attendance/adjust",
                    json={"employee_id": eid, "date": _ngay_mai(), "check_type": "in",
                          "time": "08:00", "reason": "chấm bù"}, headers=_h(token))
    assert r.status_code == 400 and "chưa tới" in r.json()["detail"], r.text


# --- Nhật ký chấm công: tìm theo tên / mã ------------------------------------
#
# Tìm ở SERVER chứ không lọc ở FE: danh sách chỉ trả 100 lượt gần nhất của CẢ XƯỞNG, lọc sau khi
# đã cắt thì gõ tên người không bấm trong vài giờ qua sẽ ra "không tìm thấy" dù họ vẫn đi làm.


def _cham(client, token):
    return client.post("/api/attendance/check",
                       json={"latitude": 10.0, "longitude": 106.0}, headers=_h(token))


def _nhat_ky(client, token, **params):
    qs = "&".join(f"{k}={v}" for k, v in params.items())
    r = client.get(f"/api/attendance/logs{'?' + qs if qs else ''}", headers=_h(token))
    assert r.status_code == 200, r.text
    return r.json()["items"]


def test_tim_nhat_ky_theo_ten_va_theo_ma(client):
    token = _admin_token(client)
    _make_location(client, token, lat=10.0, lng=106.0, radius=200)
    dept = _dept_id("Hành chính nhân sự")
    ua = _make_worker("nk-an", dept)
    _link_employee(client, token, full_name="Nguyễn Văn An", dept_id=dept, user_id=ua)
    ub = _make_worker("nk-binh", dept)
    _link_employee(client, token, full_name="Trần Thị Bình", dept_id=dept, user_id=ub)
    ta, tb = create_access_token(str(ua)), create_access_token(str(ub))
    assert _cham(client, ta).json()["success"] and _cham(client, tb).json()["success"]

    assert len(_nhat_ky(client, token)) == 2                      # không lọc → cả hai
    chi_an = _nhat_ky(client, token, q="An")
    assert chi_an and all(x["employee_name"] == "Nguyễn Văn An" for x in chi_an)
    # Không phân biệt hoa/thường.
    assert len(_nhat_ky(client, token, q="nguyễn")) == len(chi_an)
    # Theo MÃ nhân viên.
    ma = client.get("/api/employees/me", headers=_h(ta)).json()["employee"]["code"]
    assert ma and _nhat_ky(client, token, q=ma)


def test_tim_khong_khop_ai_thi_RONG_chu_khong_tra_het(client):
    """Không khớp mà trả hết là kiểu 'tìm kiếm' tệ nhất — người dùng tưởng đã tìm ra."""
    token = _admin_token(client)
    _make_location(client, token, lat=10.0, lng=106.0, radius=200)
    _link_admin_employee(client, token)
    assert _cham(client, token).json()["success"]
    assert _nhat_ky(client, token) != []
    assert _nhat_ky(client, token, q="khongcoainaytencainay") == []


def test_TIM_KIEM_khong_ro_sang_to_khac(client):
    """⭐ Tìm kiếm KHÔNG được là đường vòng để nhìn trộm. Người chỉ thấy tổ mình gõ tên người tổ
    khác phải ra RỖNG — `q` thu hẹp bên TRONG lớp scope, không thay thế nó."""
    token = _admin_token(client)
    _make_location(client, token, lat=10.0, lng=106.0, radius=200)
    dept_a, dept_b = _dept_id("Hành chính nhân sự"), _dept_id("Kinh doanh")
    ub = _make_worker("nk-to-b", dept_b)
    _link_employee(client, token, full_name="Người Tổ B", dept_id=dept_b, user_id=ub)
    assert _cham(client, create_access_token(str(ub))).json()["success"]

    hr_a = _dept_hr_token("Hành chính nhân sự")     # scope = phòng mình
    assert _nhat_ky(client, hr_a, q="Người Tổ B") == [], "tim kiem lam ro nguoi to khac"
    # Admin (scope all) thì vẫn thấy — chứng tỏ dữ liệu CÓ, chỉ bị scope chặn đúng chỗ.
    assert _nhat_ky(client, token, q="Người Tổ B") != []


def test_loc_nhat_ky_theo_khoang_ngay(client):
    """⭐ Xem lại NGÀY TRƯỚC — nhu cầu chủ nêu 03/08/2026.

    Biên `den_ngay` phải lấy TRỌN ngày đó (nửa mở tới 00:00 hôm sau): chọn "đến 28/7" mà cắt ở
    00:00 ngày 28 là mất sạch lượt bấm trong chính ngày 28 — lỗi lệch biên kinh điển."""
    from datetime import datetime as _dt, timedelta as _td, timezone as _tz
    from app.db import SessionLocal as _S
    from app.models.attendance import AttendanceLog

    token = _admin_token(client)
    _make_location(client, token, lat=10.0, lng=106.0, radius=200)
    eid = _link_admin_employee(client, token)

    vn = _tz(_td(hours=7))
    hom_qua = (_dt.now(vn) - _td(days=1)).date()
    truoc_nua = (_dt.now(vn) - _td(days=5)).date()
    db = _S()
    try:
        for d, gio in ((hom_qua, 8), (hom_qua, 17), (truoc_nua, 8)):
            db.add(AttendanceLog(
                employee_id=eid, check_type="in" if gio < 12 else "out",
                checked_at=_dt.combine(d, _dt.min.time(), tzinfo=vn).replace(hour=gio)
                .astimezone(_tz.utc)))
        db.commit()
    finally:
        db.close()

    # Đúng MỘT ngày: tu = den = hôm qua ⇒ phải ra ĐỦ 2 lượt của ngày đó (8h và 17h).
    mot_ngay = _nhat_ky(client, token, tu_ngay=hom_qua.isoformat(), den_ngay=hom_qua.isoformat())
    assert len(mot_ngay) == 2, f"bien 'den_ngay' cat mat luot trong ngay: {mot_ngay}"

    # Khoảng rộng gom cả hai ngày.
    ca_hai = _nhat_ky(client, token, tu_ngay=truoc_nua.isoformat(), den_ngay=hom_qua.isoformat())
    assert len(ca_hai) == 3

    # Ngoài khoảng ⇒ rỗng.
    assert _nhat_ky(client, token, tu_ngay=hom_qua.isoformat(),
                    den_ngay=hom_qua.isoformat(), q="khongkhopai") == []


def test_loc_ngay_thi_NOI_TRAN_dong(client):
    """Có lọc ngày thì trần phải nới: một ngày của xưởng đông người vượt xa 100 lượt, giữ trần cũ
    là lọc xong vẫn mất nửa ngày TRONG IM LẶNG."""
    from app.services.attendance_service import AttendanceService
    assert AttendanceService.LOG_LIMIT_CO_LOC_NGAY > 100
