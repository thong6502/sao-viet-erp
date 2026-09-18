"""Migration 0309 (thêm cột nhập kho thành phẩm qua Yêu cầu nhập xuất) + 0310 (gỡ sổ kho riêng SX).

Chạy trên bảng dựng tay mô phỏng DB dev đang sống — `create_all` đã có sẵn cột mới nên DB trắng
không chứng minh được gì.
"""
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session

from app.db_migrations import MIGRATIONS


def _chay(db: Session, ten: str) -> None:
    dict(MIGRATIONS)[ten](db)


def _cot(db: Session, bang: str) -> set[str]:
    return {c["name"] for c in inspect(db.get_bind()).get_columns(bang)}


def test_0309_them_cot_va_giu_du_lieu():
    with Session(create_engine("sqlite://")) as db:
        db.execute(text("CREATE TABLE stock_requests (id INTEGER PRIMARY KEY, ma VARCHAR(40))"))
        db.execute(text("CREATE TABLE stock_request_lines (id INTEGER PRIMARY KEY, don_gia BIGINT)"))
        db.execute(text("CREATE TABLE stock_lots (id INTEGER PRIMARY KEY, so_lo VARCHAR(40))"))
        db.execute(text("CREATE TABLE stock_voucher_lines (id INTEGER PRIMARY KEY, lot_id INTEGER)"))
        db.execute(text("INSERT INTO stock_request_lines (id, don_gia) VALUES (1, 700)"))
        db.commit()

        _chay(db, "0309_nhap_kho_thanh_pham_cot")

        assert "san_xuat_cong_viec_id" in _cot(db, "stock_requests")
        assert "don_gia_ban" in _cot(db, "stock_request_lines")
        assert "lo_goc_id" in _cot(db, "stock_lots")
        assert "lo_goc_id" in _cot(db, "stock_voucher_lines")
        # Dòng cũ: giá gốc giữ nguyên, giá bán + lô gốc trống (NULL = chính nó là lô gốc).
        assert db.execute(text("SELECT don_gia, don_gia_ban FROM stock_request_lines")).one() == (700, None)
        _chay(db, "0309_nhap_kho_thanh_pham_cot")   # idempotent


def test_0310_go_ba_bang_so_kho_san_xuat():
    with Session(create_engine("sqlite://")) as db:
        db.execute(text("CREATE TABLE san_xuat_kho_hang (id INTEGER PRIMARY KEY, ma VARCHAR(40))"))
        db.execute(text(
            "CREATE TABLE san_xuat_nhap_kho_yc (id INTEGER PRIMARY KEY,"
            " hang_id INTEGER REFERENCES san_xuat_kho_hang(id))"
        ))
        db.execute(text(
            "CREATE TABLE san_xuat_kho_lot (id INTEGER PRIMARY KEY,"
            " hang_id INTEGER REFERENCES san_xuat_kho_hang(id),"
            " yc_id INTEGER REFERENCES san_xuat_nhap_kho_yc(id))"
        ))
        db.execute(text("CREATE TABLE stock_requests (id INTEGER PRIMARY KEY)"))
        db.execute(text("INSERT INTO san_xuat_kho_hang (id, ma) VALUES (1, 'TP')"))
        db.execute(text("INSERT INTO san_xuat_nhap_kho_yc (id, hang_id) VALUES (1, 1)"))
        db.execute(text("INSERT INTO san_xuat_kho_lot (hang_id, yc_id) VALUES (1, 1)"))
        db.commit()

        _chay(db, "0310_go_so_kho_san_xuat")

        con = set(inspect(db.get_bind()).get_table_names())
        assert not {"san_xuat_kho_hang", "san_xuat_nhap_kho_yc", "san_xuat_kho_lot"} & con
        assert "stock_requests" in con
        _chay(db, "0310_go_so_kho_san_xuat")        # idempotent


def test_0310_db_trang_khong_no():
    with Session(create_engine("sqlite://")) as db:
        _chay(db, "0310_go_so_kho_san_xuat")
