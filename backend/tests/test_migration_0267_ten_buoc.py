"""Migration `0267` — bước đã gắn công đoạn mà `ten` còn trơ nhãn tạm thì lấy lại tên danh mục."""
from __future__ import annotations

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.db_migrations import _migrate_ten_buoc_tro_cong_doan


def _engine():
    eng = create_engine("sqlite://")
    with eng.begin() as con:
        con.execute(text("CREATE TABLE cong_doan (id INTEGER PRIMARY KEY, ten TEXT)"))
        for i, t in ((10, "Ghi kẽm CTP"), (11, "Bình bài & dàn trang"), (12, "Cắt demi / chia tờ")):
            con.execute(text("INSERT INTO cong_doan (id, ten) VALUES (:i, :t)"), {"i": i, "t": t})
        for bang in ("lsx_cong_doan", "bai_ghep_cong_doan"):
            con.execute(text(
                f"CREATE TABLE {bang} (id INTEGER PRIMARY KEY, ten TEXT, cong_doan_id INTEGER)"
            ))
            rows = [
                (1, "Công đoạn", 10),          # nhãn tạm + đã gắn công đoạn → nắn
                (2, "", 11),                   # trống + đã gắn công đoạn → nắn
                (3, "Tên tự do của người", 12),  # người đặt tên → GIỮ NGUYÊN
                (4, "Công đoạn", None),        # chưa gắn công đoạn → GIỮ NGUYÊN
            ]
            for id_, ten, cd in rows:
                con.execute(
                    text(f"INSERT INTO {bang} (id, ten, cong_doan_id) VALUES (:i, :t, :c)"),
                    {"i": id_, "t": ten, "c": cd},
                )
    return eng


def _doc(db, bang):
    return {r[0]: r[1] for r in db.execute(text(f"SELECT id, ten FROM {bang}")).all()}


def test_nan_ten_buoc_va_idempotent():
    eng = _engine()
    with Session(eng) as db:
        _migrate_ten_buoc_tro_cong_doan(db)
        for bang in ("lsx_cong_doan", "bai_ghep_cong_doan"):
            sau = _doc(db, bang)
            assert sau[1] == "Ghi kẽm CTP", bang
            assert sau[2] == "Bình bài & dàn trang", bang
            assert sau[3] == "Tên tự do của người", bang
            assert sau[4] == "Công đoạn", bang
        # Chạy lại không đổi gì thêm.
        truoc = {b: _doc(db, b) for b in ("lsx_cong_doan", "bai_ghep_cong_doan")}
        _migrate_ten_buoc_tro_cong_doan(db)
        assert {b: _doc(db, b) for b in truoc} == truoc


def test_bang_chua_ton_tai_thi_bo_qua():
    eng = create_engine("sqlite://")
    with Session(eng) as db:
        _migrate_ten_buoc_tro_cong_doan(db)  # không có bảng nào → không nổ
