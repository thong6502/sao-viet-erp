"""Migration 0269 — gỡ ô "Dự kiến có khuôn" (`phieu_thanh_pham.khuon_ngay_du_kien`).

Ô này chỉ là DỰ TRÙ của sale, không nơi nào đọc: mốc thật để xếp lịch nằm ở
`khuon_be.ngay_ve_du_kien` của chính con dao. Migration phải xoá được cột mà KHÔNG đụng
`khuon_nguon` và `phi_khuon` nằm cạnh — hai ô đó vẫn là câu trả lời có tiền đi kèm.

Idempotent: DB fresh (`create_all` dựng theo model đã bỏ cột) và DB đã xoá rồi đều là no-op.
"""
from __future__ import annotations

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session

from app.db_migrations import _migrate_go_khuon_ngay_du_kien


def _fixture(*, con_cot: bool):
    engine = create_engine("sqlite+pysqlite:///:memory:")
    cot_ngay = "khuon_ngay_du_kien DATE, " if con_cot else ""
    gia_tri = "'2026-09-20', " if con_cot else ""
    ten_ngay = "khuon_ngay_du_kien, " if con_cot else ""
    with engine.begin() as cn:
        cn.execute(text(
            "CREATE TABLE phieu_thanh_pham (id INTEGER PRIMARY KEY, thu_tu INTEGER, "
            "phi_khuon NUMERIC(18,2) NOT NULL DEFAULT 0, khuon_nguon VARCHAR(10), "
            f"{cot_ngay}dai_khuon NUMERIC(10,2) NOT NULL DEFAULT 0)"
        ))
        cn.execute(text(
            f"INSERT INTO phieu_thanh_pham (id, thu_tu, phi_khuon, khuon_nguon, {ten_ngay}dai_khuon) "
            f"VALUES (1, 3, 250000, 'lam_moi', {gia_tri}50)"
        ))
    return engine


def _chay(engine) -> None:
    with Session(engine) as db:
        _migrate_go_khuon_ngay_du_kien(db)


def _cot(engine) -> set[str]:
    return {c["name"] for c in inspect(engine).get_columns("phieu_thanh_pham")}


def test_xoa_cot_ngay_va_giu_nguyen_o_tien():
    engine = _fixture(con_cot=True)
    assert "khuon_ngay_du_kien" in _cot(engine)

    _chay(engine)

    assert "khuon_ngay_du_kien" not in _cot(engine)
    assert {"phi_khuon", "khuon_nguon", "dai_khuon"} <= _cot(engine)
    with engine.begin() as cn:
        r = cn.execute(text(
            "SELECT phi_khuon, khuon_nguon, dai_khuon FROM phieu_thanh_pham WHERE id = 1"
        )).one()
    assert [float(r[0]), r[1], float(r[2])] == [250000, "lam_moi", 50]


def test_chay_lai_khong_nem():
    engine = _fixture(con_cot=True)
    _chay(engine)
    _chay(engine)                      # idempotent
    assert "khuon_ngay_du_kien" not in _cot(engine)


def test_db_fresh_khong_co_cot_thi_bo_qua():
    engine = _fixture(con_cot=False)
    _chay(engine)
    assert "khuon_nguon" in _cot(engine)


def test_db_trang_chua_co_bang_thi_bo_qua():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    _chay(engine)
    assert set(inspect(engine).get_table_names()) == set()
