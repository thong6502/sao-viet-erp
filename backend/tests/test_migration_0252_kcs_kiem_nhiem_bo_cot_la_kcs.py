"""Migration `0252_kcs_kiem_nhiem_bo_cot_la_kcs` — thiết kế lại KCS kiêm nhiệm (2026-08-31,
`docs/superpowers/plans/2026-08-31-kcs-kiem-nhiem-suy-tu-dong.md`): bỏ cờ `la_kcs` khai TAY, nay
suy TỰ ĐỘNG từ routing + `departments.is_kcs`.

Tái hiện hình dạng DB SAU `0250`/`0251` (đã có cột `la_kcs`, có thể đã có dữ liệu cũ) rồi chạy
`0252` — phải DROP sạch, không lỗi, chạy lại lần hai vẫn no-op (cột đã mất thì guard bỏ qua)."""
from __future__ import annotations

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session

from app.db_migrations import _migrate_kcs_kiem_nhiem_bo_cot_la_kcs


def _schema_voi_la_kcs():
    """3 bảng đã qua `0250`/`0251` — có cột `la_kcs`, một vài dòng cờ `true` từ dữ liệu cũ."""
    eng = create_engine("sqlite://")
    with eng.begin() as con:
        con.execute(text(
            "CREATE TABLE cong_doan (id INTEGER PRIMARY KEY, ma TEXT, la_kcs BOOLEAN)"
        ))
        con.execute(text("INSERT INTO cong_doan (id, ma, la_kcs) VALUES (1, 'CD-IN', 1)"))

        con.execute(text(
            "CREATE TABLE lsx_cong_doan (id INTEGER PRIMARY KEY, cong_doan_id INTEGER, "
            "la_kcs BOOLEAN)"
        ))
        con.execute(text("INSERT INTO lsx_cong_doan (id, cong_doan_id, la_kcs) VALUES (1, 1, 1)"))

        con.execute(text(
            "CREATE TABLE bai_ghep_cong_doan (id INTEGER PRIMARY KEY, cong_doan_id INTEGER, "
            "la_kcs BOOLEAN)"
        ))
        con.execute(text(
            "INSERT INTO bai_ghep_cong_doan (id, cong_doan_id, la_kcs) VALUES (1, 1, 0)"
        ))
    return eng


def _cols(eng, table):
    return {c["name"] for c in inspect(eng).get_columns(table)}


def test_bo_cot_khong_loi():
    eng = _schema_voi_la_kcs()
    with Session(eng) as db:
        _migrate_kcs_kiem_nhiem_bo_cot_la_kcs(db)  # KHÔNG được raise

    assert "la_kcs" not in _cols(eng, "cong_doan")
    assert "la_kcs" not in _cols(eng, "lsx_cong_doan")
    assert "la_kcs" not in _cols(eng, "bai_ghep_cong_doan")
    # Cột khác của cùng bảng KHÔNG bị đụng.
    assert "ma" in _cols(eng, "cong_doan")
    assert "cong_doan_id" in _cols(eng, "lsx_cong_doan")


def test_chay_lai_lan_hai_khong_loi():
    eng = _schema_voi_la_kcs()
    with Session(eng) as db:
        _migrate_kcs_kiem_nhiem_bo_cot_la_kcs(db)

    with Session(eng) as db:
        _migrate_kcs_kiem_nhiem_bo_cot_la_kcs(db)  # cột đã mất → guard bỏ qua, không raise

    assert "la_kcs" not in _cols(eng, "cong_doan")


def test_bang_chua_tung_co_cot_khong_sao():
    """Bảng chưa từng chạy `0250` (fresh, hoặc test DB dựng thẳng từ model mới) — không có cột
    `la_kcs` ngay từ đầu, migration vẫn phải no-op, không lỗi vì thiếu cột."""
    eng = create_engine("sqlite://")
    with eng.begin() as con:
        con.execute(text("CREATE TABLE cong_doan (id INTEGER PRIMARY KEY, ma TEXT)"))

    with Session(eng) as db:
        _migrate_kcs_kiem_nhiem_bo_cot_la_kcs(db)  # KHÔNG được raise

    assert _cols(eng, "cong_doan") == {"id", "ma"}
