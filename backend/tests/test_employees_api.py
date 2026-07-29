"""Hồ sơ nhân sự (module `nhan_su`) — lát #1.

CRUD + KPIs, soft duplicate CCCD/BHXH, stage transitions (confirm/resign/reinstate/
transfer/promote) with Quá trình công tác events, account link/create/unlink, attachments,
and the RBAC gate. Admin (Giám đốc) holds full nhan_su by seed; a NV Sales user does not.
"""
from __future__ import annotations

from app.db import SessionLocal
from app.repositories.rbac_repo import DepartmentRepository, RoleRepository
from app.repositories.user_repo import UserRepository
from app.security import create_access_token, hash_password

ADMIN = {"username": "admin", "password": "admin123"}


def _admin_token(client) -> str:
    return client.post("/api/auth/login", json=ADMIN).json()["access_token"]


def _h(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


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
        existing = users.get_by_username("sales-emp")
        if existing is not None:
            return create_access_token(str(existing.id))
        kd = DepartmentRepository(db).get_by_name("Kinh doanh")
        role = RoleRepository(db).get_by_name_and_department("NV Sales", kd.id)
        u = users.create(username="sales-emp", name="S", password_hash=hash_password("x"))
        users.set_assignment(u, department_id=kd.id, role_id=role.id, is_active=True)
        return create_access_token(str(u.id))
    finally:
        db.close()


def _create(client, token, **over):
    body = {
        "full_name": over.pop("full_name", "Trần Văn A"),
        "department_id": over.pop("department_id", _dept_id("Hành chính nhân sự")),
        "hire_date": over.pop("hire_date", "2024-01-15"),
    }
    body.update(over)
    return client.post("/api/employees", json=body, headers=_h(token))


# --- self-service "Hồ sơ của tôi" ------------------------------------------


def test_my_profile_self_service(client):
    token = _admin_token(client)
    _create(client, token, full_name="NV Tự", phone="0900", note="ghi chú nội bộ",
            payroll_group="van_phong",
            account={"username": "nvtu", "password": "nvtu12345"})
    me_tok = client.post("/api/auth/login", json={"username": "nvtu", "password": "nvtu12345"}).json()["access_token"]

    me = client.get("/api/employees/me", headers=_h(me_tok)).json()
    assert me["has_employee"] is True
    assert me["employee"]["full_name"] == "NV Tự" and me["employee"]["phone"] == "0900"
    assert me["employee"]["note"] is None and me["employee"]["payroll_group"] is None  # nội bộ, ẩn

    # tự sửa liên lạc (whitelist): phone đổi được; full_name bị bỏ qua (không whitelist)
    upd = client.put("/api/employees/me", json={"phone": "0911", "full_name": "HACK"}, headers=_h(me_tok)).json()
    assert upd["employee"]["phone"] == "0911" and upd["employee"]["full_name"] == "NV Tự"

    # user không gắn hồ sơ → has_employee false
    assert client.get("/api/employees/me", headers=_h(_sales_token())).json()["has_employee"] is False


def test_profile_update_request_flow(client):
    """NV đề nghị đổi field bảo vệ (số TK) → chỉ field whitelist được ghi nhận; HCNS duyệt
    → áp thật vào hồ sơ; duyệt lại đơn đã xử lý → 400."""
    admin = _admin_token(client)
    _create(client, admin, full_name="NV Yêu Cầu", bank_account="111",
            account={"username": "nvyc", "password": "nvyc12345"})
    me_tok = client.post("/api/auth/login", json={"username": "nvyc", "password": "nvyc12345"}).json()["access_token"]

    # đề nghị đổi số TK (được) + phone (không whitelist → bị loại)
    r = client.post("/api/employees/me/update-requests",
                    json={"changes": {"bank_account": "999", "phone": "0900"}, "reason": "Đổi NH"},
                    headers=_h(me_tok))
    assert r.status_code == 201
    rid = r.json()["id"]
    assert r.json()["changes"].get("bank_account") == "999" and "phone" not in r.json()["changes"]

    assert any(x["id"] == rid and x["status"] == "pending"
               for x in client.get("/api/employees/me/update-requests", headers=_h(me_tok)).json()["items"])

    # HCNS thấy + duyệt
    listed = client.get("/api/employees/update-requests?status=pending", headers=_h(admin)).json()["items"]
    assert any(x["id"] == rid and x["employee_name"] == "NV Yêu Cầu" for x in listed)
    ap = client.post(f"/api/employees/update-requests/{rid}/approve", json={}, headers=_h(admin))
    assert ap.status_code == 200 and ap.json()["status"] == "approved"

    # áp thật: số TK đã đổi
    assert client.get("/api/employees/me", headers=_h(me_tok)).json()["employee"]["bank_account"] == "999"
    # duyệt lại đơn đã xử lý → 400
    assert client.post(f"/api/employees/update-requests/{rid}/approve", json={}, headers=_h(admin)).status_code == 400


# --- create + list ----------------------------------------------------------


def test_create_assigns_code_probation_and_hired_event(client):
    token = _admin_token(client)
    resp = _create(client, token, full_name="Nguyễn Thị B")
    assert resp.status_code == 201
    emp = resp.json()["employee"]
    assert emp["code"].startswith("NV")
    assert emp["status"] == "probation"  # mặc định Thử việc
    assert emp["department_name"] == "Hành chính nhân sự"

    events = client.get(f"/api/employees/{emp['id']}/events", headers=_h(token)).json()["items"]
    assert any(e["event_type"] == "hired" for e in events)


def _bac(client, token, code: str) -> int:
    """id của một bậc trong danh mục theo mã (bac_1..bac_5)."""
    items = client.get("/api/employees/bac-tay-nghe", headers=_h(token)).json()["items"]
    return next(g["id"] for g in items if g["code"] == code)


def test_create_with_employee_specific_salary_can_have_different_amounts(client):
    """Bậc thợ KHÔNG quyết định tiền — cùng bậc, 2 NV 2 mức lương vị trí khác nhau (bảng T05:
    cùng bậc 2 mà người 20tr người 10,5tr).

    Từ 29/07/2026 bậc là DANH MỤC (`job_grade_id`) chứ không còn là chữ tự do, nhưng luật trên
    không đổi: chủ chốt "khai bậc thôi, không cần điền tiền"."""
    token = _admin_token(client)
    dept_id = _dept_id("Hành chính nhân sự")
    bac_2 = _bac(client, token, "bac_2")

    first = _create(
        client, token, full_name="NV mức riêng A", department_id=dept_id,
        job_grade_id=bac_2,
        initial_salary={"luong_vi_tri": 8_000_000, "luong_trach_nhiem": 1_000_000,
                        "chuyen_can": 300_000},
    )
    second = _create(
        client, token, full_name="NV mức riêng B", department_id=dept_id,
        job_grade_id=bac_2,
        initial_salary={"luong_vi_tri": 13_000_000, "luong_trach_nhiem": 2_000_000,
                        "chuyen_can": 500_000},
    )
    assert first.status_code == 201 and second.status_code == 201
    assert first.json()["employee"]["job_grade_name"] == "Bậc 2"
    assert second.json()["employee"]["job_grade_id"] == bac_2, "hai người CÙNG một bậc"

    salary_a = client.get(
        f"/api/luong/salaries/{first.json()['employee']['id']}", headers=_h(token)
    ).json()["items"][0]
    salary_b = client.get(
        f"/api/luong/salaries/{second.json()['employee']['id']}", headers=_h(token)
    ).json()["items"][0]
    assert salary_a["amount_mode"] == salary_b["amount_mode"] == "manual"
    assert salary_a["luong_vi_tri"] + salary_a["luong_trach_nhiem"] == 9_000_000
    assert salary_b["luong_vi_tri"] + salary_b["luong_trach_nhiem"] == 15_000_000
    # Mức đóng BH = lương vị trí (khác nhau giữa 2 người cùng bậc).
    assert salary_a["luong_vi_tri"] == 8_000_000 and salary_b["luong_vi_tri"] == 13_000_000


def test_create_employee_with_initial_salary_no_grade_does_not_break(client):
    """Sau khi GỠ bậc: tạo NV + khai lương ban đầu (chỉ lương vị trí, không bậc) vẫn chạy."""
    token = _admin_token(client)
    resp = _create(
        client, token, full_name="NV gõ lương tay", department_id=_dept_id("Kinh doanh"),
        initial_salary={"luong_vi_tri": 8_000_000},
    )
    assert resp.status_code == 201, resp.text
    eid = resp.json()["employee"]["id"]
    prev = client.get(f"/api/luong/salaries/{eid}/preview", headers=_h(token)).json()
    assert prev["monthly"] == 8_000_000 and prev["insurance_base"] == 8_000_000


def test_create_with_initial_salary_requires_payroll_permission_before_creating_employee(client):
    admin = _admin_token(client)
    token = _ns_no_salary_token()
    before = client.get("/api/employees", headers=_h(admin)).json()["total"]

    response = _create(
        client,
        token,
        full_name="NV khong duoc khai luong ban dau",
        initial_salary={"luong_vi_tri": 8_000_000},
    )

    assert response.status_code == 403
    after = client.get("/api/employees", headers=_h(admin)).json()["total"]
    assert after == before


def test_create_rejects_salary_effective_before_hire_date_without_partial_employee(client):
    token = _admin_token(client)
    before = client.get("/api/employees", headers=_h(token)).json()["total"]

    response = _create(
        client,
        token,
        full_name="NV sai ngay hieu luc luong",
        hire_date="2026-02-01",
        initial_salary={
            "effective_from": "2026-01-01",
            "luong_vi_tri": 8_000_000,
        },
    )

    assert response.status_code == 400
    assert "ngay vao lam" in response.json()["detail"].lower()
    after = client.get("/api/employees", headers=_h(token)).json()["total"]
    assert after == before


def test_list_has_kpis_and_status_filter(client):
    token = _admin_token(client)
    # Baseline: mọi tài khoản đều có hồ sơ (`backfill_employee_profiles`) nên DB đã có sẵn hồ sơ
    # nền (vd admin, active). Đo DELTA thay vì số tuyệt đối để không phụ thuộc dữ liệu nền.
    base = client.get("/api/employees", headers=_h(token)).json()["kpis"]
    _create(client, token, full_name="A")   # probation (mặc định)
    active = _create(client, token, full_name="B").json()["employee"]
    client.post(
        f"/api/employees/{active['id']}/transitions",
        json={"kind": "confirm", "effective_date": "2024-03-01"},
        headers=_h(token),
    )

    data = client.get("/api/employees", headers=_h(token)).json()
    assert data["kpis"]["total"] == base["total"] + 2
    assert data["kpis"]["probation"] == base["probation"] + 1
    assert data["kpis"]["active"] == base["active"] + 1

    only_active = client.get("/api/employees?status=active", headers=_h(token)).json()
    assert only_active["total"] == base["active"] + 1
    assert all(it["status"] == "active" for it in only_active["items"])


# --- soft duplicate ---------------------------------------------------------


def test_duplicate_cccd_is_soft_warning(client):
    token = _admin_token(client)
    first = _create(client, token, full_name="X", national_id="079123456789").json()["employee"]
    resp = _create(client, token, full_name="Y", national_id="079123456789")
    assert resp.status_code == 201  # KHÔNG chặn
    dup = resp.json()["duplicate_national_id"]
    assert dup is not None and dup["id"] == first["id"]


# --- edit -------------------------------------------------------------------


def test_update_edits_profile(client):
    token = _admin_token(client)
    emp = _create(client, token).json()["employee"]
    resp = client.put(
        f"/api/employees/{emp['id']}",
        json={"full_name": "Tên Mới", "phone": "0900000000", "dependents_count": 2},
        headers=_h(token),
    )
    assert resp.status_code == 200
    out = resp.json()["employee"]
    assert out["full_name"] == "Tên Mới"
    assert out["phone"] == "0900000000"
    assert out["dependents_count"] == 2


# --- transitions ------------------------------------------------------------


def test_confirm_then_illegal_transition(client):
    token = _admin_token(client)
    emp = _create(client, token).json()["employee"]
    ok = client.post(
        f"/api/employees/{emp['id']}/transitions",
        json={"kind": "confirm", "effective_date": "2024-03-01"},
        headers=_h(token),
    )
    assert ok.status_code == 200 and ok.json()["status"] == "active"
    # confirm again from `active` is illegal
    bad = client.post(
        f"/api/employees/{emp['id']}/transitions",
        json={"kind": "confirm"},
        headers=_h(token),
    )
    assert bad.status_code == 400


def test_resign_requires_reason_then_locks_edit_until_reinstate(client):
    token = _admin_token(client)
    emp = _create(client, token).json()["employee"]
    eid = emp["id"]

    no_reason = client.post(
        f"/api/employees/{eid}/transitions", json={"kind": "resign"}, headers=_h(token)
    )
    assert no_reason.status_code == 400

    resigned = client.post(
        f"/api/employees/{eid}/transitions",
        json={"kind": "resign", "effective_date": "2024-06-30", "resign_reason": "Tự xin nghỉ"},
        headers=_h(token),
    )
    assert resigned.status_code == 200 and resigned.json()["status"] == "resigned"

    # Resigned hồ sơ is read-only.
    locked = client.put(f"/api/employees/{eid}", json={"full_name": "Z"}, headers=_h(token))
    assert locked.status_code == 400

    # Reinstate reopens it.
    back = client.post(
        f"/api/employees/{eid}/transitions", json={"kind": "reinstate"}, headers=_h(token)
    )
    assert back.status_code == 200 and back.json()["status"] == "active"
    assert client.put(f"/api/employees/{eid}", json={"full_name": "Z"}, headers=_h(token)).status_code == 200


def test_transfer_and_promote_record_events(client):
    token = _admin_token(client)
    hcns = _dept_id("Hành chính nhân sự")
    kd = _dept_id("Kinh doanh")
    emp = _create(client, token, department_id=hcns).json()["employee"]
    eid = emp["id"]

    # transfer to another department
    t = client.post(
        f"/api/employees/{eid}/transitions",
        json={"kind": "transfer", "new_department_id": kd, "effective_date": "2024-04-06"},
        headers=_h(token),
    )
    assert t.status_code == 200 and t.json()["department_id"] == kd
    # transfer to same dept is rejected
    same = client.post(
        f"/api/employees/{eid}/transitions",
        json={"kind": "transfer", "new_department_id": kd},
        headers=_h(token),
    )
    assert same.status_code == 400

    # promote (bậc tay nghề — chọn từ danh mục, không còn gõ chữ tự do)
    bac_3 = _bac(client, token, "bac_3")
    p = client.post(
        f"/api/employees/{eid}/transitions",
        json={"kind": "promote", "new_job_grade_id": bac_3},
        headers=_h(token),
    )
    assert p.status_code == 200 and p.json()["job_grade_name"] == "Bậc 3"

    kinds = {e["event_type"] for e in client.get(f"/api/employees/{eid}/events", headers=_h(token)).json()["items"]}
    assert {"hired", "transferred", "promoted"} <= kinds


def test_transfer_and_promote_change_grade_without_changing_salary(client):
    """Bậc gỡ hẳn → điều chuyển đổi PHÒNG, thăng bậc đổi `job_grade` (free-text) + chức danh;
    lương của NV KHÔNG đổi và KHÔNG sinh mốc lương mới (lương theo NV, không theo bậc/phòng)."""
    token = _admin_token(client)
    hcns = _dept_id("Hành chính nhân sự")
    kd = _dept_id("Kinh doanh")

    employee = _create(
        client, token, full_name="NV giữ nguyên lương khi đổi bậc", department_id=hcns,
        hire_date="2026-01-01", job_grade_id=_bac(client, token, "bac_1"),
        initial_salary={"effective_from": "2026-01-01", "luong_vi_tri": 11_000_000,
                        "luong_trach_nhiem": 2_000_000, "allowance": 700_000},
    ).json()["employee"]

    transferred = client.post(
        f"/api/employees/{employee['id']}/transitions",
        json={"kind": "transfer", "new_department_id": kd,
              "new_job_grade_id": _bac(client, token, "bac_2"),
              "effective_date": "2026-04-01"},
        headers=_h(token),
    )
    assert transferred.status_code == 200, transferred.text
    assert transferred.json()["department_id"] == kd
    assert transferred.json()["job_grade_name"] == "Bậc 2"

    promoted = client.post(
        f"/api/employees/{employee['id']}/transitions",
        json={"kind": "promote", "new_job_grade_id": _bac(client, token, "bac_3"),
              "new_position": "Tổ phó", "effective_date": "2026-07-01"},
        headers=_h(token),
    )
    assert promoted.status_code == 200, promoted.text
    assert promoted.json()["job_grade_name"] == "Bậc 3"

    # Lương KHÔNG đổi, KHÔNG sinh mốc lương mới (vẫn đúng 1 bản ghi ban đầu).
    history = client.get(
        f"/api/luong/salaries/{employee['id']}", headers=_h(token)
    ).json()["items"]
    assert len(history) == 1
    assert history[0]["luong_vi_tri"] == 11_000_000
    assert history[0]["luong_trach_nhiem"] == 2_000_000
    assert history[0]["allowance"] == 700_000


# --- account link -----------------------------------------------------------


def test_create_account_in_wizard_then_login(client):
    token = _admin_token(client)
    resp = _create(
        client, token, full_name="Có Tài Khoản",
        account={"username": "nv_login", "password": "secret1"},
    )
    assert resp.status_code == 201
    payload = resp.json()
    assert payload["account_username"] == "nv_login"

    # the new account can authenticate
    login = client.post("/api/auth/login", json={"username": "nv_login", "password": "secret1"})
    assert login.status_code == 200


def test_create_account_for_existing_employee(client):
    """NV tạo trước, cấp tài khoản sau — đường chính vì không còn tài khoản mồ côi để liên kết."""
    token = _admin_token(client)
    eid = _create(client, token, full_name="Cấp Sau").json()["employee"]["id"]
    resp = client.post(
        f"/api/employees/{eid}/account",
        json={"username": "nv_capsau", "password": "secret1"},
        headers=_h(token),
    )
    assert resp.status_code == 200
    assert resp.json()["account_username"] == "nv_capsau"
    login = client.post(
        "/api/auth/login", json={"username": "nv_capsau", "password": "secret1"}
    )
    assert login.status_code == 200


def test_attach_account_needs_username_or_user_id(client):
    token = _admin_token(client)
    eid = _create(client, token, full_name="Thiếu Tham Số").json()["employee"]["id"]
    resp = client.post(f"/api/employees/{eid}/account", json={}, headers=_h(token))
    assert resp.status_code == 400


def test_unlink_account_endpoint_is_gone(client):
    """Mọi tài khoản phải thuộc một hồ sơ → không còn cửa 'gỡ liên kết' (đẻ tài khoản mồ côi)."""
    token = _admin_token(client)
    payload = _create(
        client, token, full_name="Không Gỡ Được",
        account={"username": "nv_nogo", "password": "secret1"},
    ).json()
    eid = payload["employee"]["id"]
    resp = client.delete(f"/api/employees/{eid}/account", headers=_h(token))
    assert resp.status_code == 405  # method gone; chặn người = KHÓA tài khoản


def test_create_orphan_user_endpoint_is_gone(client):
    """Đường tạo tài khoản duy nhất là qua hồ sơ NV → POST /api/users không còn."""
    token = _admin_token(client)
    resp = client.post(
        "/api/users",
        json={"name": "Mồ Côi", "username": "mocoi", "department_id": _dept_id("Kinh doanh")},
        headers=_h(token),
    )
    assert resp.status_code == 405


def test_resigned_employee_cannot_login_and_reinstate_restores(client):
    """Trạng thái hồ sơ 'Đã nghỉ' ⇒ không đăng nhập được. Đổi trạng thái lại ⇒ vào được."""
    token = _admin_token(client)
    payload = _create(
        client, token, full_name="Sắp Nghỉ",
        account={"username": "nv_nghi", "password": "secret1"},
    ).json()
    eid = payload["employee"]["id"]
    creds = {"username": "nv_nghi", "password": "secret1"}
    assert client.post("/api/auth/login", json=creds).status_code == 200

    # nghỉ việc → login đóng cửa (không ai phải đi khóa tay)
    resp = client.post(
        f"/api/employees/{eid}/transitions",
        json={"kind": "resign", "effective_date": "2026-07-31", "resign_reason": "Chuyển việc"},
        headers=_h(token),
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "resigned"
    assert client.post("/api/auth/login", json=creds).status_code == 401

    # tuyển lại → tự mở, không cần nhớ mở khóa
    back = client.post(
        f"/api/employees/{eid}/transitions",
        json={"kind": "reinstate", "effective_date": "2026-09-01"},
        headers=_h(token),
    )
    assert back.status_code == 200
    assert client.post("/api/auth/login", json=creds).status_code == 200


def test_meta_returns_roles_for_account_form(client):
    token = _admin_token(client)
    meta = client.get("/api/employees/meta", headers=_h(token)).json()
    assert meta["roles"], "meta phải trả vai trò để form tài khoản chọn"
    kd = _dept_id("Kinh doanh")
    assert any(r["name"] == "NV Sales" and r["department_id"] == kd for r in meta["roles"])


# --- attachments ------------------------------------------------------------


def test_attachment_upload_list_delete(client):
    token = _admin_token(client)
    emp = _create(client, token).json()["employee"]
    eid = emp["id"]

    up = client.post(
        f"/api/employees/{eid}/attachments",
        files={"file": ("cccd.pdf", b"%PDF-1.4 fake", "application/pdf")},
        data={"doc_kind": "cccd"},
        headers=_h(token),
    )
    assert up.status_code == 201
    att = up.json()
    assert att["doc_kind"] == "cccd" and att["file_name"] == "cccd.pdf"
    assert att["file_url"].startswith(f"/api/files/hr/{eid}/")

    listed = client.get(f"/api/employees/{eid}/attachments", headers=_h(token)).json()["items"]
    assert len(listed) == 1

    assert client.delete(f"/api/employees/{eid}/attachments/{att['id']}", headers=_h(token)).status_code == 204
    assert client.get(f"/api/employees/{eid}/attachments", headers=_h(token)).json()["items"] == []


# --- RBAC -------------------------------------------------------------------


def test_forbidden_without_permission(client):
    token = _sales_token()
    assert client.get("/api/employees", headers=_h(token)).status_code == 403
    assert _create(client, token).status_code == 403


# --- N5: tách quyền SỬA lương/BHXH khỏi quyền sửa hồ sơ ---------------------


def _ns_no_salary_token() -> str:
    """User có quyền nhan_su read/create/update nhưng KHÔNG view_salary/edit_salary (N5)."""
    db = SessionLocal()
    try:
        users = UserRepository(db)
        existing = users.get_by_username("ns-nosalary")
        if existing is not None:
            return create_access_token(str(existing.id))
        hcns = DepartmentRepository(db).get_by_name("Hành chính nhân sự")
        roles = RoleRepository(db)
        role = roles.get_by_name_and_department("NS Không Lương", hcns.id)
        if role is None:
            role = roles.create(name="NS Không Lương", department_id=hcns.id)
            roles.set_permission(
                role_id=role.id, module_key="nhan_su", scope="all",
                can_read=True, can_create=True, can_update=True,
            )
        u = users.create(username="ns-nosalary", name="NS", password_hash=hash_password("x"))
        users.set_assignment(u, department_id=hcns.id, role_id=role.id, is_active=True)
        return create_access_token(str(u.id))
    finally:
        db.close()


def test_edit_salary_gate_blocks_sensitive_write(client):
    """Người có nhan_su:update nhưng KHÔNG edit_salary → field lương/BHXH bị BỎ QUA khi
    tạo/sửa (field thường vẫn ghi). Admin (có view_salary) đọc lại để kiểm."""
    admin = _admin_token(client)
    tok = _ns_no_salary_token()

    # Tạo NV kèm field nhạy cảm → bị bỏ (không lưu lén)
    created = _create(client, tok, full_name="NV No Salary",
                      bank_account="123456", payroll_group="van_phong", phone="0900")
    assert created.status_code == 201
    eid = created.json()["employee"]["id"]

    seen = client.get(f"/api/employees/{eid}", headers=_h(admin)).json()
    assert seen["phone"] == "0900"          # field thường: ghi được
    assert seen["bank_account"] is None     # nhạy cảm: bị bỏ khi tạo
    assert seen["payroll_group"] is None

    # Admin đặt số TK nền (full_name bắt buộc ở EmployeeUpdate)
    r_admin = client.put(f"/api/employees/{eid}",
                         json={"full_name": "NV No Salary", "bank_account": "111"}, headers=_h(admin))
    assert r_admin.status_code == 200
    # user không-quyền-lương PUT đổi bank + phone → bank bị bỏ, phone đổi
    upd = client.put(f"/api/employees/{eid}",
                     json={"full_name": "NV No Salary", "bank_account": "999", "phone": "0911"}, headers=_h(tok))
    assert upd.status_code == 200
    seen2 = client.get(f"/api/employees/{eid}", headers=_h(admin)).json()
    assert seen2["phone"] == "0911"         # field thường: ghi được
    assert seen2["bank_account"] == "111"   # nhạy cảm: KHÔNG đổi


# --- Đ1: hồ sơ là GỐC — đồng bộ danh tính xuống tài khoản gắn kèm ------------


def test_employee_edit_syncs_name_and_department_to_user(client):
    """Đ1/Đ2: sửa tên hồ sơ + điều chuyển phòng → tài khoản gắn kèm đồng bộ tên + phòng
    (phòng = trục data-scope RBAC). Đồng bộ 1 chiều hồ-sơ→tài-khoản."""
    admin = _admin_token(client)
    hcns = _dept_id("Hành chính nhân sự")
    kd = _dept_id("Kinh doanh")
    created = _create(client, admin, full_name="Tên Cũ", department_id=hcns,
                      account={"username": "synced", "password": "synced123"})
    eid = created.json()["employee"]["id"]

    client.put(f"/api/employees/{eid}", json={"full_name": "Tên Mới"}, headers=_h(admin))
    client.post(f"/api/employees/{eid}/transitions",
                json={"kind": "transfer", "new_department_id": kd}, headers=_h(admin))

    db = SessionLocal()
    try:
        u = UserRepository(db).get_by_username("synced")
        assert u.name == "Tên Mới"        # tên đồng bộ
        assert u.department_id == kd       # phòng (scope) đồng bộ theo điều chuyển
    finally:
        db.close()


def test_user_with_profile_cannot_self_rename(client):
    """Đ1: tài khoản CÓ hồ sơ → không tự đổi tên hiển thị qua /api/users/me (tên do hồ sơ
    quyết, HCNS cập nhật). Chặn ở backend, không chỉ ẩn ở FE."""
    admin = _admin_token(client)
    _create(client, admin, full_name="Khoa Nguyen",
            account={"username": "hasprofile", "password": "hasprofile1"})
    tok = client.post("/api/auth/login",
                      json={"username": "hasprofile", "password": "hasprofile1"}).json()["access_token"]
    r = client.patch("/api/users/me", json={"name": "Tên Tự Đặt"}, headers=_h(tok))
    assert r.status_code == 400


def test_danh_sach_nhan_vien_chan_size_qua_200(client):
    """Ghim ràng buộc mà FE ĐANG DỰA VÀO: `GET /api/employees` chặn `size > 200`.

    Modal "Gán cho nhân viên" từng gửi `size=500` ⇒ 422, và vì gọi trong `Promise.all` nên danh
    sách treo mãi ở "Đang tải danh sách nhân viên…". Nay FE phân trang theo lô 200
    (`EMP_PAGE` trong `CauHinhLuongTab.tsx`) — hạ trần xuống dưới 200 là làm hỏng chỗ đó."""
    token = _admin_token(client)
    assert client.get("/api/employees?page=1&size=500", headers=_h(token)).status_code == 422
    assert client.get("/api/employees?page=1&size=200", headers=_h(token)).status_code == 200
