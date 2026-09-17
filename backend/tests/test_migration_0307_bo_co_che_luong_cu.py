"""Migration 0307: dọn cơ chế lương cũ — bảng `salary_rate_rules`, cơ chế lương/% thử việc theo
phòng, nhóm lương của hồ sơ, `amount_mode` + `source_salary_row_id` của mốc lương.

Chạy trên DB còn bảng/cột cũ (mô phỏng DB dev đang sống) — `create_all` không tạo lại thứ đã xoá
khỏi model nên DB trắng chứng minh được rất ít.
"""
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session

from app.db_migrations import MIGRATIONS


def _chay(db: Session) -> None:
    dict(MIGRATIONS)["0307_bo_co_che_luong_cu"](db)


def _cot(db: Session, bang: str) -> set[str]:
    return {c["name"] for c in inspect(db.get_bind()).get_columns(bang)}


def test_0307_bo_bang_va_cot_luong_cu():
    eng = create_engine("sqlite://")
    with Session(eng) as db:
        db.execute(text(
            "CREATE TABLE salary_rate_rules (id INTEGER PRIMARY KEY, payroll_group VARCHAR(40),"
            " pay_grade_key VARCHAR(20), monthly_amount NUMERIC(14,2))"
        ))
        db.execute(text(
            "CREATE TABLE departments (id INTEGER PRIMARY KEY, name VARCHAR(255),"
            " salary_mechanism VARCHAR(24) NOT NULL DEFAULT 'cung',"
            " probation_ratio NUMERIC(5,4) NOT NULL DEFAULT 0.80,"
            " has_piece_work BOOLEAN NOT NULL DEFAULT 0)"
        ))
        db.execute(text(
            "CREATE TABLE employees (id INTEGER PRIMARY KEY, full_name VARCHAR(255),"
            " payroll_group VARCHAR(40))"
        ))
        db.execute(text("CREATE INDEX ix_employees_payroll_group ON employees (payroll_group)"))
        db.execute(text(
            "CREATE TABLE employee_salaries (id INTEGER PRIMARY KEY, employee_id INTEGER,"
            " amount_mode VARCHAR(8) NOT NULL DEFAULT 'rule', base_amount NUMERIC(14,2),"
            " source_salary_row_id INTEGER, luong_vi_tri NUMERIC(14,2))"
        ))
        db.execute(text("INSERT INTO departments (id, name) VALUES (1, 'Tổ In')"))
        db.execute(text("INSERT INTO employees (id, full_name, payroll_group) VALUES (1, 'A', 'to_in')"))
        db.execute(text(
            "INSERT INTO employee_salaries (employee_id, amount_mode, base_amount, luong_vi_tri)"
            " VALUES (1, 'manual', 9000000, 0)"
        ))
        db.commit()

        _chay(db)

        assert "salary_rate_rules" not in set(inspect(db.get_bind()).get_table_names())
        assert _cot(db, "departments") == {"id", "name", "has_piece_work"}
        assert _cot(db, "employees") == {"id", "full_name"}
        assert _cot(db, "employee_salaries") == {"id", "employee_id", "base_amount", "luong_vi_tri"}
        # Dữ liệu còn lại không mất: base_amount là fallback của bản ghi cũ.
        assert db.execute(text("SELECT base_amount FROM employee_salaries")).scalar_one() == 9000000
        _chay(db)   # idempotent


def test_0307_db_trang_khong_no():
    with Session(create_engine("sqlite://")) as db:
        _chay(db)


def test_model_va_schema_khong_con_co_che_luong_cu():
    import app.models as m
    import app.models.payroll as mp
    from app.models.department import Department
    from app.models.employee import Employee
    from app.models.payroll import EmployeeSalary
    from app.schemas.employee import EmployeeOut
    from app.schemas.payroll import LineOut, SalaryIn, SalaryOut
    from app.schemas.rbac import DepartmentOut

    assert not hasattr(m, "SalaryRateRule")
    assert not any(hasattr(mp, x) for x in ("AMOUNT_RULE", "APPLY_BAC_THO", "SENIORITY_BANDS"))
    assert not {"salary_mechanism", "probation_ratio"} & set(Department.__table__.columns.keys())
    assert "payroll_group" not in Employee.__table__.columns
    assert not {"amount_mode", "source_salary_row_id"} & set(EmployeeSalary.__table__.columns.keys())
    assert "payroll_group" not in EmployeeOut.model_fields and "payroll_group" not in LineOut.model_fields
    assert "amount_mode" not in SalaryIn.model_fields and "amount_mode" not in SalaryOut.model_fields
    assert not {"salary_mechanism", "probation_ratio"} & set(DepartmentOut.model_fields)
