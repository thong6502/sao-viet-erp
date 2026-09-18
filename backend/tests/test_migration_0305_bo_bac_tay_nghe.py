"""Migration 0305: bỏ hẳn bậc tay nghề — bảng `job_grades` + cột bậc/hệ số ở hồ sơ và sản xuất.

Chạy trên DB đã có bảng/cột cũ (mô phỏng DB dev đang sống): `create_all` không bao giờ tạo lại thứ
đã xoá khỏi model nên test trên DB trắng chứng minh được rất ít.
"""
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session

from app.db_migrations import MIGRATIONS


def _chay(db: Session) -> None:
    fn = dict(MIGRATIONS)["0305_bo_bac_tay_nghe"]
    fn(db)


def _cot(db: Session, bang: str) -> set[str]:
    return {c["name"] for c in inspect(db.get_bind()).get_columns(bang)}


def test_0305_bo_bang_va_cot_bac():
    eng = create_engine("sqlite://")
    with Session(eng) as db:
        db.execute(text(
            "CREATE TABLE job_grades (id INTEGER PRIMARY KEY, code VARCHAR(20),"
            " output_coefficient NUMERIC(6,3))"
        ))
        db.execute(text(
            "CREATE TABLE employees (id INTEGER PRIMARY KEY, full_name VARCHAR(255),"
            " job_grade_id INTEGER, job_grade VARCHAR(50), pay_grade_key VARCHAR(20))"
        ))
        db.execute(text(
            "CREATE TABLE san_xuat_khoang_tham_gia (id INTEGER PRIMARY KEY, employee_id INTEGER,"
            " job_grade_id INTEGER, output_coefficient NUMERIC(6,3))"
        ))
        db.execute(text(
            "CREATE TABLE san_xuat_phan_bo_dong (id INTEGER PRIMARY KEY, trong_so NUMERIC(18,6),"
            " he_so_bac NUMERIC(6,3))"
        ))
        db.execute(text("INSERT INTO employees (id, full_name, job_grade_id) VALUES (1, 'A', 1)"))
        db.commit()

        _chay(db)

        assert "job_grades" not in set(inspect(db.get_bind()).get_table_names())
        assert _cot(db, "employees") == {"id", "full_name"}
        assert _cot(db, "san_xuat_khoang_tham_gia") == {"id", "employee_id"}
        assert _cot(db, "san_xuat_phan_bo_dong") == {"id", "trong_so"}
        assert db.execute(text("SELECT full_name FROM employees")).scalar_one() == "A"
        _chay(db)   # idempotent


def test_0305_db_trang_khong_no():
    eng = create_engine("sqlite://")
    with Session(eng) as db:
        _chay(db)


def test_model_va_schema_khong_con_bac():
    import app.models as m
    from app.models.employee import Employee
    from app.models.san_xuat_phan_bo import SanXuatPhanBoDong
    from app.models.san_xuat_thuc_thi import SanXuatKhoangThamGia
    from app.schemas.employee import EmployeeOut, TransitionIn

    assert not hasattr(m, "JobGrade")
    assert not {"job_grade_id", "job_grade", "pay_grade_key"} & set(Employee.__table__.columns.keys())
    assert not {"job_grade_id", "output_coefficient"} & set(SanXuatKhoangThamGia.__table__.columns.keys())
    assert "he_so_bac" not in SanXuatPhanBoDong.__table__.columns
    assert not {"job_grade_id", "job_grade_name", "job_grade", "pay_grade_key"} & set(EmployeeOut.model_fields)
    assert not {"new_job_grade_id", "new_job_grade"} & set(TransitionIn.model_fields)
