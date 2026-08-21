"""Hồi quy cho deploy đỏ 2026-08-21: migration 0168 backfill KHÔNG được dùng ORM full-select.

Tái hiện đúng hình dạng DB prod CŨ: bảng `cong_doan` tồn tại nhưng THIẾU cả `nhom_may_cho_phep`
(cột 0168 sắp thêm) lẫn `he_so_ngoai_dong` (cột migration 0196 thêm SAU). `db.query(CongDoan)`
cũ kéo mọi cột model → `SELECT ... he_so_ngoai_dong` trên bảng thiếu cột đó ⇒ 500. Bản Core
`update()` chỉ đụng `ten` + `nhom_may_cho_phep` nên chạy trót lọt và backfill đúng.
"""
from __future__ import annotations

import json

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session

from app.db_migrations import _migrate_cong_doan_nhom_may_cho_phep


def _old_prod_congdoan_engine():
    """Bảng cong_doan tối giản, CỐ Ý thiếu nhom_may_cho_phep + he_so_ngoai_dong (như prod cũ)."""
    eng = create_engine("sqlite://")
    with eng.begin() as con:
        con.execute(text("CREATE TABLE cong_doan (id INTEGER PRIMARY KEY, ma TEXT, ten TEXT)"))
        con.execute(text("INSERT INTO cong_doan (ma, ten) VALUES ('CD1', 'Ghi kẽm CTP')"))
        con.execute(text("INSERT INTO cong_doan (ma, ten) VALUES ('CD2', 'In offset')"))
        con.execute(text("INSERT INTO cong_doan (ma, ten) VALUES ('CD3', 'Đóng gói')"))
    return eng


def _nhom(con, ten):
    row = con.execute(
        text("SELECT nhom_may_cho_phep FROM cong_doan WHERE ten = :t"), {"t": ten}
    ).scalar()
    return None if row is None else json.loads(row)


def test_0168_khong_500_va_backfill_dung_tren_db_thieu_cot_sau():
    eng = _old_prod_congdoan_engine()
    with Session(eng) as db:
        _migrate_cong_doan_nhom_may_cho_phep(db)  # KHÔNG được raise UndefinedColumn/OperationalError

    with eng.connect() as con:
        assert "nhom_may_cho_phep" in {c["name"] for c in inspect(eng).get_columns("cong_doan")}
        assert _nhom(con, "Ghi kẽm CTP") == ["Chế bản"]
        assert _nhom(con, "In offset") == ["Máy in", "In ngoài"]
        assert _nhom(con, "Đóng gói") is None  # không nằm trong bảng backfill → giữ NULL


def test_0168_idempotent_khi_cot_da_co_nhung_hang_con_null():
    """Mô phỏng lượt prod trước đã ADD cột rồi chết giữa chừng: cột có, hàng NULL → vẫn backfill."""
    eng = _old_prod_congdoan_engine()
    with eng.begin() as con:
        con.execute(text("ALTER TABLE cong_doan ADD COLUMN nhom_may_cho_phep JSON"))
    with Session(eng) as db:
        _migrate_cong_doan_nhom_may_cho_phep(db)
    with eng.connect() as con:
        assert _nhom(con, "Ghi kẽm CTP") == ["Chế bản"]

    # Chạy lại lần nữa: giá trị đã set không bị đụng, không lỗi.
    with Session(eng) as db:
        _migrate_cong_doan_nhom_may_cho_phep(db)
    with eng.connect() as con:
        assert _nhom(con, "Ghi kẽm CTP") == ["Chế bản"]
