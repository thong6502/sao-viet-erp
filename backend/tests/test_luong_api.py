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
    assert p["standard_cong_default"] == 26 and p["probation_ratio"] == 0.80

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
        assert v3["luong_cong"] == 8_000_000            # 10tr × 0.80 × 1.0 (công ty dùng 80%)
        assert v3["bhxh"] == 0                          # thử việc KHÔNG đóng BHXH (HĐ thử việc)
    finally:
        db.close()


def test_ot_and_night_pay(client):
    """Pha 4a: tăng ca (hệ số phẳng) + phụ cấp ca đêm cộng vào gross, KHÔNG prorate theo công."""
    client
    db = SessionLocal()
    try:
        svc = PayrollService(PayrollRepository(db), EmployeeRepository(db), attendance=None)
        svc.payroll.create_rule(payroll_group="ot_grp", monthly_amount=26_000_000,
                                effective_from=date(2020, 1, 1))
        params = svc.get_params()   # standard_hours_per_day=8, ot_multiplier=1.5, night_pct=0.3
        emp = SimpleNamespace(status="active", hire_date=date(2020, 1, 1), gender="male",
                              payroll_group="ot_grp", pay_grade_key=None)
        # std 26 → 1 công = 1.000.000; giờ = 125.000. OT 120' (2h)×1.5 = 375.000.
        # ca đêm 2 ngày × 1.000.000 × 0.3 = 600.000.
        v = svc._compute(employee=emp, salary=None, params=params, actual_cong=26,
                         standard_cong=26, ot_minutes=120, night_days=2, on=date(2026, 6, 1))
        assert v["ot_pay"] == 375_000
        assert v["night_pay"] == 600_000
        assert v["gross"] == 26_000_000 + 300_000 + 375_000 + 600_000   # + chuyên cần đủ công
    finally:
        db.close()


def test_piece_work_dept_skips_ot(client):
    """Tổ khoán (has_piece_work): KHÔNG tính tăng ca theo giờ; tổ thường vẫn có tăng ca."""
    client
    db = SessionLocal()
    try:
        svc = PayrollService(PayrollRepository(db), EmployeeRepository(db), attendance=None)
        svc.payroll.create_rule(payroll_group="pw_grp", monthly_amount=26_000_000,
                                effective_from=date(2020, 1, 1))
        params = svc.get_params()
        emp = SimpleNamespace(status="active", hire_date=date(2020, 1, 1), gender="male",
                              payroll_group="pw_grp", pay_grade_key=None)
        # Cùng dữ liệu OT 120', chỉ khác cờ tổ khoán.
        v_norm = svc._compute(employee=emp, salary=None, params=params, actual_cong=26,
                              standard_cong=26, ot_minutes=120, on=date(2026, 6, 1))
        v_piece = svc._compute(employee=emp, salary=None, params=params, actual_cong=26,
                               standard_cong=26, ot_minutes=120, has_piece_work=True,
                               on=date(2026, 6, 1))
        assert v_norm["ot_pay"] == 375_000          # tổ thường vẫn tính tăng ca
        assert v_piece["ot_pay"] == 0               # tổ khoán bỏ tăng ca giờ
        # Lương công giữ nguyên, gross tổ khoán KHÔNG có phần tăng ca.
        assert v_piece["gross"] == v_norm["gross"] - 375_000
    finally:
        db.close()


def _dept_row_svc(db, dept_name, **row_kw):
    """Dựng service + 1 tổ + 1 dòng bảng lương của tổ, trả (svc, dept, row)."""
    depts = DepartmentRepository(db)
    svc = PayrollService(PayrollRepository(db), EmployeeRepository(db),
                         attendance=None, departments=depts)
    dept = depts.create(name=dept_name, salary_mechanism=row_kw.pop("mechanism", "tham_nien"))
    row = depts.create_salary_row(
        department_id=dept.id, label=row_kw.pop("label", "dòng test"),
        apply_by=row_kw.pop("apply_by", "tham_nien"),
        seniority_band=row_kw.pop("seniority_band", None),
        pay_grade_key=row_kw.pop("pay_grade_key", None), gender=row_kw.pop("gender", None),
        luong_vi_tri=row_kw.pop("luong_vi_tri", 0), luong_trach_nhiem=row_kw.pop("luong_trach_nhiem", 0),
        phu_cap=row_kw.pop("phu_cap", 0), chuyen_can=row_kw.pop("chuyen_can", 0),
        sort_order=row_kw.pop("sort_order", 0),
    )
    return svc, dept, row


def test_resolve_dept_row_reads_components(client):
    """dept_row: monthly = vị trí+trách nhiệm (KHÔNG gồm phụ cấp); chuyên cần lấy từ NV."""
    client
    db = SessionLocal()
    try:
        svc, dept, row = _dept_row_svc(
            db, "Tổ Bồi (resolve)", seniority_band="y1_5",
            luong_vi_tri=6_000_000, luong_trach_nhiem=2_000_000)
        params = svc.get_params()
        emp = SimpleNamespace(status="active", hire_date=date(2022, 1, 1), gender="male",
                              payroll_group=None, pay_grade_key=None, department_id=dept.id)
        salary = SimpleNamespace(amount_mode="dept_row", base_amount=None,
                                 source_salary_row_id=row.id, chuyen_can=300_000)
        res = svc._resolve_salary(emp, salary, params, date(2026, 6, 1))
        assert res["source"] == "dept_row"
        assert res["monthly"] == 8_000_000          # vị trí+trách nhiệm, KHÔNG gồm phụ cấp
        assert res["chuyen_can_amt"] == 300_000      # theo NV (salary.chuyen_can)
    finally:
        db.close()


def test_resolve_dept_row_live_update(client):
    """Sửa số trong dòng bảng lương của tổ → _resolve đọc SỐNG mức mới (không đóng băng)."""
    client
    db = SessionLocal()
    try:
        svc, dept, row = _dept_row_svc(
            db, "Tổ Bồi (live)", luong_vi_tri=6_000_000, luong_trach_nhiem=2_000_000)
        params = svc.get_params()
        emp = SimpleNamespace(status="active", hire_date=date(2022, 1, 1), gender="male",
                              payroll_group=None, pay_grade_key=None, department_id=dept.id)
        salary = SimpleNamespace(amount_mode="dept_row", base_amount=None,
                                 source_salary_row_id=row.id, chuyen_can=0)
        assert svc._resolve_salary(emp, salary, params, date(2026, 6, 1))["monthly"] == 8_000_000
        row.luong_vi_tri = 7_000_000            # sửa bảng lương của tổ
        db.commit()
        assert svc._resolve_salary(emp, salary, params, date(2026, 6, 1))["monthly"] == 9_000_000
    finally:
        db.close()


def test_resolve_dept_row_manual_override_wins(client):
    """Mức nhập tay (manual) ưu tiên hơn dept_row trong _resolve."""
    client
    db = SessionLocal()
    try:
        svc, dept, row = _dept_row_svc(
            db, "Tổ Bồi (override)", luong_vi_tri=6_000_000, luong_trach_nhiem=2_000_000, phu_cap=1_000_000)
        params = svc.get_params()
        emp = SimpleNamespace(status="active", hire_date=date(2022, 1, 1), gender="male",
                              payroll_group=None, pay_grade_key=None, department_id=dept.id)
        salary = SimpleNamespace(amount_mode="manual", base_amount=12_345_000,
                                 source_salary_row_id=row.id)
        res = svc._resolve_salary(emp, salary, params, date(2026, 6, 1))
        assert res["source"] == "manual" and res["monthly"] == 12_345_000
    finally:
        db.close()


def test_resolve_dept_row_inactive_falls_through(client):
    """Dòng bị vô hiệu/xóa → không dùng dept_row; rơi về rule/none như cũ."""
    client
    db = SessionLocal()
    try:
        svc, dept, row = _dept_row_svc(
            db, "Tổ Bồi (inactive)", luong_vi_tri=6_000_000, luong_trach_nhiem=2_000_000)
        params = svc.get_params()
        emp = SimpleNamespace(status="active", hire_date=date(2022, 1, 1), gender="male",
                              payroll_group=None, pay_grade_key=None, department_id=dept.id)
        salary = SimpleNamespace(amount_mode="dept_row", base_amount=None, source_salary_row_id=row.id)
        row.is_active = False
        db.commit()
        res = svc._resolve_salary(emp, salary, params, date(2026, 6, 1))
        assert res["source"] == "none" and res["monthly"] == 0.0   # không rule → 0
    finally:
        db.close()


def test_compute_dept_row_per_employee_pc_cc(client):
    """_compute dept_row: monthly = vị trí+trách nhiệm; phụ cấp + chuyên cần theo NV; OT KHÔNG gồm phụ cấp."""
    client
    db = SessionLocal()
    try:
        svc, dept, row = _dept_row_svc(
            db, "Tổ Bồi (compute)", luong_vi_tri=7_000_000, luong_trach_nhiem=2_000_000)  # monthly nền = 9tr
        params = svc.get_params()
        salary = SimpleNamespace(amount_mode="dept_row", base_amount=None, source_salary_row_id=row.id,
                                 allowance=1_000_000, insurance_base=None, chuyen_can=300_000)
        emp = SimpleNamespace(status="active", hire_date=date(2022, 1, 1), gender="male",
                              payroll_group=None, pay_grade_key=None, department_id=dept.id)
        # đủ công → luong_cong = 9tr; chuyên cần 300k (theo NV) + phụ cấp 1tr (phẳng)
        full = svc._compute(employee=emp, salary=salary, params=params, actual_cong=26,
                            standard_cong=26, on=date(2026, 6, 1))
        assert full["monthly_salary"] == 9_000_000 and full["luong_cong"] == 9_000_000
        assert full["chuyen_can"] == 300_000
        assert full["gross"] == 9_000_000 + 300_000 + 1_000_000
        # nửa công → luong_cong prorate; chuyên cần = 0; phụ cấp vẫn cộng phẳng
        half = svc._compute(employee=emp, salary=salary, params=params, actual_cong=13,
                            standard_cong=26, on=date(2026, 6, 1))
        assert half["luong_cong"] == 4_500_000 and half["chuyen_can"] == 0
        assert half["gross"] == 4_500_000 + 1_000_000
        # thử việc → ×80% trên luong_cong (nền vị trí+trách nhiệm)
        emp_tv = SimpleNamespace(status="probation", hire_date=date(2026, 5, 1), gender="male",
                                 payroll_group=None, pay_grade_key=None, department_id=dept.id)
        tv = svc._compute(employee=emp_tv, salary=salary, params=params, actual_cong=26,
                          standard_cong=26, on=date(2026, 6, 1))
        assert tv["luong_cong"] == round(9_000_000 * 0.80)
        # OT chỉ trên vị trí+trách nhiệm — phụ cấp KHÔNG ảnh hưởng tiền tăng ca
        sal_lo = SimpleNamespace(amount_mode="dept_row", base_amount=None, source_salary_row_id=row.id,
                                 allowance=0, insurance_base=None, chuyen_can=0)
        sal_hi = SimpleNamespace(amount_mode="dept_row", base_amount=None, source_salary_row_id=row.id,
                                 allowance=5_000_000, insurance_base=None, chuyen_can=0)
        ot_lo = svc._compute(employee=emp, salary=sal_lo, params=params, actual_cong=26, standard_cong=26,
                             ot_minutes=120, on=date(2026, 6, 1))
        ot_hi = svc._compute(employee=emp, salary=sal_hi, params=params, actual_cong=26, standard_cong=26,
                             ot_minutes=120, on=date(2026, 6, 1))
        assert ot_lo["ot_pay"] == ot_hi["ot_pay"] and ot_lo["ot_pay"] > 0
        assert ot_hi["gross"] == ot_lo["gross"] + 5_000_000
    finally:
        db.close()


def test_bhxh_cap(client):
    """Pha 4a: BHXH/BHYT áp trần bh_base_cap, BHTN áp trần bhtn_base_cap RIÊNG."""
    client
    db = SessionLocal()
    try:
        svc = PayrollService(PayrollRepository(db), EmployeeRepository(db), attendance=None)
        svc.payroll.create_rule(payroll_group="hi_grp", monthly_amount=60_000_000,
                                effective_from=date(2020, 1, 1))
        params = svc.get_params()   # bh_base_cap=50.6tr, bhtn_base_cap=106.2tr
        emp = SimpleNamespace(status="active", hire_date=date(2020, 1, 1), gender="male",
                              payroll_group="hi_grp", pay_grade_key=None)
        v = svc._compute(employee=emp, salary=None, params=params, actual_cong=26,
                         standard_cong=26, on=date(2026, 6, 1))
        # base 60tr > trần BHXH/BHYT 50.6tr → phần đó trên 50.6tr; BHTN 60tr < 106.2tr → trên 60tr.
        assert v["bhxh"] == round(50_600_000 * (0.08 + 0.015) + 60_000_000 * 0.01)
    finally:
        db.close()


def test_probation_no_bhxh(client):
    """Pha 4a: NV thử việc KHÔNG đóng BHXH (HĐ thử việc)."""
    client
    db = SessionLocal()
    try:
        svc = PayrollService(PayrollRepository(db), EmployeeRepository(db), attendance=None)
        svc.payroll.create_rule(payroll_group="pb_grp", monthly_amount=12_000_000,
                                effective_from=date(2020, 1, 1))
        params = svc.get_params()
        emp = SimpleNamespace(status="probation", hire_date=date(2026, 5, 1), gender="male",
                              payroll_group="pb_grp", pay_grade_key=None)
        v = svc._compute(employee=emp, salary=None, params=params, actual_cong=26,
                         standard_cong=26, on=date(2026, 6, 1))
        assert v["bhxh"] == 0 and v["insurance_base"] == 0
        assert v["luong_cong"] == round(12_000_000 * 0.80)   # thử việc 80% (mặc định công ty)
    finally:
        db.close()


def test_update_line_keeps_ot_night_pay(client):
    """Pha 4a (bẫy C2): sửa ô tay (vi phạm) KHÔNG được xóa tăng ca/ca đêm khỏi gross."""
    token = _admin_token(client)
    emp_id = _make_emp(client, token, name="NV OT", payroll_group="x", status="active")
    db = SessionLocal()
    try:
        repo = PayrollRepository(db)
        svc = PayrollService(repo, EmployeeRepository(db), attendance=None)
        period = repo.create_period(year=2026, month=6, status="draft", standard_cong=26)
        ln = repo.create_line(period_id=period.id, employee_id=emp_id,
                              luong_cong=10_000_000, chuyen_can=300_000, allowance=0,
                              ot_pay=375_000, night_pay=600_000, bhxh=1_050_000)
        updated = svc.update_line(line_id=ln.id, actor=None, vi_pham=200_000)
        assert float(updated.ot_pay) == 375_000 and float(updated.night_pay) == 600_000
        # gross vẫn còn OT + ca đêm, chỉ trừ thêm vi phạm 200k.
        assert float(updated.gross) == 10_000_000 + 300_000 + 375_000 + 600_000 - 200_000
        assert float(updated.net_pay) == float(updated.gross) - 1_050_000
    finally:
        db.close()


# --- TNCN tự tính (Pha 4b) --------------------------------------------------


def test_params_deduction_2026(client):
    """Giảm trừ gia cảnh mặc định = mức 2026 (NQ 110/2025)."""
    token = _admin_token(client)
    p = client.get("/api/luong/params", headers=_h(token)).json()
    assert p["deduction_self"] == 15_500_000 and p["deduction_dependent"] == 6_200_000


def test_pit_brackets_seeded_and_editable(client):
    """Biểu thuế TNCN seed 5 bậc 2026 + sửa được."""
    token = _admin_token(client)
    items = client.get("/api/luong/pit-brackets", headers=_h(token)).json()["items"]
    assert len(items) == 5
    assert items[0]["rate"] == 0.05
    assert items[-1]["up_to"] is None and items[-1]["rate"] == 0.35
    bid = items[0]["id"]
    upd = client.put(f"/api/luong/pit-brackets/{bid}",
                     json={"seq": 1, "up_to": 11_000_000, "rate": 0.05}, headers=_h(token))
    assert upd.status_code == 200 and upd.json()["up_to"] == 11_000_000


def test_pit_progressive(client):
    """Lũy tiến từng phần: thu nhập tính thuế 20tr → 1,5tr (10tr×5% + 10tr×10%)."""
    client
    db = SessionLocal()
    try:
        svc = PayrollService(PayrollRepository(db), EmployeeRepository(db), attendance=None)
        params, brackets = svc.get_params(), svc.get_pit_brackets()
        # gross 35,5tr, không OT/đêm/BHXH, 0 phụ thuộc → tính thuế = 35,5 − 15,5 = 20tr.
        taxable, pit = svc._auto_pit(gross=35_500_000, bhxh=0, ot_pay=0, night_pay=0,
                                     dependents_count=0, params=params, brackets=brackets)
        assert taxable == 20_000_000
        assert pit == 1_500_000
    finally:
        db.close()


def test_pit_exempt_ot_night(client):
    """OT + ca đêm được MIỄN thuế (Luật 109/2025) → giảm thu nhập chịu thuế."""
    client
    db = SessionLocal()
    try:
        svc = PayrollService(PayrollRepository(db), EmployeeRepository(db), attendance=None)
        params, brackets = svc.get_params(), svc.get_pit_brackets()
        # gross 35,5tr trong đó 5tr OT + 2tr ca đêm (miễn) → chịu thuế 28,5tr → tính thuế 13tr.
        taxable, pit = svc._auto_pit(gross=35_500_000, bhxh=0, ot_pay=5_000_000, night_pay=2_000_000,
                                     dependents_count=0, params=params, brackets=brackets)
        assert taxable == 13_000_000
        assert pit == round(10_000_000 * 0.05 + 3_000_000 * 0.10)   # 800k
    finally:
        db.close()


def test_pit_dependents_reduce_tax(client):
    """Người phụ thuộc giảm thu nhập tính thuế (6,2tr/người)."""
    client
    db = SessionLocal()
    try:
        svc = PayrollService(PayrollRepository(db), EmployeeRepository(db), attendance=None)
        params, brackets = svc.get_params(), svc.get_pit_brackets()
        # gross 35,5tr, 2 phụ thuộc (12,4tr) → tính thuế = 20tr − 12,4tr = 7,6tr.
        taxable, pit = svc._auto_pit(gross=35_500_000, bhxh=0, ot_pay=0, night_pay=0,
                                     dependents_count=2, params=params, brackets=brackets)
        assert taxable == 7_600_000
        assert pit == round(7_600_000 * 0.05)
    finally:
        db.close()


def test_pit_manual_override_and_reset(client):
    """pit tự tính; HCNS ghi đè tay (pit_manual) → giữ; reset (pit_manual=False) → về auto."""
    token = _admin_token(client)
    emp_id = _make_emp(client, token, name="NV Thuế", payroll_group="x", status="active")
    db = SessionLocal()
    try:
        repo = PayrollRepository(db)
        svc = PayrollService(repo, EmployeeRepository(db), attendance=None)
        period = repo.create_period(year=2026, month=6, status="draft", standard_cong=26)
        ln = repo.create_line(period_id=period.id, employee_id=emp_id,
                              luong_cong=50_000_000, gross=50_000_000, bhxh=0)
        # auto: sửa (chưa manual) → pit tính lại theo gross.
        upd = svc.update_line(line_id=ln.id, actor=None, vi_pham=0)
        auto_pit = float(upd.pit)
        assert auto_pit > 0 and upd.pit_manual is False
        # ghi đè tay.
        upd2 = svc.update_line(line_id=ln.id, actor=None, pit=1_234_000)
        assert float(upd2.pit) == 1_234_000 and upd2.pit_manual is True
        # reset về tự tính.
        upd3 = svc.update_line(line_id=ln.id, actor=None, pit_manual=False)
        assert float(upd3.pit) == auto_pit and upd3.pit_manual is False
    finally:
        db.close()


# --- Chi trả + xuất file + nhật ký (Pha 4c) ---------------------------------


def test_pay_unpay_flow(client):
    """State machine: nháp→chốt→đã chi→hủy chi; chặn pay-khi-chưa-chốt, reopen/generate-khi-đã-chi."""
    token = _admin_token(client)
    _make_emp(client, token, name="NV Chi", payroll_group="x", status="active")
    y, m = 2026, 6
    assert client.post("/api/luong/generate", json={"year": y, "month": m}, headers=_h(token)).status_code == 200
    # pay khi CHƯA chốt → 400
    assert client.post("/api/luong/pay", json={"year": y, "month": m}, headers=_h(token)).status_code == 400
    assert client.post("/api/luong/lock", json={"year": y, "month": m}, headers=_h(token)).status_code == 200
    paid = client.post("/api/luong/pay", json={"year": y, "month": m}, headers=_h(token))
    assert paid.status_code == 200 and paid.json()["status"] == "paid" and paid.json()["paid_at"]
    # reopen / generate khi ĐÃ CHI → chặn
    assert client.post("/api/luong/reopen", json={"year": y, "month": m}, headers=_h(token)).status_code == 400
    assert client.post("/api/luong/generate", json={"year": y, "month": m}, headers=_h(token)).status_code in (400, 409)
    # hủy chi → về locked
    un = client.post("/api/luong/unpay", json={"year": y, "month": m, "note": "nhầm"}, headers=_h(token))
    assert un.status_code == 200 and un.json()["status"] == "locked" and un.json()["paid_at"] is None


def test_export_xlsx_smoke(client):
    """Xuất bảng lương + file chuyển khoản .xlsx trả 200 + đúng content-type Excel."""
    token = _admin_token(client)
    _make_emp(client, token, name="NV Xls", payroll_group="x", status="active")
    y, m = 2026, 6
    client.post("/api/luong/generate", json={"year": y, "month": m}, headers=_h(token))
    r1 = client.get(f"/api/luong/export.xlsx?year={y}&month={m}", headers=_h(token))
    assert r1.status_code == 200 and "spreadsheetml" in r1.headers["content-type"]
    r2 = client.get(f"/api/luong/bank.xlsx?year={y}&month={m}", headers=_h(token))
    assert r2.status_code == 200 and "spreadsheetml" in r2.headers["content-type"]


def test_payroll_audit_logged(client):
    """Thao tác lương ghi nhật ký (tạo bảng / chốt) — hiện ở Nhật ký chung."""
    token = _admin_token(client)
    _make_emp(client, token, name="NV Audit", payroll_group="x", status="active")
    y, m = 2026, 6
    client.post("/api/luong/generate", json={"year": y, "month": m}, headers=_h(token))
    client.post("/api/luong/lock", json={"year": y, "month": m}, headers=_h(token))
    db = SessionLocal()
    try:
        from sqlalchemy import select

        from app.models.audit import AuditLog
        actions = [a.action for a in db.execute(select(AuditLog)).scalars()]
        assert "payroll_generate" in actions and "payroll_lock" in actions
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


def test_my_advance_self_create(client):
    """Nhân viên TỰ lập đề nghị tạm ứng (self-service) → pending → hiện ở list HCNS;
    payload có sẵn dept/bank cho phiếu in."""
    token = _admin_token(client)  # admin có hồ sơ (backfill) → coi như 1 NV tự ứng
    created = client.post("/api/luong/advances/me", json={
        "period_year": 2026, "period_month": 6,
        "advance_date": "2026-06-12", "amount": 1_500_000, "reason": "Tự ứng",
    }, headers=_h(token))
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["status"] == "pending"
    import re
    assert re.match(r"^TU-\d{6}-[A-Z0-9]{4}$", body.get("code") or ""), body.get("code")  # TU-YYMMDD-XXXX
    for k in ("department_name", "bank_account", "bank_name", "employee_name"):
        assert k in body  # field cho phiếu in (giá trị có thể None)
    aid = body["id"]
    mine = client.get("/api/luong/advances/me", headers=_h(token)).json()
    assert mine["has_employee"] is True and any(a["id"] == aid for a in mine["items"])
    listed = client.get("/api/luong/advances?year=2026&month=6", headers=_h(token)).json()["items"]
    assert any(a["id"] == aid for a in listed)
    # badge real-time: người có quyền duyệt thấy số 'chờ duyệt' > 0
    summ = client.get("/api/luong/advances/notify-summary", headers=_h(token)).json()
    assert summ["pending_approval_count"] >= 1


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

    # sửa ô tay: vi phạm 500k + thưởng 5tr → gross/net tính lại. Thưởng đủ lớn để 500k nằm trong
    # trần khấu trừ 30% (Điều 102) → khoản phạt được áp trọn.
    upd = client.put(f"/api/luong/lines/{lid}", json={"vi_pham": 500_000, "other_bonus": 5_000_000},
                     headers=_h(token)).json()
    assert upd["vi_pham"] == 500_000 and upd["other_bonus"] == 5_000_000
    exp_gross = upd["luong_cong"] + upd["chuyen_can"] + upd["allowance"] + 5_000_000 - 500_000
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


# --- Nhóm ĐỎ: vá lỗi tiền/luật engine lương ---------------------------------


def test_dis_deduction_capped_30pct(client):
    """#2b Điều 102: khấu trừ kỷ luật (vi_pham) ≤ 30% lương sau BHXH+TNCN; vượt thì kẹp."""
    client
    db = SessionLocal()
    try:
        svc = PayrollService(PayrollRepository(db), EmployeeRepository(db), attendance=None)
        svc.payroll.create_rule(payroll_group="d102", monthly_amount=20_000_000,
                                effective_from=date(2020, 1, 1))
        params = svc.get_params()
        emp = SimpleNamespace(status="active", hire_date=date(2020, 1, 1), gender="male",
                              payroll_group="d102", pay_grade_key=None)
        # phạt khủng 100tr → cột vi_pham LƯU RAW; phần kẹp chỉ ảnh hưởng gross (trần 30%).
        v = svc._compute(employee=emp, salary=None, params=params, actual_cong=26, standard_cong=26,
                         vi_pham=100_000_000, on=date(2026, 6, 1))
        assert v["vi_pham"] == 100_000_000            # RAW (không còn capped)
        income = (v["luong_cong"] + v["chuyen_can"] + v["allowance"] + v["khoan"]
                  + v["ot_pay"] + v["night_pay"] + v["other_bonus"])
        phat_eff = income - v["gross"]                # gross = income − phạt đã kẹp
        base = income - v["bhxh"] - v["pit"]
        assert 0 < phat_eff < 100_000_000
        assert abs(phat_eff - round(0.30 * base)) <= 1
    finally:
        db.close()


def test_bonus_items_taxable(client):
    """Thưởng chi tiết = thu nhập chịu thuế: gross tăng đúng Σ thưởng (dieu_chinh âm giảm); PIT tăng."""
    client
    db = SessionLocal()
    try:
        svc = PayrollService(PayrollRepository(db), EmployeeRepository(db), attendance=None)
        svc.payroll.create_rule(payroll_group="bonus_grp", monthly_amount=30_000_000,
                                effective_from=date(2020, 1, 1))
        params = svc.get_params()
        emp = SimpleNamespace(status="active", hire_date=date(2020, 1, 1), gender="male",
                              payroll_group="bonus_grp", pay_grade_key=None, dependents_count=0)
        base = svc._compute(employee=emp, salary=None, params=params, actual_cong=26, standard_cong=26,
                            on=date(2026, 6, 1))
        withb = svc._compute(employee=emp, salary=None, params=params, actual_cong=26, standard_cong=26,
                             thuong_5s=1_000_000, thuong_doanh_so=2_000_000, dieu_chinh_luong=-500_000,
                             on=date(2026, 6, 1))
        assert withb["thuong_5s"] == 1_000_000 and withb["thuong_doanh_so"] == 2_000_000
        assert withb["dieu_chinh_luong"] == -500_000
        assert withb["gross"] == base["gross"] + 2_500_000     # 1tr + 2tr − 0.5tr
        assert withb["pit"] > base["pit"]                      # thưởng chịu thuế → PIT tăng
    finally:
        db.close()


def test_cong_doan_auto(client):
    """Đoàn phí công đoàn = insurance_base × cong_doan_rate; thử việc = 0."""
    client
    db = SessionLocal()
    try:
        svc = PayrollService(PayrollRepository(db), EmployeeRepository(db), attendance=None)
        svc.update_params(cong_doan_rate=0.005)
        svc.payroll.create_rule(payroll_group="cd_grp", monthly_amount=10_000_000,
                                effective_from=date(2020, 1, 1))
        params = svc.get_params()
        emp = SimpleNamespace(status="active", hire_date=date(2020, 1, 1), gender="male",
                              payroll_group="cd_grp", pay_grade_key=None, dependents_count=0)
        v = svc._compute(employee=emp, salary=None, params=params, actual_cong=26, standard_cong=26,
                         on=date(2026, 6, 1))
        assert v["cong_doan"] == round(v["insurance_base"] * 0.005) and v["cong_doan"] > 0
        emp_tv = SimpleNamespace(status="probation", hire_date=date(2026, 5, 1), gender="male",
                                 payroll_group="cd_grp", pay_grade_key=None, dependents_count=0)
        v_tv = svc._compute(employee=emp_tv, salary=None, params=params, actual_cong=26,
                            standard_cong=26, on=date(2026, 6, 1))
        assert v_tv["cong_doan"] == 0
        svc.update_params(cong_doan_rate=0)   # khôi phục
    finally:
        db.close()


def test_penalties_share_30pct_cap(client):
    """5 khoản phạt gộp CHUNG 1 trần 30%; từng cột lưu RAW (không capped riêng)."""
    client
    db = SessionLocal()
    try:
        svc = PayrollService(PayrollRepository(db), EmployeeRepository(db), attendance=None)
        svc.payroll.create_rule(payroll_group="pen_grp", monthly_amount=20_000_000,
                                effective_from=date(2020, 1, 1))
        params = svc.get_params()
        emp = SimpleNamespace(status="active", hire_date=date(2020, 1, 1), gender="male",
                              payroll_group="pen_grp", pay_grade_key=None, dependents_count=0)
        v = svc._compute(employee=emp, salary=None, params=params, actual_cong=26, standard_cong=26,
                         vi_pham=30_000_000, di_tre=30_000_000, dt_vuot_troi=30_000_000,
                         phat_bien_ban=30_000_000, phat_5s_dong_phuc=30_000_000, on=date(2026, 6, 1))
        for k in ("vi_pham", "di_tre", "dt_vuot_troi", "phat_bien_ban", "phat_5s_dong_phuc"):
            assert v[k] == 30_000_000                          # RAW
        income = (v["luong_cong"] + v["chuyen_can"] + v["allowance"] + v["khoan"]
                  + v["ot_pay"] + v["night_pay"] + v["other_bonus"])
        phat_eff = income - v["gross"]
        base = income - v["bhxh"] - v["pit"]
        assert abs(phat_eff - round(0.30 * base)) <= 1         # gộp về đúng trần 30%
    finally:
        db.close()


def test_generate_preserves_detail_and_net_cong_doan(client):
    """generate: preserve ô tay chi tiết khi Tính lại; net TRỪ công đoàn."""
    token = _admin_token(client)
    client.put("/api/luong/params", json={"cong_doan_rate": 0.005}, headers=_h(token))
    eid = _make_emp(client, token, name="NV Phiếu", status="active")
    client.post(f"/api/luong/salaries/{eid}", json={"effective_from": "2026-01-01",
                "amount_mode": "manual", "base_amount": 5_000_000}, headers=_h(token))
    gen = client.post("/api/luong/generate", json={"year": 2026, "month": 8}, headers=_h(token)).json()
    line = next(l for l in gen["lines"] if l["employee_id"] == eid)
    client.put(f"/api/luong/lines/{line['id']}",
               json={"thuong_5s": 5_000_000, "di_tre": 200_000}, headers=_h(token))
    gen2 = client.post("/api/luong/generate", json={"year": 2026, "month": 8}, headers=_h(token)).json()
    l2 = next(l for l in gen2["lines"] if l["employee_id"] == eid)
    assert l2["thuong_5s"] == 5_000_000 and l2["di_tre"] == 200_000     # preserve
    assert l2["cong_doan"] == round(l2["insurance_base"] * 0.005)
    assert l2["net_pay"] == round(max(0.0, l2["gross"] - l2["bhxh"] - l2["cong_doan"]
                                      - l2["pit"] - l2["advance_total"]))
    assert l2["net_pay"] > 0                                    # dương → chứng minh có trừ công đoàn
    client.put("/api/luong/params", json={"cong_doan_rate": 0}, headers=_h(token))   # khôi phục


def test_net_floored_at_zero(client):
    """#2a: tạm ứng vượt lương thực → thực nhận = 0, KHÔNG âm."""
    token = _admin_token(client)
    client.post("/api/luong/rules", json={"payroll_group": "flr", "monthly_amount": 10_000_000,
                "effective_from": "2026-01-01"}, headers=_h(token))
    eid = _make_emp(client, token, name="NV Sàn", payroll_group="flr", status="active")
    client.post(f"/api/luong/salaries/{eid}", json={"effective_from": "2026-01-01",
                "amount_mode": "rule"}, headers=_h(token))
    aid = client.post("/api/luong/advances", json={"employee_id": eid, "period_year": 2027,
        "period_month": 3, "advance_date": "2027-03-05", "amount": 5_000_000},
        headers=_h(token)).json()["id"]
    client.post(f"/api/luong/advances/{aid}/approve", json={}, headers=_h(token))
    gen = client.post("/api/luong/generate", json={"year": 2027, "month": 3}, headers=_h(token)).json()
    line = next(l for l in gen["lines"] if l["employee_id"] == eid)
    assert line["net_pay"] == 0   # 0 công + tạm ứng 5tr → sàn 0, không âm


def test_standard_cong_from_params(client):
    """Công chuẩn (mẫu số chia lương công) lấy từ THAM SỐ CHUNG `standard_cong_default`, KHÔNG
    động theo Lịch — đổi tham số thì mẫu số đổi theo; cấu hình lịch KHÔNG ảnh hưởng mẫu số."""
    token = _admin_token(client)
    assert client.put("/api/luong/params", json={"standard_cong_default": 24},
                      headers=_h(token)).status_code == 200
    # Cấu hình lịch bỏ T7 → nếu còn tính động sẽ ra ≠ 24; nhưng mẫu số PHẢI = 24 (tham số chung).
    assert client.put("/api/calendar/config", json={"works_sat": False},
                      headers=_h(token)).status_code == 200
    assert client.post("/api/luong/generate", json={"year": 2027, "month": 9},
                       headers=_h(token)).status_code == 200
    with SessionLocal() as db:
        p = PayrollRepository(db).get_period_by_ym(2027, 9)
        assert float(p.standard_cong) == 24
    client.put("/api/luong/params", json={"standard_cong_default": 26}, headers=_h(token))  # khôi phục


def test_luong_cong_capped_at_standard(client):
    """Chặn trần: làm ĐỦ (≥ công chuẩn) → nguyên lương tháng (không trả dư tháng dài); thiếu → prorate."""
    client
    db = SessionLocal()
    try:
        svc = PayrollService(PayrollRepository(db), EmployeeRepository(db), attendance=None)
        svc.payroll.create_rule(payroll_group="cap_grp", monthly_amount=13_000_000,
                                effective_from=date(2020, 1, 1))
        params = svc.get_params()
        emp = SimpleNamespace(status="active", hire_date=date(2020, 1, 1), gender="male",
                              payroll_group="cap_grp", pay_grade_key=None)
        # 27 công / chuẩn 26 → chặn trần = nguyên 13tr (KHÔNG 27/26 = dư)
        over = svc._compute(employee=emp, salary=None, params=params, actual_cong=27,
                            standard_cong=26, on=date(2026, 7, 1))
        assert over["luong_cong"] == 13_000_000
        # 13 công / 26 → nửa lương
        half = svc._compute(employee=emp, salary=None, params=params, actual_cong=13,
                            standard_cong=26, on=date(2026, 7, 1))
        assert half["luong_cong"] == 6_500_000
    finally:
        db.close()


def test_special_day_premium(client):
    """#3 Đ98: làm nguyên công ngày lễ = +200% premium (base 100% đã nằm trong lương công);
    OT ngày lễ ×3, OT ngày nghỉ tuần ×2."""
    client
    db = SessionLocal()
    try:
        svc = PayrollService(PayrollRepository(db), EmployeeRepository(db), attendance=None)
        svc.payroll.create_rule(payroll_group="sd", monthly_amount=26_000_000,
                                effective_from=date(2020, 1, 1))
        params = svc.get_params()   # ot 1.5 · ot_rest 2 · ot_hol 3 · hol_wm 3 · rest_wm 2
        emp = SimpleNamespace(status="active", hire_date=date(2020, 1, 1), gender="male",
                              payroll_group="sd", pay_grade_key=None)
        daily = 26_000_000 / 26   # 1.000.000 ; giờ = 125.000
        # 1 công ngày lễ (nằm trong 26 công) → premium = 1×(3−1)×daily = 2.000.000, không OT.
        v = svc._compute(employee=emp, salary=None, params=params, actual_cong=26, standard_cong=26,
                         holiday_cong=1, on=date(2026, 6, 1))
        assert v["ot_pay"] == round(daily * (3 - 1))   # 2.000.000 premium lễ
        # OT: 60' ngày lễ ×3 + 60' ngày nghỉ tuần ×2 (tổng ot_minutes = 120, không có OT thường).
        v2 = svc._compute(employee=emp, salary=None, params=params, actual_cong=26, standard_cong=26,
                          ot_minutes=120, ot_holiday_minutes=60, ot_restday_minutes=60,
                          on=date(2026, 6, 1))
        hourly = daily / 8   # 125.000
        assert v2["ot_pay"] == round(hourly * (1 * 3 + 1 * 2))   # 125k × 5 = 625.000
    finally:
        db.close()
