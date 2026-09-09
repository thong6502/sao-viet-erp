"""Migration 0272 + 0274 — bốn ô công thức về màn Công đoạn, ba ô cũ biến mất.

`0272` chép công thức cũ XUỐNG bảng con của công đoạn (`piece_rates.cong_thuc_luong` →
`cong_doan_dau_viec.cong_thuc_khoan`, `vat_tu_in_an.cong_thuc_luong` →
`cong_doan_dau_viec_vat_tu.cong_thuc_luong`) để số của lệnh không xê dịch ngay sau khi deploy;
`0274` gỡ ba ô nguồn. Hai migration này chạy trên DB có dữ liệu thật nên phải khoá bằng test.

Bẫy được canh ở đây là bẫy Inspector–pool: `inspect()` mượn rồi TRẢ connection, mà pool SQLite
`:memory:` chỉ có MỘT connection dùng chung với Session — trả về là ROLLBACK. Đã đo: xếp một lần
soi cột XEN GIỮA hai lệnh ghi của `0272` thì backfill `cong_thuc_khoan` biến mất IM LẶNG (test đầu
tiên đỏ đúng ở đó). `0274` chỉ chạy DDL nên pysqlite tự commit, xen kẽ vẫn sống — nó xếp cùng khuôn
để không ai phải nhớ ngoại lệ này.
"""
from __future__ import annotations

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db_migrations import (
    _migrate_cong_thuc_ve_cong_doan,
    _migrate_go_ba_o_cong_thuc_luong,
)


def _engine():
    """Đúng pool mà bộ test thật dùng (`app/db.py`): MỘT connection dùng chung cho cả Session lẫn
    Inspector — điều kiện để bẫy "Inspector trả connection = ROLLBACK" lộ ra."""
    return create_engine("sqlite+pysqlite:///:memory:", poolclass=StaticPool,
                         connect_args={"check_same_thread": False})


def _engine_0272():
    """Bốn bảng ở trạng thái TRƯỚC migration: bảng con chưa có ô, bảng nguồn còn công thức."""
    engine = _engine()
    with engine.begin() as cn:
        cn.execute(text(
            "CREATE TABLE piece_rates (id INTEGER PRIMARY KEY, ten VARCHAR(80),"
            " cong_thuc_luong TEXT)"))
        cn.execute(text(
            "CREATE TABLE vat_tu_in_an (id INTEGER PRIMARY KEY, ma VARCHAR(40),"
            " cong_thuc_luong TEXT)"))
        cn.execute(text(
            "CREATE TABLE cong_doan_dau_viec (id INTEGER PRIMARY KEY, cong_doan_id INTEGER,"
            " piece_rate_id INTEGER)"))
        cn.execute(text(
            "CREATE TABLE cong_doan_dau_viec_vat_tu (id INTEGER PRIMARY KEY,"
            " cong_doan_dau_viec_id INTEGER, vat_tu_id INTEGER, thu_tu INTEGER)"))
        cn.execute(text(
            "INSERT INTO piece_rates (id, ten, cong_thuc_luong) VALUES"
            " (1, 'In tờ rời', 'sl_vao * so_luot_chay'), (2, 'Bắt tay', NULL)"))
        cn.execute(text(
            "INSERT INTO vat_tu_in_an (id, ma, cong_thuc_luong) VALUES"
            " (1, 'MUC-CMYK', 'sl_vao / 8000'), (2, 'KEM-74', '')"))
        cn.execute(text(
            "INSERT INTO cong_doan_dau_viec (id, cong_doan_id, piece_rate_id) VALUES"
            " (10, 2, 1), (11, 2, 2)"))
        cn.execute(text(
            "INSERT INTO cong_doan_dau_viec_vat_tu"
            " (id, cong_doan_dau_viec_id, vat_tu_id, thu_tu) VALUES"
            " (20, 10, 1, 0), (21, 10, 2, 1)"))
    return engine


def _chay(engine, ham) -> None:
    with Session(engine) as db:
        ham(db)


def _lay(engine, sql: str):
    with engine.begin() as cn:
        return cn.execute(text(sql)).all()


def test_0272_chep_ca_hai_cong_thuc_xuong_bang_con():
    engine = _engine_0272()

    _chay(engine, _migrate_cong_thuc_ve_cong_doan)

    # Đầu việc trỏ tới đơn giá CÓ công thức thì nhận đúng câu đó; trỏ tới đơn giá trống thì để trống
    # chứ không đoán.
    assert _lay(engine, "SELECT id, cong_thuc_khoan FROM cong_doan_dau_viec ORDER BY id") == [
        (10, "sl_vao * so_luot_chay"), (11, None)]
    # Dòng vật tư: chuỗi rỗng ở nguồn cũng là "chưa khai", không được chép thành ''.
    assert _lay(engine,
                "SELECT id, cong_thuc_luong FROM cong_doan_dau_viec_vat_tu ORDER BY id") == [
        (20, "sl_vao / 8000"), (21, None)]


def test_0272_chay_lai_khong_de_cau_da_sua_tay():
    engine = _engine_0272()
    _chay(engine, _migrate_cong_thuc_ve_cong_doan)
    with engine.begin() as cn:
        cn.execute(text("UPDATE cong_doan_dau_viec SET cong_thuc_khoan = 'sl_ra * 2' WHERE id = 10"))
        cn.execute(text(
            "UPDATE cong_doan_dau_viec_vat_tu SET cong_thuc_luong = 'so_mau * 3' WHERE id = 20"))

    _chay(engine, _migrate_cong_thuc_ve_cong_doan)

    assert _lay(engine, "SELECT cong_thuc_khoan FROM cong_doan_dau_viec WHERE id = 10") == [
        ("sl_ra * 2",)]
    assert _lay(engine, "SELECT cong_thuc_luong FROM cong_doan_dau_viec_vat_tu WHERE id = 20") == [
        ("so_mau * 3",)]


def test_0272_bo_qua_khi_db_chua_co_bang_con():
    engine = _engine()
    with engine.begin() as cn:
        cn.execute(text("CREATE TABLE piece_rates (id INTEGER PRIMARY KEY, cong_thuc_luong TEXT)"))
    _chay(engine, _migrate_cong_thuc_ve_cong_doan)  # không ném


def test_0274_go_cong_thuc_luong_o_CA_BA_bang():
    engine = _engine()
    with engine.begin() as cn:
        for bang in ("may_thiet_bi", "piece_rates", "vat_tu_in_an"):
            cn.execute(text(
                f"CREATE TABLE {bang} (id INTEGER PRIMARY KEY, ten VARCHAR(80),"
                " cong_thuc_luong TEXT)"))
            cn.execute(text(f"INSERT INTO {bang} (id, ten, cong_thuc_luong) VALUES (1, 'x', 'a')"))

    _chay(engine, _migrate_go_ba_o_cong_thuc_luong)

    insp = inspect(engine)
    for bang in ("may_thiet_bi", "piece_rates", "vat_tu_in_an"):
        cot = {c["name"] for c in insp.get_columns(bang)}
        assert "cong_thuc_luong" not in cot, f"{bang} vẫn còn ô cũ"
        assert "ten" in cot, f"{bang}: chỉ gỡ một cột, không được dựng lại bảng mất cột khác"


def test_0274_chay_lai_va_giay_van_giu_o_cong_thuc():
    engine = _engine()
    with engine.begin() as cn:
        cn.execute(text("CREATE TABLE may_thiet_bi (id INTEGER PRIMARY KEY, cong_thuc_luong TEXT)"))
        # Giấy CỐ Ý giữ ô công thức: định mức giấy là của chính loại giấy, không đổi theo công đoạn.
        cn.execute(text("CREATE TABLE giay_nguyen (id INTEGER PRIMARY KEY, cong_thuc_luong TEXT)"))

    _chay(engine, _migrate_go_ba_o_cong_thuc_luong)
    _chay(engine, _migrate_go_ba_o_cong_thuc_luong)  # idempotent

    insp = inspect(engine)
    assert "cong_thuc_luong" not in {c["name"] for c in insp.get_columns("may_thiet_bi")}
    assert "cong_thuc_luong" in {c["name"] for c in insp.get_columns("giay_nguyen")}
