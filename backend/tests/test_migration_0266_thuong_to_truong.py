"""Migration 0266 — cột `payroll_lines.thuong_to_truong` (thưởng/phạt tổ trưởng theo chất lượng).

Bảng nguồn `san_xuat_thuong_to_truong` là bảng MỚI nên `create_all` tự dựng; chỉ cột trên bảng
lương CŨ mới cần ALTER. Hai thứ phải đúng, sai là vỡ DB đang chạy:

  · DB đã có dòng lương ⇒ thêm cột KHÔNG được đụng số cũ, và dòng cũ nhận 0 (không NULL — cột
    `NOT NULL DEFAULT 0`, engine cộng thẳng vào `gross` nên NULL là `None + float` ⇒ 500);
  · chạy lại KHÔNG được ném (`run_migrations` bỏ qua id đã applied, nhưng DB fresh chạy
    `create_all` trước rồi mới tới migration — lúc đó cột đã có sẵn).
"""
from __future__ import annotations

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session

from app.db_migrations import _migrate_thuong_to_truong_cot_luong


def _fixture(*, co_cot: bool):
    """DB "cũ" chỉ có đúng phần `payroll_lines` mà migration đụng tới, kèm một dòng lương thật."""
    engine = create_engine("sqlite+pysqlite:///:memory:")
    them = ", thuong_to_truong NUMERIC(14,2) NOT NULL DEFAULT 0" if co_cot else ""
    with engine.begin() as cn:
        cn.execute(text(
            "CREATE TABLE payroll_lines (id INTEGER PRIMARY KEY, employee_id INTEGER, "
            f"khoan NUMERIC(14,2) NOT NULL DEFAULT 0, gross NUMERIC(14,2) NOT NULL DEFAULT 0{them})"
        ))
        cn.execute(text(
            "INSERT INTO payroll_lines (id, employee_id, khoan, gross) VALUES (1, 7, 500000, 9000000)"
        ))
    return engine


def _chay(engine) -> None:
    with Session(engine) as db:
        _migrate_thuong_to_truong_cot_luong(db)


def _cot(engine) -> set[str]:
    return {c["name"] for c in inspect(engine).get_columns("payroll_lines")}


def test_them_cot_va_KHONG_dung_so_cu():
    engine = _fixture(co_cot=False)
    assert "thuong_to_truong" not in _cot(engine)

    _chay(engine)

    assert "thuong_to_truong" in _cot(engine)
    with engine.begin() as cn:
        r = cn.execute(text(
            "SELECT khoan, gross, thuong_to_truong FROM payroll_lines WHERE id = 1"
        )).one()
    assert float(r[0]) == 500000 and float(r[1]) == 9000000
    assert r[2] is not None and float(r[2]) == 0, "dòng cũ phải là 0, KHÔNG được NULL"


def test_chay_lai_khong_nem():
    engine = _fixture(co_cot=False)
    _chay(engine)
    _chay(engine)                      # idempotent
    assert "thuong_to_truong" in _cot(engine)


def test_db_fresh_da_co_cot_thi_bo_qua():
    """DB mới dựng bằng `create_all` (model đã khai cột) rồi mới chạy migration."""
    engine = _fixture(co_cot=True)
    _chay(engine)
    assert "thuong_to_truong" in _cot(engine)


def test_chua_co_bang_payroll_lines_thi_bo_qua():
    """Migration chạy trên DB trắng chưa dựng bảng lương ⇒ no-op, không ném."""
    engine = create_engine("sqlite+pysqlite:///:memory:")
    _chay(engine)
    assert "payroll_lines" not in set(inspect(engine).get_table_names())
