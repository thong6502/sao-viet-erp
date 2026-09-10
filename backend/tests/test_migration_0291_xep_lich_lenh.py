"""mg 0291 — bảng `xep_lich_lenh` (Xếp lịch 3, cấp LỆNH SẢN XUẤT).

Kiểm trên DB TRẮNG dựng bằng CHÍNH migration (không `create_all`): đây mới đúng là thứ DB live
nhận. `create_all` dựng từ model nên nó không chứng minh được gì về migration.
"""
from __future__ import annotations

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session

from app.db_migrations import MIGRATIONS


def _chay(db: Session, key: str) -> None:
    for k, fn in MIGRATIONS:
        if k == key:
            fn(db)
            return
    raise AssertionError(f"khong tim thay migration {key}")


def _db_trang():
    """Engine SQLite trắng đã có mỗi bảng `lsx` — đủ để FK `lsx_id` trỏ được."""
    eng = create_engine("sqlite://")
    db = Session(eng)
    db.execute(text("CREATE TABLE lsx (id INTEGER PRIMARY KEY, ma TEXT)"))
    db.commit()
    return eng, db


def test_0291_tao_bang_xep_lich_lenh():
    eng, db = _db_trang()
    with db:
        _chay(db, "0291_xep_lich_lenh")
        cols = {c["name"] for c in inspect(eng).get_columns("xep_lich_lenh")}
    assert cols == {"id", "lsx_id", "bat_dau_at", "created_by", "created_at", "updated_at"}


def test_0291_chay_lai_khong_vo():
    """Idempotent — mỗi lần deploy là chạy lại toàn bộ danh sách migration."""
    eng, db = _db_trang()
    with db:
        _chay(db, "0291_xep_lich_lenh")
        _chay(db, "0291_xep_lich_lenh")
    assert inspect(eng).has_table("xep_lich_lenh")


def test_0291_mot_lenh_mot_moc():
    """`lsx_id` UNIQUE — màn ở cấp LỆNH, hai mốc cho một lệnh là mâu thuẫn chứ không phải dữ liệu."""
    eng, db = _db_trang()
    with db:
        _chay(db, "0291_xep_lich_lenh")
        idx = inspect(eng).get_indexes("xep_lich_lenh")
        uq = inspect(eng).get_unique_constraints("xep_lich_lenh")
    assert (
        any(i["column_names"] == ["lsx_id"] and i["unique"] for i in idx)
        or any(u["column_names"] == ["lsx_id"] for u in uq)
    )


def test_0291_khop_voi_model():
    """Migration và model phải tả CÙNG một bảng — lệch là DB live khác DB test, im lặng."""
    from app.models.xep_lich_lenh import XepLichLenh

    eng, db = _db_trang()
    with db:
        _chay(db, "0291_xep_lich_lenh")
        cols = {c["name"] for c in inspect(eng).get_columns("xep_lich_lenh")}
    assert cols == {c.name for c in XepLichLenh.__table__.columns}
