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


def _sal(**kw):
    """Salary namespace cho engine test — mức nền + BH đều bám `luong_vi_tri` (chủ 2026-07-20:
    lương vị trí = lương cơ bản = mức đóng BH). Field đủ cho mọi getattr của _compute."""
    base = dict(amount_mode="manual", base_amount=None, luong_vi_tri=0, luong_trach_nhiem=0,
                insurance_base=None, allowance=0, chuyen_can=0, phu_cap_ca=0, phu_cap_tham_nien=0,
                insurance_elsewhere=False, union_member=False, source_salary_row_id=None)
    base.update(kw)
    return SimpleNamespace(**base)


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


def test_payroll_resolves_historical_status_and_department_from_employee_events(client):
    token = _admin_token(client)
    old_dept = _dept_id("Hành chính nhân sự")
    new_dept = _dept_id("Kinh doanh")
    employee_id = _make_emp(
        client, token, name="NV lịch sử lương", hire_date="2026-01-01", status="probation"
    )
    assert client.post(
        f"/api/employees/{employee_id}/transitions",
        json={"kind": "confirm", "effective_date": "2026-03-01"},
        headers=_h(token),
    ).status_code == 200
    assert client.post(
        f"/api/employees/{employee_id}/transitions",
        json={"kind": "transfer", "new_department_id": new_dept, "effective_date": "2026-04-01"},
        headers=_h(token),
    ).status_code == 200

    db = SessionLocal()
    try:
        employees = EmployeeRepository(db)
        svc = PayrollService(PayrollRepository(db), employees, attendance=None)
        employee = employees.get_by_id(employee_id)
        assert svc._employment_context_on(employee, date(2026, 2, 28)) == ("probation", old_dept)
        assert svc._employment_context_on(employee, date(2026, 3, 31)) == ("active", old_dept)
        assert svc._employment_context_on(employee, date(2026, 4, 30)) == ("active", new_dept)
    finally:
        db.close()


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
        v = svc._compute(employee=emp, salary=_sal(luong_vi_tri=10_000_000), params=params, actual_cong=13,
                         standard_cong=26, on=on)
        assert v["monthly_salary"] == 10_000_000
        assert v["luong_cong"] == 5_000_000
        assert v["chuyen_can"] == 0
        assert v["bhxh"] == round(10_000_000 * 0.105)   # 1.050.000, không prorate

        # đủ công → lương công đủ. Chuyên cần = số khai ở HỒ SƠ NV (chưa khai → 0đ; từ 2026-07-23
        # bỏ mức mặc định công ty, không còn tự rơi về 300k).
        v2 = svc._compute(employee=emp, salary=_sal(luong_vi_tri=10_000_000), params=params, actual_cong=26,
                          standard_cong=26, on=on)
        assert v2["luong_cong"] == 10_000_000 and v2["chuyen_can"] == 0
        assert v2["gross"] == 10_000_000
        # Khai chuyên cần ở hồ sơ NV → mới ra tiền.
        v2b = svc._compute(employee=emp, salary=_sal(luong_vi_tri=10_000_000, chuyen_can=300_000),
                           params=params, actual_cong=26, standard_cong=26, on=on)
        assert v2b["chuyen_can"] == 300_000 and v2b["gross"] == 10_300_000

        # thử việc → ×0.8.
        emp_tv = SimpleNamespace(status="probation", hire_date=date(2026, 5, 1), gender="male",
                                 payroll_group="ut_grp", pay_grade_key=None)
        v3 = svc._compute(employee=emp_tv, salary=_sal(luong_vi_tri=10_000_000), params=params, actual_cong=26,
                          standard_cong=26, on=on)
        assert v3["monthly_salary"] == 10_000_000       # mức gốc (chưa nhân)
        assert v3["luong_cong"] == 8_000_000            # 10tr × 0.80 × 1.0 (công ty dùng 80%)
        assert v3["bhxh"] == 0                          # thử việc KHÔNG đóng BHXH (HĐ thử việc)
    finally:
        db.close()


def test_ot_and_night_pay(client):
    """Tăng ca (hệ số phẳng) cộng vào gross, KHÔNG prorate theo công. Tiền ca đêm KHÔNG còn
    tính theo % đơn giá công (PRD v2 C4) → tổ chưa khai đơn giá ca thì night_pay = 0."""
    client
    db = SessionLocal()
    try:
        svc = PayrollService(PayrollRepository(db), EmployeeRepository(db), attendance=None)
        svc.payroll.create_rule(payroll_group="ot_grp", monthly_amount=26_000_000,
                                effective_from=date(2020, 1, 1))
        params = svc.get_params()   # standard_hours_per_day=8, ot_multiplier=1.5
        emp = SimpleNamespace(status="active", hire_date=date(2020, 1, 1), gender="male",
                              payroll_group="ot_grp", pay_grade_key=None)
        # std 26 → 1 công = 1.000.000; giờ = 125.000. OT 120' (2h)×1.5 = 375.000.
        v = svc._compute(employee=emp, salary=_sal(luong_vi_tri=26_000_000), params=params, actual_cong=26,
                         standard_cong=26, ot_minutes=120, night_days=2, on=date(2026, 6, 1))
        assert v["ot_pay"] == 375_000
        assert v["night_pay"] == 0            # chưa khai đơn giá ca của tổ → không ra tiền
        # Chuyên cần = 0 (hồ sơ NV chưa khai; không còn mức mặc định công ty từ 2026-07-23).
        assert v["gross"] == 26_000_000 + 375_000
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
        v_norm = svc._compute(employee=emp, salary=_sal(luong_vi_tri=26_000_000), params=params, actual_cong=26,
                              standard_cong=26, ot_minutes=120, on=date(2026, 6, 1))
        v_piece = svc._compute(employee=emp, salary=_sal(luong_vi_tri=26_000_000), params=params, actual_cong=26,
                               standard_cong=26, ot_minutes=120, has_piece_work=True,
                               on=date(2026, 6, 1))
        assert v_norm["ot_pay"] == 375_000          # tổ thường vẫn tính tăng ca
        assert v_piece["ot_pay"] == 0               # tổ khoán bỏ tăng ca giờ
        # Lương công giữ nguyên, gross tổ khoán KHÔNG có phần tăng ca.
        assert v_piece["gross"] == v_norm["gross"] - 375_000
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
        v = svc._compute(employee=emp, salary=_sal(luong_vi_tri=60_000_000), params=params, actual_cong=26,
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
        v = svc._compute(employee=emp, salary=_sal(luong_vi_tri=12_000_000), params=params, actual_cong=26,
                         standard_cong=26, on=date(2026, 6, 1))
        assert v["bhxh"] == 0 and v["insurance_base"] == 0
        assert v["luong_cong"] == round(12_000_000 * 0.80)   # thử việc 80% (mặc định công ty)
    finally:
        db.close()


def test_insurance_elsewhere_only_tnld_bnn(client):
    """BH đóng ở nơi khác: công ty KHÔNG trừ BHXH/BHYT/BHTN của NV (bhxh=0) nhưng GIỮ insurance_base
    (> 0, KHÁC thử việc vốn = 0) để đoàn phí công đoàn VẪN tính. TNLĐ-BNN là chi phí phía công ty,
    không vào bảng lương tháng (chỉ hiển thị ở màn Sửa lương). Param `tnld_bnn_rate` mặc định 0.5%."""
    client
    db = SessionLocal()
    try:
        svc = PayrollService(PayrollRepository(db), EmployeeRepository(db), attendance=None)
        svc.update_params(cong_doan_rate=0.005)
        params = svc.get_params()
        assert float(params.tnld_bnn_rate) == 0.005            # mặc định TNLĐ-BNN 0.5%
        emp = SimpleNamespace(status="active", hire_date=date(2020, 1, 1), gender="male",
                              payroll_group=None, pay_grade_key=None, dependents_count=0)
        # union_member=True: đoàn viên nên đoàn phí CĐ VẪN trừ dù BH đóng ở nơi khác.
        v = svc._compute(employee=emp,
                         salary=_sal(luong_vi_tri=10_000_000, insurance_elsewhere=True, union_member=True),
                         params=params, actual_cong=26, standard_cong=26, on=date(2026, 6, 1))
        assert v["bhxh"] == 0                                  # KHÔNG trừ BHXH/BHYT/BHTN của NV
        assert v["insurance_base"] == 10_000_000               # GIỮ mức nền (khác thử việc = 0)
        assert v["cong_doan"] == round(10_000_000 * 0.005) and v["cong_doan"] > 0   # đoàn phí CĐ VẪN trừ (đoàn viên)
        # tnld_bnn_rate sửa được (round-trip qua update_params)
        svc.update_params(tnld_bnn_rate=0.007)
        assert float(svc.get_params().tnld_bnn_rate) == 0.007
        svc.update_params(cong_doan_rate=0, tnld_bnn_rate=0.005)   # khôi phục
    finally:
        db.close()


def test_compute_day_cong_late_early_minutes():
    """`compute_day_cong` cho ra SỐ PHÚT đi trễ (quá dung sai) + về sớm — nền phạt tự động."""
    from app.services.attendance_service import compute_day_cong
    # Ca 08:00–17:00 (480–1020), dung sai 5'. Vào 08:20 (500' → trễ 15' quá grace), ra 16:40 (1000' → sớm 20').
    v = compute_day_cong(start_min=480, end_min=1020, is_overnight=False, grace_min=5,
                         first_in_min=500, last_out_min=1000)
    assert v["late_minutes"] == 15 and v["early_minutes"] == 20
    # Vào trong dung sai (08:03) + ra đúng giờ → 0/0.
    v2 = compute_day_cong(start_min=480, end_min=1020, is_overnight=False, grace_min=5,
                          first_in_min=483, last_out_min=1020)
    assert v2["late_minutes"] == 0 and v2["early_minutes"] == 0


def test_late_penalty_amount_tiers(client):
    """Tra bảng phạt cho 1 lần vi phạm: bậc ĐẦU có up_to_minute ≥ phút; ∞ là chốt cuối."""
    from app.services.payroll_service import _late_penalty_amount
    db = SessionLocal()
    try:
        svc = PayrollService(PayrollRepository(db), EmployeeRepository(db), attendance=None)
        bks = svc.get_late_penalty_brackets()   # seed mặc định 20/40/100/150k
        assert _late_penalty_amount(0, bks) == 0
        assert _late_penalty_amount(10, bks) == 20_000     # ≤15'
        assert _late_penalty_amount(15, bks) == 20_000
        assert _late_penalty_amount(16, bks) == 40_000     # ≤30'
        assert _late_penalty_amount(45, bks) == 100_000    # ≤60'
        assert _late_penalty_amount(120, bks) == 150_000   # >60' (∞)
    finally:
        db.close()


def test_di_tre_auto_from_attendance(client):
    """END-TO-END: NV đi trễ (không phép) → generate() TỰ điền ô "Đi trễ" theo bảng phạt; HCNS sửa
    tay thì khóa (tính lại không đè); "về tự động" thì tính lại từ chấm công."""
    from datetime import datetime as _dt, timezone as _tz
    from app.repositories.attendance_repo import AttendanceRepository
    token = _admin_token(client)
    eid = _make_emp(client, token, name="NV Trễ", status="active")
    client.post(f"/api/luong/salaries/{eid}", json={"effective_from": "2026-01-01",
                "luong_vi_tri": 10_000_000}, headers=_h(token))
    db = SessionLocal()
    try:
        arepo = AttendanceRepository(db)
        shift = arepo.create_shift(name="HC", start_minute=480, end_minute=1020,
                                   is_overnight=False, grace_minutes=5)
        EmployeeRepository(db).get_by_id(eid).default_shift_id = shift.id
        db.commit()
        # 2026-06-15 (Thứ Hai): vào 08:30 VN (01:30 UTC → trễ 25') + ra 17:00 VN (10:00 UTC).
        arepo.create_log(employee_id=eid, check_type="in",
                         checked_at=_dt(2026, 6, 15, 1, 30, tzinfo=_tz.utc), within_range=True)
        arepo.create_log(employee_id=eid, check_type="out",
                         checked_at=_dt(2026, 6, 15, 10, 0, tzinfo=_tz.utc), within_range=True)
    finally:
        db.close()
    gen = client.post("/api/luong/generate", json={"year": 2026, "month": 6}, headers=_h(token)).json()
    line = next(l for l in gen["lines"] if l["employee_id"] == eid)
    assert line["di_tre"] == 40_000 and line["di_tre_manual"] is False   # 25' → bậc ≤30' = 40.000
    # Sửa tay → khóa; generate lại KHÔNG đè.
    client.put(f"/api/luong/lines/{line['id']}", json={"di_tre": 5_000}, headers=_h(token))
    l2 = next(l for l in client.post("/api/luong/generate", json={"year": 2026, "month": 6},
                                     headers=_h(token)).json()["lines"] if l["employee_id"] == eid)
    assert l2["di_tre"] == 5_000 and l2["di_tre_manual"] is True
    # Về tự động → update_line tính lại từ chấm công NGAY (trả về dòng đã cập nhật).
    l3 = client.put(f"/api/luong/lines/{line['id']}",
                    json={"di_tre_manual": False}, headers=_h(token)).json()
    assert l3["di_tre"] == 40_000 and l3["di_tre_manual"] is False


def test_compute_day_cong_night_minutes():
    """SỐ PHÚT rơi 22h–06h: giờ đêm TRONG ca + giờ TĂNG CA ĐÊM (sau end_ref)."""
    from app.services.attendance_service import compute_day_cong
    # Ca qua đêm 22:00–06:00 (1320→360) làm đủ → 8h đêm, 0 OT đêm.
    v = compute_day_cong(start_min=1320, end_min=360, is_overnight=True, grace_min=5,
                         first_in_min=1320, last_out_min=360)
    assert v["night_minutes"] == 480 and v["ot_night_minutes"] == 0
    # Ca qua đêm 20:00–04:00 → giờ đêm 22:00–04:00 = 6h.
    v2 = compute_day_cong(start_min=1200, end_min=240, is_overnight=True, grace_min=5,
                          first_in_min=1200, last_out_min=240)
    assert v2["night_minutes"] == 360
    # Ca THƯỜNG 14:00–22:00 kết thúc 22h, TĂNG CA tới 23:00 → giờ đêm TRONG ca = 0, tăng ca đêm 60' (chủ soi).
    v3 = compute_day_cong(start_min=840, end_min=1320, is_overnight=False, grace_min=5,
                          first_in_min=840, last_out_min=1380)
    assert v3["night_minutes"] == 0 and v3["ot_night_minutes"] == 60
    # Ca ngày 08:00–17:00 → không giờ đêm.
    v4 = compute_day_cong(start_min=480, end_min=1020, is_overnight=False, grace_min=5,
                          first_in_min=480, last_out_min=1020)
    assert v4["night_minutes"] == 0 and v4["ot_night_minutes"] == 0


def test_night_premium_engine(client):
    """Engine: (A) giờ đêm trong ca × hệ số → premium; (B) tăng ca đêm Đ98.3 (200%); miễn TNCN."""
    db = SessionLocal()
    try:
        svc = PayrollService(PayrollRepository(db), EmployeeRepository(db), attendance=None)
        params = svc.get_params()   # night_pct 0.3 · ot_night_extra_pct 0.2 · ot_multiplier 1.5 · 8h/ngày
        assert float(params.ot_night_extra_pct) == 0.2 and float(params.night_pct) == 0.3
        emp = SimpleNamespace(status="active", hire_date=date(2020, 1, 1), gender="male",
                              payroll_group=None, pay_grade_key=None, dependents_count=0)
        base = dict(employee=emp, salary=_sal(luong_vi_tri=26_000_000), params=params,
                    actual_cong=26, standard_cong=26, on=date(2026, 6, 1))   # đơn giá 1tr/công → 125k/giờ
        v0 = svc._compute(**base)
        # (A) 8h đêm × (1.3−1) = 144' → 125k × 144/60 = 300k.
        v = svc._compute(**{**base, "night_premium_minutes": 144})
        assert v["night_premium_pay"] == 300_000
        assert v["pit"] == v0["pit"] and v["pit_taxable"] == v0["pit_taxable"]   # premium MIỄN TNCN
        # (B) tăng ca đêm ngày thường 120' (2h): 125k × 2 × (0.3 + 0.2×1) = 125k (khớp OT đêm 200%).
        vb = svc._compute(**{**base, "ot_night_normal_minutes": 120})
        assert vb["night_premium_pay"] == 125_000
    finally:
        db.close()


def test_night_pay_auto_from_attendance(client):
    """END-TO-END: gán ca qua đêm (hệ số 1.3) + chấm công 1 đêm 22:00–06:00 → generate() tự điền
    'Phụ cấp ca đêm theo giờ' = 30% đơn giá 8 giờ."""
    from datetime import datetime as _dt, timezone as _tz
    from app.repositories.attendance_repo import AttendanceRepository
    token = _admin_token(client)
    eid = _make_emp(client, token, name="NV Ca đêm", status="active")
    client.post(f"/api/luong/salaries/{eid}", json={"effective_from": "2026-01-01",
                "luong_vi_tri": 26_000_000}, headers=_h(token))
    db = SessionLocal()
    try:
        arepo = AttendanceRepository(db)
        shift = arepo.create_shift(name="Ca đêm", start_minute=1320, end_minute=360,
                                   is_overnight=True, grace_minutes=5, night_multiplier=1.3)
        EmployeeRepository(db).get_by_id(eid).default_shift_id = shift.id
        db.commit()
        # Ngày công 15/06: vào 22:00 VN 15/06 (15:00 UTC) + ra 06:00 VN 16/06 (23:00 UTC 15/06).
        arepo.create_log(employee_id=eid, check_type="in",
                         checked_at=_dt(2026, 6, 15, 15, 0, tzinfo=_tz.utc), within_range=True)
        arepo.create_log(employee_id=eid, check_type="out",
                         checked_at=_dt(2026, 6, 15, 23, 0, tzinfo=_tz.utc), within_range=True)
    finally:
        db.close()
    gen = client.post("/api/luong/generate", json={"year": 2026, "month": 6}, headers=_h(token)).json()
    line = next(l for l in gen["lines"] if l["employee_id"] == eid)
    assert line["night_premium_pay"] == 300_000   # 8h × (1.3−1) = 144' → 125k × 144/60


def _setup_shift_and_punches(client, token, *, name, start_min, end_min, overnight,
                             in_utc, out_utc):
    """Tạo NV + mức lương + gán ca + 2 lượt chấm (giờ UTC). Trả employee_id."""
    from app.repositories.attendance_repo import AttendanceRepository
    eid = _make_emp(client, token, name=name, status="active")
    client.post(f"/api/luong/salaries/{eid}", json={"effective_from": "2026-01-01",
                "luong_vi_tri": 26_000_000}, headers=_h(token))
    db = SessionLocal()
    try:
        arepo = AttendanceRepository(db)
        shift = arepo.create_shift(name=name, start_minute=start_min, end_minute=end_min,
                                   is_overnight=overnight, grace_minutes=5)
        EmployeeRepository(db).get_by_id(eid).default_shift_id = shift.id
        db.commit()
        arepo.create_log(employee_id=eid, check_type="in", checked_at=in_utc, within_range=True)
        arepo.create_log(employee_id=eid, check_type="out", checked_at=out_utc, within_range=True)
    finally:
        db.close()
    return eid


def _mk_ot(client, token, eid, *, work_date, frm, to):
    """Phiếu tăng ca do người có quyền duyệt tạo hộ ⇒ APPROVED luôn."""
    r = client.post("/api/overtime", json={"employee_id": eid, "work_date": work_date,
                                           "from_minute": frm, "to_minute": to}, headers=_h(token))
    assert r.status_code == 201, r.text
    return r.json()


def _gen_line(client, token, eid):
    gen = client.post("/api/luong/generate", json={"year": 2026, "month": 6},
                      headers=_h(token)).json()
    return next(l for l in gen["lines"] if l["employee_id"] == eid)


def _tat_tran_tam_ung(client, token):
    """Tắt trần tạm ứng (0% = không giới hạn) cho các test KHÔNG nói về trần — kịch bản cũ của chúng
    (ứng số lớn, hoặc NV chưa khai lương) sẽ bị luật trần mới chặn. Trần có test riêng ở trên."""
    client.put("/api/luong/params", json={"advance_max_pct": 0}, headers=_h(token))


def _adv(client, token, eid, amount, *, month=6, expect=201):
    """HCNS lập đề nghị tạm ứng hộ NV (kỳ 2026-06)."""
    r = client.post("/api/luong/advances", json={
        "employee_id": eid, "period_year": 2026, "period_month": month,
        "advance_date": f"2026-{month:02d}-05", "amount": amount}, headers=_h(token))
    assert r.status_code == expect, r.text
    return r


def _emp_luong_10tr(client, token, name):
    eid = _make_emp(client, token, name=name, status="active")
    client.post(f"/api/luong/salaries/{eid}", json={"effective_from": "2026-01-01",
                "luong_vi_tri": 8_000_000, "luong_trach_nhiem": 2_000_000}, headers=_h(token))
    return eid   # lương tháng = 10tr → trần 10% = 1tr


def test_tran_tam_ung_chan_khi_vuot(client):
    """Trần 10% của 10tr = 1tr: ứng 600k qua, ứng thêm 500k bị chặn (chỉ còn 400k)."""
    token = _admin_token(client)
    eid = _emp_luong_10tr(client, token, "NV Tạm ứng 1")
    _adv(client, token, eid, 600_000)
    r = _adv(client, token, eid, 500_000, expect=400)
    assert "Vượt trần" in r.json()["detail"]
    assert "400" in r.json()["detail"]          # có nêu số còn lại
    _adv(client, token, eid, 400_000)           # vừa đủ trần → qua


def test_don_cho_duyet_van_chiem_han_muc(client):
    """Chủ chốt: đơn ĐANG CHỜ DUYỆT giữ chỗ — không lách được bằng cách gửi nhiều đơn nhỏ."""
    token = _admin_token(client)
    eid = _emp_luong_10tr(client, token, "NV Tạm ứng 2")
    _adv(client, token, eid, 600_000)                     # vẫn pending
    _adv(client, token, eid, 600_000, expect=400)         # tổng 1.2tr > 1tr → chặn


def test_duyet_kiem_lai_tran(client):
    """Đơn hợp lệ lúc tạo (trần cao) nhưng khi HẠ TRẦN thì DUYỆT phải bị chặn."""
    token = _admin_token(client)
    client.put("/api/luong/params", json={"advance_max_pct": 0.5}, headers=_h(token))
    eid = _emp_luong_10tr(client, token, "NV Tạm ứng 3")
    aid = _adv(client, token, eid, 3_000_000).json()["id"]     # 30% — hợp lệ lúc trần 50%
    client.put("/api/luong/params", json={"advance_max_pct": 0.1}, headers=_h(token))
    bad = client.post(f"/api/luong/advances/{aid}/approve", json={}, headers=_h(token))
    assert bad.status_code == 400 and "Vượt trần" in bad.json()["detail"]


def test_tran_0_la_khong_gioi_han(client):
    """Đặt 0% = tắt trần — đường thoát để duyệt nốt đơn tồn."""
    token = _admin_token(client)
    client.put("/api/luong/params", json={"advance_max_pct": 0}, headers=_h(token))
    eid = _emp_luong_10tr(client, token, "NV Tạm ứng 4")
    _adv(client, token, eid, 9_000_000)          # 90% lương vẫn qua


def test_chua_khai_luong_thi_chan_tam_ung(client):
    token = _admin_token(client)
    eid = _make_emp(client, token, name="NV Chưa khai lương", status="active")
    r = _adv(client, token, eid, 100_000, expect=400)
    assert "chưa khai lương" in r.json()["detail"].lower()


def test_api_quota_khop_voi_luat_chan(client):
    """Số hiện trên form ("còn được ứng") lấy CÙNG nguồn với chỗ chặn ⇒ không bao giờ lệch."""
    from app.db import SessionLocal
    from app.repositories.employee_repo import EmployeeRepository
    from app.repositories.rbac_repo import DepartmentRepository, RoleRepository
    from app.repositories.user_repo import UserRepository
    from app.security import create_access_token, hash_password

    admin = _admin_token(client)
    eid = _emp_luong_10tr(client, admin, "NV Xem hạn mức")
    _adv(client, admin, eid, 600_000)

    db = SessionLocal()
    try:
        users = UserRepository(db)
        kd = DepartmentRepository(db).get_by_name("Kinh doanh")
        role = RoleRepository(db).get_by_name_and_department("NV Sales", kd.id)
        u = users.create(username="nv-han-muc", name="NV", password_hash=hash_password("x"))
        users.set_assignment(u, department_id=kd.id, role_id=role.id, is_active=True)
        emps = EmployeeRepository(db)
        emps.update(emps.get_by_id(eid), user_id=u.id)
        tok = create_access_token(str(u.id))
    finally:
        db.close()

    q = client.get("/api/luong/advances/quota?year=2026&month=6", headers=_h(tok))
    assert q.status_code == 200, q.text
    d = q.json()
    assert d["monthly"] == 10_000_000 and d["limit"] == 1_000_000
    assert d["used"] == 600_000 and d["remaining"] == 400_000


def test_phieu_luong_tach_3_dong_bao_hiem(client):
    """Phiếu lương phải hiện RIÊNG BHXH / BHYT / BHTN (kèm tỷ lệ), và 3 dòng cộng lại ĐÚNG BẰNG
    số bảo hiểm đã đóng băng — để TỔNG TRỪ không bao giờ lệch THỰC NHẬN."""
    token = _admin_token(client)
    eid = _make_emp(client, token, name="NV Bảo hiểm", status="active")
    client.post(f"/api/luong/salaries/{eid}", json={"effective_from": "2026-01-01",
                "luong_vi_tri": 10_000_000}, headers=_h(token))
    line = _gen_line(client, token, eid)

    rows = line["insurance_lines"]
    assert [r["label"].split()[0] for r in rows] == ["BHXH", "BHYT", "BHTN"]
    assert all("%" in r["label"] for r in rows)          # nhãn kèm tỷ lệ
    assert line["bhxh"] > 0
    assert sum(r["amount"] for r in rows) == line["bhxh"]   # BẤT BIẾN: tổng khớp số đã trừ


def test_phieu_luong_bao_hiem_bang_0_van_du_3_dong(client):
    """NV được nơi khác đóng BH → không trừ đồng nào, nhưng phiếu vẫn đủ 3 mục (giá trị 0)."""
    token = _admin_token(client)
    eid = _make_emp(client, token, name="NV BH nơi khác", status="active")
    client.post(f"/api/luong/salaries/{eid}", json={"effective_from": "2026-01-01",
                "luong_vi_tri": 10_000_000, "insurance_elsewhere": True}, headers=_h(token))
    line = _gen_line(client, token, eid)
    assert line["bhxh"] == 0
    assert [r["amount"] for r in line["insurance_lines"]] == [0, 0, 0]


def test_nv_khong_co_quyen_cau_hinh_luong_van_thay_3_dong(client):
    """CA GỐC CỦA BUG: nhân viên xem phiếu của CHÍNH MÌNH (không có `luong:view_salary`) trước đây
    chỉ thấy 1 dòng gộp vì FE phải đi xin tỷ lệ. Nay backend trả sẵn ⇒ vẫn đủ 3 dòng."""
    from app.db import SessionLocal
    from app.repositories.employee_repo import EmployeeRepository
    from app.repositories.rbac_repo import DepartmentRepository, RoleRepository
    from app.repositories.user_repo import UserRepository
    from app.security import create_access_token, hash_password

    admin = _admin_token(client)
    eid = _make_emp(client, admin, name="NV Xem phiếu", status="active")
    client.post(f"/api/luong/salaries/{eid}", json={"effective_from": "2026-01-01",
                "luong_vi_tri": 10_000_000}, headers=_h(admin))
    client.post("/api/luong/generate", json={"year": 2026, "month": 6}, headers=_h(admin))

    db = SessionLocal()
    try:
        users = UserRepository(db)
        kd = DepartmentRepository(db).get_by_name("Kinh doanh")
        role = RoleRepository(db).get_by_name_and_department("NV Sales", kd.id)
        u = users.create(username="nv-xem-phieu", name="NV", password_hash=hash_password("x"))
        users.set_assignment(u, department_id=kd.id, role_id=role.id, is_active=True)
        emps = EmployeeRepository(db)
        emps.update(emps.get_by_id(eid), user_id=u.id)
        tok = create_access_token(str(u.id))
    finally:
        db.close()

    # Không có quyền cấu hình lương...
    assert client.get("/api/luong/params", headers=_h(tok)).status_code == 403
    # ...nhưng phiếu lương của chính mình vẫn đủ 3 dòng bảo hiểm.
    slip = client.get("/api/luong/payslip/me", headers=_h(tok))
    assert slip.status_code == 200, slip.text
    rows = slip.json()["line"]["insurance_lines"]
    assert [r["label"].split()[0] for r in rows] == ["BHXH", "BHYT", "BHTN"]
    assert sum(r["amount"] for r in rows) == slip.json()["line"]["bhxh"]


def test_tang_ca_vuot_nua_dem_khong_mat_cong(client):
    """Bug chủ phát hiện 23/07/2026: ca chiều 14:00–22:00 tăng ca tới 03:00 hôm sau thì lượt RA bị
    ném sang NGÀY DƯƠNG LỊCH MỚI ⇒ ngày cũ treo ⇒ 0 công + 0 tăng ca (mất trắng 13h làm việc).
    Sau khi sửa + có phiếu tăng ca duyệt: ĐỦ 1 công + 300' tăng ca."""
    from datetime import datetime as _dt, timezone as _tz
    token = _admin_token(client)
    # Ngày công 15/06: vào 14:00 VN (07:00 UTC 15/06) → ra 03:00 VN 16/06 (20:00 UTC 15/06).
    eid = _setup_shift_and_punches(
        client, token, name="NV TC qua đêm", start_min=840, end_min=1320, overnight=False,
        in_utc=_dt(2026, 6, 15, 7, 0, tzinfo=_tz.utc),
        out_utc=_dt(2026, 6, 15, 20, 0, tzinfo=_tz.utc))
    _mk_ot(client, token, eid, work_date="2026-06-15", frm=1320, to=1620)  # 22:00 → 03:00 hôm sau
    line = _gen_line(client, token, eid)
    assert line["actual_cong"] == 1.0     # KHÔNG còn mất công vì lượt RA rơi sang ngày mới
    assert line["ot_minutes"] == 300      # 22:00 → 03:00 = 5h tăng ca


def test_ca_dem_tang_ca_qua_gio_tan_ca(client):
    """Ca đêm 22:00–06:00 làm thêm tới 08:00: trước đây ra sau 06:00 là mất trắng công.
    Sau khi sửa + có phiếu: 1 công + 120' tăng ca."""
    from datetime import datetime as _dt, timezone as _tz
    token = _admin_token(client)
    # Ngày công 15/06: vào 22:00 VN (15:00 UTC 15/06) → ra 08:00 VN 16/06 (01:00 UTC 16/06).
    eid = _setup_shift_and_punches(
        client, token, name="NV ca đêm TC", start_min=1320, end_min=360, overnight=True,
        in_utc=_dt(2026, 6, 15, 15, 0, tzinfo=_tz.utc),
        out_utc=_dt(2026, 6, 16, 1, 0, tzinfo=_tz.utc))
    # Ca đêm hết lúc 06:00 hôm sau = phút 1800 trên trục ngày công; tăng ca 06:00 → 08:00.
    _mk_ot(client, token, eid, work_date="2026-06-15", frm=1800, to=1920)
    line = _gen_line(client, token, eid)
    assert line["actual_cong"] == 1.0
    assert line["ot_minutes"] == 120      # 06:00 → 08:00


def test_tang_ca_khong_phieu_thi_khong_ra_tien_nhung_giu_du_cong(client):
    """Chốt của chủ 23/07/2026: KHÔNG có phiếu tăng ca ⇒ phần vượt ca KHÔNG ra tiền, NHƯNG công
    ca chính vẫn ĐỦ (không ai mất công gốc chỉ vì quên xin phiếu)."""
    from datetime import datetime as _dt, timezone as _tz
    token = _admin_token(client)
    eid = _setup_shift_and_punches(
        client, token, name="NV TC không phiếu", start_min=840, end_min=1320, overnight=False,
        in_utc=_dt(2026, 6, 15, 7, 0, tzinfo=_tz.utc),
        out_utc=_dt(2026, 6, 15, 20, 0, tzinfo=_tz.utc))
    line = _gen_line(client, token, eid)
    assert line["actual_cong"] == 1.0     # công ca chính GIỮ NGUYÊN
    assert line["ot_minutes"] == 0        # không phiếu → không tiền tăng ca


def test_ve_som_hon_phieu_tra_theo_thuc_te(client):
    """Phiếu là TRẦN, không phải mức trả: duyệt tới 03:00 nhưng 00:00 đã về ⇒ chỉ trả 120'."""
    from datetime import datetime as _dt, timezone as _tz
    token = _admin_token(client)
    # vào 14:00 VN 15/06 → ra 00:00 VN 16/06 (17:00 UTC 15/06) = tăng ca 2h thật.
    eid = _setup_shift_and_punches(
        client, token, name="NV về sớm hơn phiếu", start_min=840, end_min=1320, overnight=False,
        in_utc=_dt(2026, 6, 15, 7, 0, tzinfo=_tz.utc),
        out_utc=_dt(2026, 6, 15, 17, 0, tzinfo=_tz.utc))
    _mk_ot(client, token, eid, work_date="2026-06-15", frm=1320, to=1620)  # duyệt tới 03:00
    line = _gen_line(client, token, eid)
    assert line["actual_cong"] == 1.0
    assert line["ot_minutes"] == 120      # trả theo giờ THỰC (22:00→00:00), không phải 300'


def test_lam_qua_phieu_thi_chan_tran(client):
    """Làm quá phiếu: phần vượt KHÔNG được tính (muốn tính phải xin phiếu bổ sung)."""
    from datetime import datetime as _dt, timezone as _tz
    token = _admin_token(client)
    # vào 14:00 → ra 03:00 hôm sau (thực 5h TC) nhưng phiếu chỉ duyệt tới 00:00 (2h).
    eid = _setup_shift_and_punches(
        client, token, name="NV làm quá phiếu", start_min=840, end_min=1320, overnight=False,
        in_utc=_dt(2026, 6, 15, 7, 0, tzinfo=_tz.utc),
        out_utc=_dt(2026, 6, 15, 20, 0, tzinfo=_tz.utc))
    _mk_ot(client, token, eid, work_date="2026-06-15", frm=1320, to=1440)  # chỉ tới 00:00
    line = _gen_line(client, token, eid)
    assert line["actual_cong"] == 1.0
    assert line["ot_minutes"] == 120      # kẹp trần theo phiếu, không phải 300'


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
    eid = _make_emp(client, token, name="Thợ In A")

    # khai lương = lương vị trí + trách nhiệm của NV (mức nền, gõ tay từng ô)
    s = client.post(f"/api/luong/salaries/{eid}", json={
        "effective_from": "2026-01-01", "luong_vi_tri": 18_000_000,
        "luong_trach_nhiem": 4_000_000, "allowance": 300_000,
    }, headers=_h(token))
    assert s.status_code == 201

    prev = client.get(f"/api/luong/salaries/{eid}/preview", headers=_h(token)).json()
    assert prev["monthly"] == 22_000_000 and prev["source"] == "employee"
    assert prev["insurance_base"] == 18_000_000   # mức đóng BH = lương vị trí

    hist = client.get(f"/api/luong/salaries/{eid}", headers=_h(token)).json()
    assert hist["employee_name"] == "Thợ In A" and len(hist["items"]) == 1

    # điều chỉnh hiệu lực sau → preview lấy mức mới
    client.post(f"/api/luong/salaries/{eid}", json={
        "effective_from": "2026-07-01", "luong_vi_tri": 24_000_000,
    }, headers=_h(token))
    prev2 = client.get(f"/api/luong/salaries/{eid}/preview", headers=_h(token)).json()
    assert prev2["monthly"] == 24_000_000 and prev2["source"] == "employee"

    hist2 = client.get(f"/api/luong/salaries/{eid}", headers=_h(token)).json()["items"]
    assert len(hist2) == 2
    assert hist2[0]["effective_to"] is None
    assert hist2[1]["effective_to"] == "2026-06-30"

    # NHẬT KÝ điều chỉnh: mỗi lần lưu (kể cả CÙNG ngày hiệu lực) = MỘT bản ghi mới — giữ đủ
    # dấu vết "ai · lúc nào". "Hiện hành" = bản lưu SAU (id lớn hơn) → preview + đầu danh sách
    # lấy 25tr; danh sách nay có 3 dòng (01-01, 07-01@24tr, 07-01@25tr).
    client.post(f"/api/luong/salaries/{eid}", json={
        "effective_from": "2026-07-01", "luong_vi_tri": 25_000_000,
    }, headers=_h(token))
    hist3 = client.get(f"/api/luong/salaries/{eid}", headers=_h(token)).json()["items"]
    assert len(hist3) == 3 and hist3[0]["luong_vi_tri"] == 25_000_000
    assert hist3[0]["is_current"] is True
    assert hist3[0]["actor_name"]        # có tên người điều chỉnh (nhật ký "ai sửa")
    prev3 = client.get(f"/api/luong/salaries/{eid}/preview", headers=_h(token)).json()
    assert prev3["monthly"] == 25_000_000


# --- tạm ứng ----------------------------------------------------------------


def test_advance_workflow(client):
    token = _admin_token(client)
    _tat_tran_tam_ung(client, token)
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
    _tat_tran_tam_ung(client, token)
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
    _tat_tran_tam_ung(client, token)   # tạm ứng 2tr/10tr = 20% > trần mặc định
    eid = _make_emp(client, token, name="NV Bảng", status="active")
    client.post(f"/api/luong/salaries/{eid}", json={
        "effective_from": "2026-01-01", "luong_vi_tri": 10_000_000,
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
        v = svc._compute(employee=emp, salary=_sal(luong_vi_tri=20_000_000), params=params, actual_cong=26, standard_cong=26,
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
        base = svc._compute(employee=emp, salary=_sal(luong_vi_tri=30_000_000), params=params, actual_cong=26, standard_cong=26,
                            on=date(2026, 6, 1))
        withb = svc._compute(employee=emp, salary=_sal(luong_vi_tri=30_000_000), params=params, actual_cong=26, standard_cong=26,
                             thuong_5s=1_000_000, thuong_doanh_so=2_000_000, dieu_chinh_luong=-500_000,
                             on=date(2026, 6, 1))
        assert withb["thuong_5s"] == 1_000_000 and withb["thuong_doanh_so"] == 2_000_000
        assert withb["dieu_chinh_luong"] == -500_000
        assert withb["gross"] == base["gross"] + 2_500_000     # 1tr + 2tr − 0.5tr
        assert withb["pit"] > base["pit"]                      # thưởng chịu thuế → PIT tăng
    finally:
        db.close()


def test_cong_doan_auto(client):
    """Đoàn phí công đoàn = insurance_base × cong_doan_rate — CHỈ đoàn viên (union_member); thử việc = 0;
    không phải đoàn viên = 0 (chủ 2026-07-21: opt-in từng người)."""
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
        # Đoàn viên → có trừ đoàn phí.
        v = svc._compute(employee=emp, salary=_sal(luong_vi_tri=10_000_000, union_member=True),
                         params=params, actual_cong=26, standard_cong=26, on=date(2026, 6, 1))
        assert v["cong_doan"] == round(v["insurance_base"] * 0.005) and v["cong_doan"] > 0
        # KHÔNG phải đoàn viên → 0 dù rate > 0.
        v_no = svc._compute(employee=emp, salary=_sal(luong_vi_tri=10_000_000, union_member=False),
                            params=params, actual_cong=26, standard_cong=26, on=date(2026, 6, 1))
        assert v_no["cong_doan"] == 0
        # Thử việc (dù là đoàn viên) → 0.
        emp_tv = SimpleNamespace(status="probation", hire_date=date(2026, 5, 1), gender="male",
                                 payroll_group="cd_grp", pay_grade_key=None, dependents_count=0)
        v_tv = svc._compute(employee=emp_tv, salary=_sal(luong_vi_tri=10_000_000, union_member=True),
                            params=params, actual_cong=26, standard_cong=26, on=date(2026, 6, 1))
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
        v = svc._compute(employee=emp, salary=_sal(luong_vi_tri=20_000_000), params=params, actual_cong=26, standard_cong=26,
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
    # union_member=True: đoàn viên → có trừ đoàn phí công đoàn (mặc định false thì công đoàn = 0).
    client.post(f"/api/luong/salaries/{eid}", json={"effective_from": "2026-01-01",
                "luong_vi_tri": 5_000_000, "union_member": True}, headers=_h(token))
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
    _tat_tran_tam_ung(client, token)   # kịch bản CẦN ứng vượt lương → phải tắt trần mới dựng được
    eid = _make_emp(client, token, name="NV Sàn", status="active")
    client.post(f"/api/luong/salaries/{eid}", json={"effective_from": "2026-01-01",
                "luong_vi_tri": 10_000_000}, headers=_h(token))
    aid = client.post("/api/luong/advances", json={"employee_id": eid, "period_year": 2027,
        "period_month": 3, "advance_date": "2027-03-05", "amount": 5_000_000},
        headers=_h(token)).json()["id"]
    client.post(f"/api/luong/advances/{aid}/approve", json={}, headers=_h(token))
    gen = client.post("/api/luong/generate", json={"year": 2027, "month": 3}, headers=_h(token)).json()
    line = next(l for l in gen["lines"] if l["employee_id"] == eid)
    assert line["net_pay"] == 0   # 0 công + tạm ứng 5tr → sàn 0, không âm


def test_standard_cong_dong_theo_lich(client):
    """Công chuẩn (mẫu số chia lương công) ĐỘNG theo Lịch từng tháng (redesign-hcns Đ3/N4) — KHÔNG
    còn cố định 26: đổi tuần làm việc thì mẫu số của kỳ đổi theo, luôn khớp số ngày làm việc của lịch.
    Nhờ vậy làm ĐỦ tháng = nguyên lương kể cả tháng ngắn (NĐ145/2020 Đ55)."""
    token = _admin_token(client)
    base = client.get("/api/calendar/month", params={"year": 2027, "month": 9},
                      headers=_h(token)).json()["working_days"]
    assert client.post("/api/luong/generate", json={"year": 2027, "month": 9},
                       headers=_h(token)).status_code == 200
    with SessionLocal() as db:
        assert float(PayrollRepository(db).get_period_by_ym(2027, 9).standard_cong) == base

    # Tắt Thứ 7 → công chuẩn tháng GIẢM; mẫu số kỳ lương đi theo LỊCH (không phải tham số chung).
    assert client.put("/api/calendar/config", json={"works_sat": False},
                      headers=_h(token)).status_code == 200
    after = client.get("/api/calendar/month", params={"year": 2027, "month": 9},
                       headers=_h(token)).json()["working_days"]
    assert after < base
    assert client.post("/api/luong/generate", json={"year": 2027, "month": 9},
                       headers=_h(token)).status_code == 200
    with SessionLocal() as db:
        assert float(PayrollRepository(db).get_period_by_ym(2027, 9).standard_cong) == after


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
        over = svc._compute(employee=emp, salary=_sal(luong_vi_tri=13_000_000), params=params, actual_cong=27,
                            standard_cong=26, on=date(2026, 7, 1))
        assert over["luong_cong"] == 13_000_000
        # 13 công / 26 → nửa lương
        half = svc._compute(employee=emp, salary=_sal(luong_vi_tri=13_000_000), params=params, actual_cong=13,
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
        v = svc._compute(employee=emp, salary=_sal(luong_vi_tri=26_000_000), params=params, actual_cong=26, standard_cong=26,
                         holiday_cong=1, on=date(2026, 6, 1))
        assert v["ot_pay"] == round(daily * (3 - 1))   # 2.000.000 premium lễ
        # OT: 60' ngày lễ ×3 + 60' ngày nghỉ tuần ×2 (tổng ot_minutes = 120, không có OT thường).
        v2 = svc._compute(employee=emp, salary=_sal(luong_vi_tri=26_000_000), params=params, actual_cong=26, standard_cong=26,
                          ot_minutes=120, ot_holiday_minutes=60, ot_restday_minutes=60,
                          on=date(2026, 6, 1))
        hourly = daily / 8   # 125.000
        assert v2["ot_pay"] == round(hourly * (1 * 3 + 1 * 2))   # 125k × 5 = 625.000
    finally:
        db.close()
