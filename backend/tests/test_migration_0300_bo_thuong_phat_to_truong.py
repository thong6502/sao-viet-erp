"""Migration 0300: bỏ hẳn thưởng/phạt tổ trưởng — bảng bậc + cột lương.

Chạy trên DB đã có bảng/cột cũ (mô phỏng DB dev đang sống): `create_all` không bao giờ tạo lại thứ
đã xoá khỏi model nên test trên DB trắng chứng minh được rất ít.
"""
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session

from app.db_migrations import MIGRATIONS


def _chay(db: Session) -> None:
    fn = dict(MIGRATIONS)["0300_bo_thuong_phat_to_truong"]
    fn(db)


def test_0300_bo_bang_bac_va_cot_luong():
    eng = create_engine("sqlite://")
    with Session(eng) as db:
        db.execute(text(
            "CREATE TABLE payroll_lines (id INTEGER PRIMARY KEY, khoan NUMERIC(14,2),"
            " thuong_to_truong NUMERIC(14,2) NOT NULL DEFAULT 0)"
        ))
        db.execute(text("CREATE TABLE piece_leader_bonus_brackets (id INTEGER PRIMARY KEY)"))
        db.commit()
        _chay(db)
        insp = inspect(db.get_bind())
        assert "piece_leader_bonus_brackets" not in set(insp.get_table_names())
        cols = {c["name"] for c in insp.get_columns("payroll_lines")}
        assert "thuong_to_truong" not in cols
        assert "khoan" in cols
        _chay(db)   # idempotent


def test_0300_db_trang_khong_no():
    eng = create_engine("sqlite://")
    with Session(eng) as db:
        _chay(db)


def test_model_khong_con_thuong_phat_to_truong():
    import app.models as m
    from app.models.payroll import PayrollLine
    from app.schemas.payroll import LineOut

    assert not hasattr(m, "PieceLeaderBonusBracket")
    assert "thuong_to_truong" not in PayrollLine.__table__.columns
    assert "thuong_to_truong" not in LineOut.model_fields
