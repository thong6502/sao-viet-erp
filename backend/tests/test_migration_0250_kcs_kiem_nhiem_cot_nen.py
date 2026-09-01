"""Migration `0250_kcs_kiem_nhiem_cot_nen` — module KCS kiêm nhiệm, Task 1/12.

Tái hiện hình dạng DB CŨ (trước migration): 5 bảng đã tồn tại (`cong_doan`, `lsx_cong_doan`,
`bai_ghep_cong_doan`, `san_xuat_cong_viec`, `san_xuat_kcs_batch`) nhưng THIẾU các cột KCS mới —
đúng thực tế dev/prod hiện tại (bảng có sẵn, cột chưa có). Migration phải ALTER thêm cột, KHÔNG
được lỗi, và chạy lại lần hai phải là no-op (guard theo cột đã tồn tại).

CHỈ soi phần ALTER cột — backfill số liệu là việc của migration `0251`
(`test_migration_0251_kcs_kiem_nhiem_backfill.py`).
"""
from __future__ import annotations

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session

from app.db_migrations import _migrate_kcs_kiem_nhiem_cot_nen


def _old_schema_engine():
    """5 bảng tối giản, CỐ Ý thiếu mọi cột KCS mới (như DB dev/prod trước migration này)."""
    eng = create_engine("sqlite://")
    with eng.begin() as con:
        con.execute(text("CREATE TABLE cong_doan (id INTEGER PRIMARY KEY, ma TEXT)"))
        con.execute(text("INSERT INTO cong_doan (id, ma) VALUES (1, 'CD-IN')"))

        con.execute(text("CREATE TABLE lsx_cong_doan (id INTEGER PRIMARY KEY, cong_doan_id INTEGER)"))
        con.execute(text("INSERT INTO lsx_cong_doan (id, cong_doan_id) VALUES (1, 1)"))

        con.execute(text(
            "CREATE TABLE bai_ghep_cong_doan (id INTEGER PRIMARY KEY, cong_doan_id INTEGER)"
        ))
        con.execute(text("INSERT INTO bai_ghep_cong_doan (id, cong_doan_id) VALUES (1, 1)"))

        con.execute(text(
            "CREATE TABLE san_xuat_cong_viec (id INTEGER PRIMARY KEY, la_kcs_cuoi BOOLEAN)"
        ))
        con.execute(text("INSERT INTO san_xuat_cong_viec (id, la_kcs_cuoi) VALUES (1, 0)"))

        con.execute(text(
            "CREATE TABLE departments (id INTEGER PRIMARY KEY, name TEXT)"
        ))
        con.execute(text("INSERT INTO departments (id, name) VALUES (1, 'To KCS')"))

        con.execute(text(
            "CREATE TABLE san_xuat_kcs_batch (id INTEGER PRIMARY KEY, cong_viec_id INTEGER)"
        ))
        con.execute(text("INSERT INTO san_xuat_kcs_batch (id, cong_viec_id) VALUES (1, 1)"))
    return eng


def _cols(eng, table):
    return {c["name"] for c in inspect(eng).get_columns(table)}


def _index_names(eng, table):
    return {ix["name"] for ix in inspect(eng).get_indexes(table)}


def test_them_cot_khong_loi_va_dung_kieu():
    eng = _old_schema_engine()
    with Session(eng) as db:
        _migrate_kcs_kiem_nhiem_cot_nen(db)  # KHÔNG được raise

    assert "la_kcs" in _cols(eng, "cong_doan")
    assert {"la_kcs", "kcs_tieu_chi_bo_sung_json"} <= _cols(eng, "lsx_cong_doan")
    assert {"la_kcs", "kcs_tieu_chi_bo_sung_json"} <= _cols(eng, "bai_ghep_cong_doan")
    assert "kcs_tieu_chi_json" in _cols(eng, "san_xuat_cong_viec")
    assert {"loai", "kcs_department_id", "checklist_json"} <= _cols(eng, "san_xuat_kcs_batch")

    # Model khai `index=True` cho `kcs_department_id` — ALTER thủ công phải tự tạo index cùng
    # tên SQLAlchemy tự sinh (`ix_<table>_<cot>`), không chỉ thêm cột suông (bug đã vá: FK có
    # nhưng thiếu index thật trên DB dev/prod, nơi bảng đã tồn tại từ trước nên create_all
    # không tự sinh index cho cột mới).
    assert "ix_san_xuat_kcs_batch_kcs_department_id" in _index_names(eng, "san_xuat_kcs_batch")

    with eng.connect() as con:
        # Dòng cũ đọc ra false/NULL đúng nghĩa "chưa khai" — không suy diễn gì thêm ở migration này.
        assert con.execute(text("SELECT la_kcs FROM cong_doan WHERE id = 1")).scalar() in (0, False)
        assert con.execute(
            text("SELECT la_kcs, kcs_tieu_chi_bo_sung_json FROM lsx_cong_doan WHERE id = 1")
        ).one() == (0, None)
        assert con.execute(text("SELECT loai FROM san_xuat_kcs_batch WHERE id = 1")).scalar() == "routing"
        assert con.execute(
            text("SELECT kcs_department_id FROM san_xuat_kcs_batch WHERE id = 1")
        ).scalar() is None


def test_chay_lai_lan_hai_khong_loi_khong_doi_du_lieu():
    eng = _old_schema_engine()
    with Session(eng) as db:
        _migrate_kcs_kiem_nhiem_cot_nen(db)

    # Giả lập dữ liệu đã được service ghi sau lượt ALTER đầu — migration KHÔNG được đụng lại.
    with eng.begin() as con:
        con.execute(text("UPDATE cong_doan SET la_kcs = 1 WHERE id = 1"))

    with Session(eng) as db:
        _migrate_kcs_kiem_nhiem_cot_nen(db)  # KHÔNG được raise (cột đã có → guard bỏ qua)

    # Guard theo cột bỏ qua cả ALTER lẫn CREATE INDEX ở lượt hai — index vẫn phải còn đó.
    assert "ix_san_xuat_kcs_batch_kcs_department_id" in _index_names(eng, "san_xuat_kcs_batch")

    with eng.connect() as con:
        assert con.execute(text("SELECT la_kcs FROM cong_doan WHERE id = 1")).scalar() in (1, True)
