"""Migration `0253_xep_lich_phan_doan` — thêm chiều PHÂN ĐOẠN cho `xep_lich_cong_doan`
(`docs/superpowers/plans/2026-08-31-tach-lan-chay-cong-doan.md`).

DB test dựng bằng `create_all` nên bốn nhánh `if` trong migration KHÔNG BAO GIỜ chạy ở bộ test
thường — bảng sinh ra đã đủ cột. File này tái hiện hình dạng DB THẬT (live/prod đang thiếu bốn
cột) rồi chạy migration trên đó: đây là chỗ duy nhất chứng minh câu lệnh ALTER thật sự chạy được.
"""
from __future__ import annotations

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session

from app.db_migrations import _migrate_xep_lich_phan_doan


def _schema_truoc_0253(*, co_cot_goc=False):
    """`xep_lich_cong_doan` như DB live trước migration: chưa có bốn cột phân đoạn, có dòng sẵn.

    `co_cot_goc=True` tái hiện lần chạy TRƯỚC hỏng giữa chừng — cột `goc_dong_id` đã thêm xong
    nhưng index chưa kịp tạo.
    """
    eng = create_engine("sqlite://")
    cot_goc = ", goc_dong_id INTEGER" if co_cot_goc else ""
    with eng.begin() as con:
        con.execute(text(
            "CREATE TABLE xep_lich_cong_doan ("
            "  id INTEGER PRIMARY KEY, nguon TEXT NOT NULL DEFAULT 'lsx', lsx_id INTEGER,"
            "  lsx_cong_doan_id INTEGER, source_thu_tu INTEGER NOT NULL DEFAULT 0,"
            f"  trang_thai TEXT NOT NULL DEFAULT 'cho_xep'{cot_goc})"
        ))
        con.execute(text(
            "INSERT INTO xep_lich_cong_doan (id, nguon, lsx_id, lsx_cong_doan_id) VALUES"
            " (1, 'lsx', 10, 100), (2, 'lsx', 10, 101)"
        ))
    return eng


def _cols(eng):
    return {c["name"] for c in inspect(eng).get_columns("xep_lich_cong_doan")}


def _indexes(eng):
    return {i["name"] for i in inspect(eng).get_indexes("xep_lich_cong_doan")}


def test_them_du_bon_cot_va_index():
    eng = _schema_truoc_0253()
    with Session(eng) as db:
        _migrate_xep_lich_phan_doan(db)

    assert {"so_luong", "phan_doan_so", "phan_doan_tong", "goc_dong_id"} <= _cols(eng)
    assert "ix_xep_lich_cong_doan_goc_dong_id" in _indexes(eng)


def test_hang_cu_thanh_mot_phan_doan_tron_buoc():
    """Hàng CŨ = chưa tách: `1/1` và `so_luong` NULL (nghĩa "trọn bước", KHÁC hẳn 0).

    KHÔNG backfill `so_luong` bằng số thật của bước — số đó tính lúc đọc từ routing, viết cứng
    xuống đây là đẻ nguồn số thứ hai.
    """
    eng = _schema_truoc_0253()
    with Session(eng) as db:
        _migrate_xep_lich_phan_doan(db)

    with eng.connect() as con:
        rows = con.execute(text(
            "SELECT id, so_luong, phan_doan_so, phan_doan_tong, goc_dong_id"
            " FROM xep_lich_cong_doan ORDER BY id"
        )).all()
    assert [tuple(r) for r in rows] == [(1, None, 1, 1, None), (2, None, 1, 1, None)]


def test_chay_lai_lan_hai_khong_loi():
    eng = _schema_truoc_0253()
    with Session(eng) as db:
        _migrate_xep_lich_phan_doan(db)
    with Session(eng) as db:
        _migrate_xep_lich_phan_doan(db)      # cột đã có → guard bỏ qua, không raise

    assert {"so_luong", "phan_doan_so", "phan_doan_tong", "goc_dong_id"} <= _cols(eng)


def test_lan_chay_truoc_hong_giua_chung_van_duoc_tao_index():
    """Cột `goc_dong_id` đã có nhưng index chưa — index phải nằm NGOÀI guard theo cột, không thì
    DB đó vĩnh viễn quét bảng mỗi lần tra cụm phân đoạn."""
    eng = _schema_truoc_0253(co_cot_goc=True)
    assert "ix_xep_lich_cong_doan_goc_dong_id" not in _indexes(eng)

    with Session(eng) as db:
        _migrate_xep_lich_phan_doan(db)

    assert "ix_xep_lich_cong_doan_goc_dong_id" in _indexes(eng)


def test_bang_chua_ton_tai_thi_no_op():
    """DB trắng chưa `create_all` — migration phải im lặng bỏ qua, không lỗi vì thiếu bảng."""
    eng = create_engine("sqlite://")
    with Session(eng) as db:
        _migrate_xep_lich_phan_doan(db)      # KHÔNG được raise

    assert "xep_lich_cong_doan" not in inspect(eng).get_table_names()
