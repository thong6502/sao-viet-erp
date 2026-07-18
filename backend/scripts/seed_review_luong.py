"""SEED dữ liệu REVIEW LƯƠNG — kỳ 7/2026 (chỉ dev.db).

Đổ một bộ dữ liệu lương "đủ mọi trường hợp" để chủ (non-tech) mở app soi UI/UX phân hệ Lương
từ tài khoản nhân viên tới HCNS: chính thức/thử việc, tổ khoán, tăng ca + ca đêm, thiếu công
prorate, tạm ứng, thưởng/phạt chi tiết, phạt chạm trần 30%, lương dept_row (bảng lương của tổ).

IDEMPOTENT: get-before-create toàn bộ (phòng/NV/lương/tạm ứng/khoán/period line/tài khoản).
Chạy lại KHÔNG tạo trùng và KHÔNG ghi đè các ô chỉnh tay của kỳ (generate giữ ô tay, update_line
gán giá trị tuyệt đối). CHỈ tác động dev.db — KHÔNG sửa code/schema, KHÔNG động prod.

Chạy:  cd backend && PYTHONIOENCODING=utf-8 python scripts/seed_review_luong.py
"""
from __future__ import annotations

import sys
from datetime import date, datetime, timezone

sys.path.insert(0, ".")

from sqlalchemy import select  # noqa: E402

from app.db import SessionLocal  # noqa: E402
from app.security import hash_password  # noqa: E402

from app.models.attendance import APERIOD_LOCKED, AttendancePeriod  # noqa: E402
from app.models.department import Department  # noqa: E402
from app.models.employee import STATUS_ACTIVE, STATUS_PROBATION, Employee  # noqa: E402
from app.models.payroll import AMOUNT_MANUAL, DepartmentSalaryRow, EmployeeSalary, PayrollLine  # noqa: E402
from app.models.production import ProductionOrder  # noqa: E402
from app.models.production_output import ProductionOutput  # noqa: E402
from app.models.role import Role  # noqa: E402
from app.models.user import User  # noqa: E402

from app.repositories.attendance_repo import AttendanceRepository  # noqa: E402
from app.repositories.audit_repo import AuditLogRepository  # noqa: E402
from app.repositories.employee_repo import EmployeeRepository  # noqa: E402
from app.repositories.payroll_repo import PayrollRepository  # noqa: E402
from app.repositories.piece_work_repo import PieceWorkRepository  # noqa: E402
from app.repositories.production_output_repo import ProductionOutputRepository  # noqa: E402
from app.repositories.rbac_repo import DepartmentRepository, RoleRepository  # noqa: E402
from app.repositories.user_repo import UserRepository  # noqa: E402

from app.services.attendance_service import AttendanceService  # noqa: E402
from app.services.payroll_service import PayrollService  # noqa: E402
from app.services.piece_work_service import PieceWorkService  # noqa: E402

YEAR, MONTH = 2026, 7
EFF = date(YEAR, MONTH, 1)


def _money(x) -> str:
    return f"{float(x or 0):,.0f}".replace(",", ".")


def _now():
    return datetime.now(timezone.utc)


def main() -> None:
    db = SessionLocal()
    stats = {k: [0, 0] for k in (  # [tạo mới, bỏ qua]
        "dept", "salary_row", "employee", "salary", "period_line", "advance",
        "khoan", "user", "role",
    )}
    warnings: list[str] = []

    # --- DI (dựng chuỗi như deps.py; audit=None cho đường seed) --------------
    payroll_repo = PayrollRepository(db)
    employee_repo = EmployeeRepository(db)
    attendance_repo = AttendanceRepository(db)
    piece_repo = PieceWorkRepository(db)
    output_repo = ProductionOutputRepository(db)
    dept_repo = DepartmentRepository(db)
    role_repo = RoleRepository(db)
    user_repo = UserRepository(db)
    _audit_repo = AuditLogRepository(db)  # có sẵn nếu cần; đường seed dùng audit=None

    attendance_service = AttendanceService(attendance_repo, employee_repo, None, payroll=payroll_repo)
    piece_service = PieceWorkService(piece_repo, outputs=output_repo)
    payroll_service = PayrollService(
        payroll_repo, employee_repo, attendance_service,
        audit=None, piece=piece_service, departments=dept_repo,
    )

    admin = user_repo.get_by_username("admin")
    if admin is None:
        raise SystemExit("KHÔNG tìm thấy user 'admin' — dev.db chưa seed? Dừng.")

    # === Tham số lương: đoàn phí công đoàn 0,5% ==============================
    payroll_service.update_params(cong_doan_rate=0.005)

    # === Phòng ban (get-or-create theo tên) =================================
    def get_or_create_dept(name, *, salary_mechanism="cung", has_piece_work=False):
        d = dept_repo.get_by_name(name)
        if d is not None:
            # đồng bộ cờ khoán / cơ chế nếu phòng đã tồn tại nhưng khác kỳ vọng
            changed = False
            if has_piece_work and not d.has_piece_work:
                d.has_piece_work = True
                changed = True
            if salary_mechanism != "cung" and d.salary_mechanism != salary_mechanism:
                d.salary_mechanism = salary_mechanism
                changed = True
            if changed:
                db.commit()
                db.refresh(d)
            stats["dept"][1] += 1
            return d
        d = dept_repo.create(name=name, salary_mechanism=salary_mechanism, has_piece_work=has_piece_work)
        stats["dept"][0] += 1
        return d

    dept_kd = get_or_create_dept("Kinh doanh")
    dept_in = get_or_create_dept("Tổ In", has_piece_work=True)
    dept_dan = get_or_create_dept("Tổ Dán", salary_mechanism="tham_nien_gioi_tinh")
    dept_hcns = dept_repo.get_by_name("Hành chính nhân sự")
    dept_bgd = dept_repo.get_by_name("Ban giám đốc")
    if dept_hcns is None or dept_bgd is None:
        raise SystemExit("Thiếu phòng 'Hành chính nhân sự' / 'Ban giám đốc' seed sẵn — dừng.")

    # === Bảng lương của Tổ Dán (get-or-create theo (dept,label)) ============
    def get_or_create_salary_row(dept_id, label, **fields):
        existing = db.execute(
            select(DepartmentSalaryRow).where(
                DepartmentSalaryRow.department_id == dept_id,
                DepartmentSalaryRow.label == label,
            )
        ).scalars().first()
        if existing is not None:
            stats["salary_row"][1] += 1
            return existing
        order = dept_repo.next_salary_row_order(dept_id)
        row = dept_repo.create_salary_row(
            department_id=dept_id, label=label, apply_by="tham_nien_gioi_tinh",
            phu_cap=0, chuyen_can=0, sort_order=order, **fields,
        )
        stats["salary_row"][0] += 1
        return row

    row_nam_lt1 = get_or_create_salary_row(
        dept_dan.id, "Nam < 1 năm", gender="male", seniority_band="lt1",
        luong_vi_tri=6_000_000, luong_trach_nhiem=1_000_000)
    row_nam_1_5 = get_or_create_salary_row(
        dept_dan.id, "Nam 1–5 năm", gender="male", seniority_band="y1_5",
        luong_vi_tri=7_000_000, luong_trach_nhiem=1_500_000)
    row_nu_lt1 = get_or_create_salary_row(
        dept_dan.id, "Nữ < 1 năm", gender="female", seniority_band="lt1",
        luong_vi_tri=5_500_000, luong_trach_nhiem=800_000)
    row_nu_1_5 = get_or_create_salary_row(
        dept_dan.id, "Nữ 1–5 năm", gender="female", seniority_band="y1_5",
        luong_vi_tri=6_500_000, luong_trach_nhiem=1_200_000)
    _ = (row_nam_lt1, row_nam_1_5, row_nu_lt1)  # giữ để soi bảng lương tổ đủ 4 dòng

    # === 9 nhân viên test (get-or-create theo full_name) ====================
    def get_or_create_employee(full_name, **fields):
        e = db.execute(select(Employee).where(Employee.full_name == full_name)).scalars().first()
        if e is not None:
            stats["employee"][1] += 1
            return e
        e = employee_repo.create(full_name=full_name, **fields)
        stats["employee"][0] += 1
        return e

    chinh = get_or_create_employee(
        "Lê Văn Chính", department_id=dept_kd.id, status=STATUS_ACTIVE, gender="male",
        hire_date=date(2020, 1, 15), dependents_count=1, bank_account="0011", bank_name="Vietcombank")
    thu = get_or_create_employee(
        "Phạm Thị Thử", department_id=dept_kd.id, status=STATUS_PROBATION, gender="female",
        hire_date=date(2026, 7, 1), dependents_count=0)
    khoan = get_or_create_employee(
        "Trần Văn Khoán", department_id=dept_in.id, status=STATUS_ACTIVE, gender="male",
        hire_date=date(2019, 3, 1), dependents_count=2)
    tangca = get_or_create_employee(
        "Nguyễn Văn Tăng Ca", department_id=dept_kd.id, status=STATUS_ACTIVE, gender="male",
        hire_date=date(2021, 6, 1), dependents_count=0)
    thieucong = get_or_create_employee(
        "Hoàng Thị Thiếu Công", department_id=dept_kd.id, status=STATUS_ACTIVE, gender="female",
        hire_date=date(2022, 2, 1), dependents_count=1)
    phat = get_or_create_employee(
        "Đỗ Văn Phạt", department_id=dept_kd.id, status=STATUS_ACTIVE, gender="male",
        hire_date=date(2018, 5, 1), dependents_count=0)
    dan = get_or_create_employee(
        "Vũ Thị Dán", department_id=dept_dan.id, status=STATUS_ACTIVE, gender="female",
        hire_date=date(2023, 1, 1), dependents_count=1)
    tamung = get_or_create_employee(
        "Bùi Văn Tạm Ứng", department_id=dept_kd.id, status=STATUS_ACTIVE, gender="male",
        hire_date=date(2020, 9, 1), dependents_count=0)
    quanly = get_or_create_employee(
        "Mai Thị Quản Lý", department_id=dept_bgd.id, status=STATUS_ACTIVE, gender="female",
        hire_date=date(2015, 1, 1), dependents_count=2)

    # === Khai lương (set_salary, effective_from=1/7/2026) ===================
    def has_salary(emp_id) -> bool:
        return any(s.effective_from == EFF for s in payroll_repo.list_salaries(emp_id))

    def set_salary_manual(emp, base, insurance_base, allowance, chuyen_can):
        if has_salary(emp.id):
            stats["salary"][1] += 1
            return
        payroll_service.set_salary(
            employee_id=emp.id, actor=admin, effective_from=EFF, amount_mode=AMOUNT_MANUAL,
            base_amount=base, insurance_base=insurance_base, allowance=allowance, chuyen_can=chuyen_can)
        stats["salary"][0] += 1

    set_salary_manual(chinh, 12_000_000, 12_000_000, 1_000_000, 500_000)
    set_salary_manual(thu, 10_000_000, 0, 0, 300_000)
    set_salary_manual(khoan, 8_000_000, 8_000_000, 500_000, 400_000)
    set_salary_manual(tangca, 10_000_000, 10_000_000, 0, 300_000)
    set_salary_manual(thieucong, 9_000_000, 9_000_000, 0, 500_000)
    set_salary_manual(phat, 11_000_000, 11_000_000, 0, 300_000)
    set_salary_manual(tamung, 10_000_000, 10_000_000, 0, 300_000)
    set_salary_manual(quanly, 40_000_000, 40_000_000, 0, 500_000)
    # Vũ Thị Dán: dept_row → trỏ dòng "Nữ 1–5 năm" của Tổ Dán (đọc sống vị trí+trách nhiệm).
    if has_salary(dan.id):
        stats["salary"][1] += 1
    else:
        payroll_service.set_salary(
            employee_id=dan.id, actor=admin, effective_from=EFF,
            source_salary_row_id=row_nu_1_5.id, insurance_base=0,
            allowance=800_000, chuyen_can=400_000)
        stats["salary"][0] += 1

    # === Snapshot chấm công 7/2026 (kỳ LOCKED để Lương đọc snapshot) ========
    aperiod = attendance_repo.get_period_by_ym(YEAR, MONTH)
    if aperiod is None:
        aperiod = attendance_repo.create_period(
            year=YEAR, month=MONTH, status=APERIOD_LOCKED,
            locked_at=_now(), locked_by=admin.id, created_by=admin.id)
    elif aperiod.status != APERIOD_LOCKED:
        attendance_repo.update_period(aperiod, status=APERIOD_LOCKED, locked_at=_now(), locked_by=admin.id)

    existing_line_emp = {ln.employee_id for ln in attendance_repo.list_period_lines(aperiod.id)}

    # Dòng công của 9 NV test (mặc định 26 công; riêng khoán/tăng-ca/thiếu-công).
    line_metrics: dict[int, dict] = {
        chinh.id: dict(total_cong=26, total_days=26),
        thu.id: dict(total_cong=26, total_days=26),
        khoan.id: dict(total_cong=26, total_days=26, ot_minutes=300),
        tangca.id: dict(total_cong=26, total_days=26, ot_minutes=600, night_days=4),
        thieucong.id: dict(total_cong=18, total_days=18),
        phat.id: dict(total_cong=26, total_days=26),
        dan.id: dict(total_cong=26, total_days=26),
        tamung.id: dict(total_cong=26, total_days=26),
        quanly.id: dict(total_cong=26, total_days=26),
    }
    # TOP-UP: mọi NV active khác chưa có period_line → 26 công (để bảng lương không trống).
    for e in employee_repo.list_scoped_all(scope="all", actor=admin):
        if e.status == STATUS_ACTIVE and e.id not in line_metrics:
            line_metrics.setdefault(e.id, dict(total_cong=26, total_days=26))

    for emp_id, m in line_metrics.items():
        if emp_id in existing_line_emp:
            stats["period_line"][1] += 1
            continue
        attendance_repo.create_period_line(period_id=aperiod.id, employee_id=emp_id, **m)
        stats["period_line"][0] += 1

    # === Tiền khoán cho Trần Văn Khoán (LSX tối thiểu + phiếu sản lượng) =====
    order = db.execute(
        select(ProductionOrder).where(ProductionOrder.code == "LSX-SEED-LUONG-01")
    ).scalars().first()
    if order is None:
        order = ProductionOrder(code="LSX-SEED-LUONG-01", product_name="Khoán demo (soi lương)",
                                status="open", created_by_user_id=admin.id)
        db.add(order)
        db.commit()
        db.refresh(order)
    existing_out = [o for o in output_repo.list_nguoi_by_period(YEAR, MONTH)
                    if o.employee_id == khoan.id and o.cong_doan == "CD-KHOAN-DEMO"]
    if existing_out:
        stats["khoan"][1] += 1
    else:
        output_repo.create(
            production_order_id=order.id, cong_doan="CD-KHOAN-DEMO", ghi_theo="nguoi",
            year=YEAR, month=MONTH, group_name="Tổ In", employee_id=khoan.id,
            work_name="Gia công khoán demo", unit="khac", unit_price=100_000, quantity=30,
            tinh_khoan=True, recorded_by=admin.id)
        stats["khoan"][0] += 1

    # === Tạm ứng cho Bùi Văn Tạm Ứng (tạo + duyệt) ==========================
    advs = [a for a in payroll_repo.list_advances(year=YEAR, month=MONTH) if a.employee_id == tamung.id]
    if not advs:
        adv = payroll_service.create_advance(
            employee_id=tamung.id, actor=admin, period_year=YEAR, period_month=MONTH,
            advance_date=date(YEAR, MONTH, 10), amount=3_000_000, reason="Tạm ứng demo")
        payroll_service.decide_advance(advance_id=adv.id, actor=admin, approve=True)
        stats["advance"][0] += 1
    else:
        adv = advs[0]
        if adv.status == "pending":
            payroll_service.decide_advance(advance_id=adv.id, actor=admin, approve=True)
        stats["advance"][1] += 1

    # === Tính bảng lương 7/2026 =============================================
    period = payroll_repo.get_period_by_ym(YEAR, MONTH)
    if period is not None and period.status == "paid":
        payroll_service.unpay_period(year=YEAR, month=MONTH, actor=admin)
        payroll_service.reopen_period(year=YEAR, month=MONTH, actor=admin)
        warnings.append("Kỳ lương 7/2026 đang 'đã chi' → đã mở lại về nháp để tính lại.")
    elif period is not None and period.status == "locked":
        payroll_service.reopen_period(year=YEAR, month=MONTH, actor=admin)
        warnings.append("Kỳ lương 7/2026 đang 'đã chốt' → đã mở lại về nháp để tính lại.")

    period = payroll_service.generate(year=YEAR, month=MONTH, actor=admin, scope="all")

    # === Ô tay chi tiết (thưởng/phạt) — gán sau generate ====================
    def edit_line(emp, **fields):
        ln = payroll_repo.get_line_by_pe(period.id, emp.id)
        if ln is None:
            warnings.append(f"Không thấy dòng lương của {emp.full_name} để gán ô tay.")
            return
        payroll_service.update_line(line_id=ln.id, actor=admin, **fields)

    edit_line(chinh, thuong_5s=300_000, thuong_doanh_so=2_000_000,
              thuong_thanh_tich=1_000_000, other_bonus=500_000)
    edit_line(tangca, di_tre=150_000, dt_vuot_troi=100_000,
              phat_bien_ban=200_000, phat_5s_dong_phuc=50_000)
    edit_line(dan, phep_nam=500_000, tra_dong_phuc=300_000)
    edit_line(phat, vi_pham=50_000_000)  # 50tr → chạm trần 30% (Đ102)

    # === Tài khoản RBAC (role HCNS + 2 user demo) ===========================
    role = role_repo.get_by_name_and_department("NV Xem lương (test)", dept_hcns.id)
    if role is None:
        role = role_repo.create(name="NV Xem lương (test)", department_id=dept_hcns.id)
        stats["role"][0] += 1
    else:
        stats["role"][1] += 1
    role_repo.set_permission(role_id=role.id, module_key="luong", scope="own", can_read=True)
    role_repo.set_permission(role_id=role.id, module_key="dashboard", scope="own", can_read=True)

    def get_or_create_user(username, name, link_emp):
        u = user_repo.get_by_username(username)
        if u is None:
            u = user_repo.create(username=username, name=name, password_hash=hash_password("password123"))
            stats["user"][0] += 1
        else:
            stats["user"][1] += 1
        user_repo.set_assignment(u, department_id=dept_hcns.id, role_id=role.id, is_active=True)
        if link_emp.user_id != u.id:
            employee_repo.update(link_emp, user_id=u.id)
        return u

    get_or_create_user("nhanvien", "Nhân viên demo", chinh)
    get_or_create_user("thuviec", "Nhân viên thử việc demo", thu)

    db.commit()

    # === Verify: query lại payroll_lines kỳ 7/2026 cho 9 NV test ============
    test_ids = [chinh.id, thu.id, khoan.id, tangca.id, thieucong.id, phat.id, dan.id, tamung.id, quanly.id]
    lines = {ln.employee_id: ln for ln in payroll_repo.list_lines(period.id)}

    print("\n" + "=" * 118)
    print(f"SEED REVIEW LƯƠNG — kỳ {MONTH}/{YEAR} (dev.db) — trạng thái kỳ: {period.status}")
    print("=" * 118)
    print("Thống kê (tạo mới / bỏ qua):")
    label = {
        "dept": "Phòng ban", "salary_row": "Dòng lương tổ", "employee": "Nhân viên",
        "salary": "Khai lương", "period_line": "Dòng chấm công", "advance": "Tạm ứng",
        "khoan": "Phiếu khoán", "user": "Tài khoản", "role": "Vai trò",
    }
    for k, (new, skip) in stats.items():
        print(f"  · {label[k]:<16}: +{new}  (bỏ qua {skip})")

    hdr = ("Nhân viên", "TV", "Công", "Lương công", "Khoán", "Tăng ca", "Ca đêm",
           "BHXH", "C.đoàn", "TNCN", "Tạm ứng", "Thực nhận")
    print("\n" + "-" * 118)
    print(f"{hdr[0]:<20}{hdr[1]:>4}{hdr[2]:>6}{hdr[3]:>13}{hdr[4]:>12}{hdr[5]:>10}{hdr[6]:>9}"
          f"{hdr[7]:>11}{hdr[8]:>9}{hdr[9]:>10}{hdr[10]:>11}{hdr[11]:>14}")
    print("-" * 118)
    for emp_id in test_ids:
        ln = lines.get(emp_id)
        emp = employee_repo.get_by_id(emp_id)
        if ln is None:
            print(f"{emp.full_name:<20}  (KHÔNG có dòng lương)")
            continue
        print(f"{emp.full_name:<20}"
              f"{'TV' if ln.is_probation else '-':>4}"
              f"{float(ln.actual_cong):>6.0f}"
              f"{_money(ln.luong_cong):>13}"
              f"{_money(ln.khoan):>12}"
              f"{_money(ln.ot_pay):>10}"
              f"{_money(ln.night_pay):>9}"
              f"{_money(ln.bhxh):>11}"
              f"{_money(ln.cong_doan):>9}"
              f"{_money(ln.pit):>10}"
              f"{_money(ln.advance_total):>11}"
              f"{_money(ln.net_pay):>14}")
    print("-" * 118)
    # Nhắc riêng số vi_pham RAW của Đỗ Văn Phạt (chạm trần) để chủ đối chiếu.
    ln_phat = lines.get(phat.id)
    if ln_phat is not None:
        print(f"Đỗ Văn Phạt — vi_pham lưu RAW: {_money(ln_phat.vi_pham)}đ · gross sau trừ: "
              f"{_money(ln_phat.gross)}đ · thực nhận: {_money(ln_phat.net_pay)}đ")
    if warnings:
        print("\nCẢNH BÁO:")
        for w in warnings:
            print("  ! " + w)
    print("\nĐăng nhập: admin/admin123 (HCNS) · nhanvien/password123 · thuviec/password123")
    print("=" * 118 + "\n")

    db.close()


if __name__ == "__main__":
    main()
