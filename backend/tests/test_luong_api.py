"""Lương (module `luong`, Phase 1): params + quy tắc, engine tính lương (prorate công,
%thử việc, chuyên cần, BHXH), khai báo/điều chỉnh lương, tạm ứng, tạo/khóa bảng lương."""
from __future__ import annotations

from datetime import date
from types import SimpleNamespace

from app.db import SessionLocal
from app.repositories.employee_repo import EmployeeRepository
from app.repositories.payroll_repo import PayrollRepository
from app.repositories.rbac_repo import DepartmentRepository, RoleRepository
from app.repositories.user_repo import UserRepository
from app.security import create_access_token, hash_password
from app.services.payroll_service import PayrollService

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
        existing = users.get_by_username("sales-luong")
        if existing is not None:
            return create_access_token(str(existing.id))
        kd = DepartmentRepository(db).get_by_name("Kinh doanh")
        role = RoleRepository(db).get_by_name_and_department("NV Sales", kd.id)
        u = users.create(username="sales-luong", name="S", password_hash=hash_password("x"))
        users.set_assignment(u, department_id=kd.id, role_id=role.id, is_active=True)
        return create_access_token(str(u.id))
    finally:
        db.close()


def _make_emp(client, token, *, name, payroll_group=None, pay_grade_key=None,
              gender="male", hire_date="2020-01-01", status=None) -> int:
    body = {"full_name": name, "department_id": _dept_id("Hành chính nhân sự"),
            "hire_date": hire_date, "gender": gender}
    if payroll_group:
        body["payroll_group"] = payroll_group
    if pay_grade_key:
        body["pay_grade_key"] = pay_grade_key
    if status:
        body["status"] = status
    return client.post("/api/employees", json=body, headers=_h(token)).json()["employee"]["id"]


# --- params + rules ---------------------------------------------------------


def test_params_defaults_and_rbac(client):
    token = _admin_token(client)
    p = client.get("/api/luong/params", headers=_h(token)).json()
    assert p["standard_cong_default"] == 26 and p["probation_ratio"] == 0.8

    upd = client.put("/api/luong/params", json={"standard_cong_default": 24}, headers=_h(token))
    assert upd.status_code == 200 and upd.json()["standard_cong_default"] == 24
    # khôi phục
    client.put("/api/luong/params", json={"standard_cong_default": 26}, headers=_h(token))

    # NV Sales không có quyền lương
    assert client.get("/api/luong/params", headers=_h(_sales_token())).status_code == 403


def test_rule_crud(client):
    token = _admin_token(client)
    created = client.post("/api/luong/rules", json={
        "payroll_group": "to_in", "pay_grade_key": "tho_1", "monthly_amount": 25_000_000,
        "effective_from": "2026-01-01",
    }, headers=_h(token))
    assert created.status_code == 201
    rid = created.json()["id"]
    listed = client.get("/api/luong/rules", headers=_h(token)).json()["items"]
    assert any(r["id"] == rid and r["monthly_amount"] == 25_000_000 for r in listed)

    upd = client.put(f"/api/luong/rules/{rid}", json={
        "payroll_group": "to_in", "pay_grade_key": "tho_1", "monthly_amount": 26_000_000,
    }, headers=_h(token))
    assert upd.json()["monthly_amount"] == 26_000_000
    assert client.delete(f"/api/luong/rules/{rid}", headers=_h(token)).status_code == 204


# --- engine (unit) ----------------------------------------------------------


def test_compute_engine(client):
    """Prorate công + %thử việc + chuyên cần + BHXH — kiểm trực tiếp _compute."""
    client  # đảm bảo app khởi động (tạo bảng + migration)
    db = SessionLocal()
    try:
        svc = PayrollService(PayrollRepository(db), EmployeeRepository(db), attendance=None)
        svc.payroll.create_rule(payroll_group="ut_grp", monthly_amount=10_000_000,
                                effective_from=date(2020, 1, 1))
        params = svc.get_params()
        on = date(2026, 6, 1)

        emp = SimpleNamespace(status="active", hire_date=date(2020, 1, 1), gender="male",
                              payroll_group="ut_grp", pay_grade_key=None)

        # nửa công (13/26) → lương công = 5tr; chưa đủ công → chuyên cần 0.
        v = svc._compute(employee=emp, salary=None, params=params, actual_cong=13,
                         standard_cong=26, on=on)
        assert v["monthly_salary"] == 10_000_000
        assert v["luong_cong"] == 5_000_000
        assert v["chuyen_can"] == 0
        assert v["bhxh"] == round(10_000_000 * 0.105)   # 1.050.000, không prorate

        # đủ công → lương công đủ + chuyên cần mặc định 300k.
        v2 = svc._compute(employee=emp, salary=None, params=params, actual_cong=26,
                          standard_cong=26, on=on)
        assert v2["luong_cong"] == 10_000_000 and v2["chuyen_can"] == 300_000
        assert v2["gross"] == 10_300_000

        # thử việc → ×0.8.
        emp_tv = SimpleNamespace(status="probation", hire_date=date(2026, 5, 1), gender="male",
                                 payroll_group="ut_grp", pay_grade_key=None)
        v3 = svc._compute(employee=emp_tv, salary=None, params=params, actual_cong=26,
                          standard_cong=26, on=on)
        assert v3["monthly_salary"] == 10_000_000       # mức gốc (chưa nhân)
        assert v3["luong_cong"] == 8_000_000            # 10tr × 0.8 × 1.0
        assert v3["bhxh"] == round(8_000_000 * 0.105)   # đóng trên mức thử việc
    finally:
        db.close()


# --- lương nhân viên (khai báo + preview) -----------------------------------


def test_salary_declare_and_preview(client):
    token = _admin_token(client)
    client.post("/api/luong/rules", json={
        "payroll_group": "to_in", "pay_grade_key": "tho_2", "monthly_amount": 22_000_000,
        "effective_from": "2026-01-01",
    }, headers=_h(token))
    eid = _make_emp(client, token, name="Thợ In A", payroll_group="to_in", pay_grade_key="tho_2")

    # khai lương rule-mode
    s = client.post(f"/api/luong/salaries/{eid}", json={
        "effective_from": "2026-01-01", "amount_mode": "rule", "allowance": 300_000,
    }, headers=_h(token))
    assert s.status_code == 201

    prev = client.get(f"/api/luong/salaries/{eid}/preview", headers=_h(token)).json()
    assert prev["monthly"] == 22_000_000 and prev["source"] == "rule"

    hist = client.get(f"/api/luong/salaries/{eid}", headers=_h(token)).json()
    assert hist["employee_name"] == "Thợ In A" and len(hist["items"]) == 1

    # điều chỉnh (manual) hiệu lực sau → preview lấy mức mới
    client.post(f"/api/luong/salaries/{eid}", json={
        "effective_from": "2026-07-01", "amount_mode": "manual", "base_amount": 24_000_000,
    }, headers=_h(token))
    prev2 = client.get(f"/api/luong/salaries/{eid}/preview", headers=_h(token)).json()
    assert prev2["monthly"] == 24_000_000 and prev2["source"] == "manual"


# --- tạm ứng ----------------------------------------------------------------


def test_advance_workflow(client):
    token = _admin_token(client)
    eid = _make_emp(client, token, name="NV Ứng", payroll_group="van_phong")
    created = client.post("/api/luong/advances", json={
        "employee_id": eid, "period_year": 2026, "period_month": 6,
        "advance_date": "2026-06-10", "amount": 2_000_000, "reason": "Ứng",
    }, headers=_h(token))
    assert created.status_code == 201 and created.json()["status"] == "pending"
    aid = created.json()["id"]

    ap = client.post(f"/api/luong/advances/{aid}/approve", json={}, headers=_h(token))
    assert ap.status_code == 200 and ap.json()["status"] == "approved"
    # duyệt lại → 400
    assert client.post(f"/api/luong/advances/{aid}/approve", json={}, headers=_h(token)).status_code == 400

    listed = client.get("/api/luong/advances?year=2026&month=6&status=approved", headers=_h(token)).json()["items"]
    assert any(a["id"] == aid and a["employee_name"] == "NV Ứng" for a in listed)


# --- bảng lương tháng: tạo + engine + khóa ----------------------------------


def test_generate_lock_flow(client):
    token = _admin_token(client)
    client.post("/api/luong/rules", json={
        "payroll_group": "vp_gen", "monthly_amount": 10_000_000, "effective_from": "2026-01-01",
    }, headers=_h(token))
    eid = _make_emp(client, token, name="NV Bảng", payroll_group="vp_gen", status="active")
    client.post(f"/api/luong/salaries/{eid}", json={
        "effective_from": "2026-01-01", "amount_mode": "rule",
    }, headers=_h(token))
    # tạm ứng đã duyệt 2tr trong kỳ
    aid = client.post("/api/luong/advances", json={
        "employee_id": eid, "period_year": 2026, "period_month": 6,
        "advance_date": "2026-06-05", "amount": 2_000_000,
    }, headers=_h(token)).json()["id"]
    client.post(f"/api/luong/advances/{aid}/approve", json={}, headers=_h(token))

    gen = client.post("/api/luong/generate", json={"year": 2026, "month": 6}, headers=_h(token))
    assert gen.status_code == 200
    line = next(l for l in gen.json()["lines"] if l["employee_id"] == eid)
    assert line["monthly_salary"] == 10_000_000
    assert line["bhxh"] == round(10_000_000 * 0.105)
    assert line["advance_total"] == 2_000_000
    lid = line["id"]

    # sửa ô tay: vi phạm 500k + thưởng 1tr → gross/net tính lại
    upd = client.put(f"/api/luong/lines/{lid}", json={"vi_pham": 500_000, "other_bonus": 1_000_000},
                     headers=_h(token)).json()
    assert upd["vi_pham"] == 500_000 and upd["other_bonus"] == 1_000_000
    exp_gross = upd["luong_cong"] + upd["chuyen_can"] + upd["allowance"] + 1_000_000 - 500_000
    assert upd["gross"] == exp_gross
    assert upd["net_pay"] == exp_gross - upd["bhxh"] - upd["pit"] - upd["advance_total"]

    # chốt kỳ → generate lại + sửa dòng đều bị chặn (409)
    lock = client.post("/api/luong/lock", json={"year": 2026, "month": 6}, headers=_h(token))
    assert lock.status_code == 200 and lock.json()["status"] == "locked"
    assert client.post("/api/luong/generate", json={"year": 2026, "month": 6}, headers=_h(token)).status_code == 409
    assert client.put(f"/api/luong/lines/{lid}", json={"vi_pham": 0}, headers=_h(token)).status_code == 409

    # mở lại → sửa được
    assert client.post("/api/luong/reopen", json={"year": 2026, "month": 6}, headers=_h(token)).status_code == 200
    assert client.put(f"/api/luong/lines/{lid}", json={"vi_pham": 0}, headers=_h(token)).status_code == 200
