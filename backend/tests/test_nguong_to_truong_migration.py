"""Migration 0133 — ngưỡng tổ trưởng: đo bằng TIỀN → đo bằng SẢN LƯỢNG.

Chủ nhìn màn thật rồi nói: *"nó là sản lượng mà sao lại chữ đ là sao"*. Ô đang là tiền nhưng trong
đầu chủ nó là số lượng làm được — và màn hình là phép thử cuối.

Bảng này mới dựng cùng ngày, trên DB dev đang 0 dòng, chưa từng lên prod. Vẫn phải có migration vì
`create_all` chỉ TẠO bảng thiếu, không bao giờ ALTER bảng đã có.
"""
from __future__ import annotations

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session

from app.db_migrations import _migrate_nguong_to_truong_theo_san_luong


def _engine_cu():
    """DB "cũ": bảng ngưỡng còn cột `min_khoan_to` (đo bằng tiền), có sẵn một dòng."""
    engine = create_engine("sqlite+pysqlite:///:memory:")
    with engine.begin() as cn:
        cn.execute(text(
            "CREATE TABLE piece_leader_bonus_settings (id INTEGER PRIMARY KEY, "
            "department_id INTEGER NOT NULL UNIQUE, "
            "min_khoan_to NUMERIC(14,2) NOT NULL DEFAULT 0, "
            "created_at TIMESTAMP, updated_at TIMESTAMP)"))
        cn.execute(text(
            "INSERT INTO piece_leader_bonus_settings (department_id, min_khoan_to) "
            "VALUES (6, 3000000)"))
    return engine


def _cols(engine) -> set[str]:
    return {c["name"] for c in inspect(engine).get_columns("piece_leader_bonus_settings")}


def test_be_thang_con_so_cu_sang_cot_moi():
    """Chủ chốt: `3.000.000 đ` → `3.000.000 sản lượng`.

    Ngưỡng là con số trần, không kèm đơn vị (chủ chốt "Đơn vị bỏ đi") — nên chỉ có đúng một cột
    để bê sang, và cột tiền cũ phải biến mất chứ không để lại làm nguồn sự thật thứ hai."""
    engine = _engine_cu()
    with Session(engine) as db:
        _migrate_nguong_to_truong_theo_san_luong(db)

    cols = _cols(engine)
    assert "min_output_qty" in cols
    assert "min_khoan_to" not in cols, "cột cũ phải biến mất, để lại là hai nguồn sự thật"

    with engine.begin() as cn:
        qty = cn.execute(text(
            "SELECT min_output_qty FROM piece_leader_bonus_settings")).scalar()
    assert float(qty) == 3_000_000


def test_chay_lai_lan_hai_khong_no():
    """Migration chạy MỖI lần khởi động ⇒ guard theo cột, lần hai phải là no-op."""
    engine = _engine_cu()
    with Session(engine) as db:
        _migrate_nguong_to_truong_theo_san_luong(db)
    with engine.begin() as cn:
        cn.execute(text("UPDATE piece_leader_bonus_settings SET min_output_qty = 5000"))

    with Session(engine) as db:
        _migrate_nguong_to_truong_theo_san_luong(db)   # không được nổ

    with engine.begin() as cn:
        qty = cn.execute(text(
            "SELECT min_output_qty FROM piece_leader_bonus_settings")).scalar()
    assert float(qty) == 5_000, "lần hai không được đè lên số đã khai"


def test_bo_qua_khi_chua_co_bang():
    """DB trắng: `create_all` sẽ dựng bảng ĐÚNG hình mới ⇒ migration không có gì để làm."""
    engine = create_engine("sqlite+pysqlite:///:memory:")
    with Session(engine) as db:
        _migrate_nguong_to_truong_theo_san_luong(db)   # không được nổ
