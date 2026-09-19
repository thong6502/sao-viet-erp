"""mg `0324`: gỡ "Công thức sản lượng ra" của Công đoạn — ba cột + lịch sử công thức của nó.

Thứ đáng canh: (1) drop đúng ba cột, cột khác của `cong_doan` còn nguyên dữ liệu; (2) lịch sử công
thức chỉ xoá dòng của `cong_doan.cong_thuc_san_luong`, lịch sử của Giấy vẫn còn; (3) chạy lại lần
hai không nổ (DB đã gỡ rồi, hoặc DB trắng vốn không có cột).

Khuôn lấy từ `test_migration_0286_so_tp_ve_so_con.py`.
"""
from __future__ import annotations

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session

from app.db_migrations import MIGRATIONS, _migrate_go_cong_thuc_san_luong


def _engine():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    with engine.begin() as cn:
        cn.execute(text(
            "CREATE TABLE cong_doan (id INTEGER PRIMARY KEY, ma TEXT, cong_thuc_gia TEXT, "
            "cong_thuc_san_luong TEXT, don_vi_san_luong TEXT, he_so_ngoai_dong REAL)"
        ))
        cn.execute(text(
            "INSERT INTO cong_doan VALUES (1, 'CD-CTP', 'so_kem * don_gia', 'so_kem', 'kem', 1)"
        ))
        cn.execute(text(
            "CREATE TABLE cong_thuc_lich_su (id INTEGER PRIMARY KEY, bang TEXT, row_id INTEGER, "
            "truong TEXT, gia_tri TEXT)"
        ))
        cn.execute(text(
            "INSERT INTO cong_thuc_lich_su (bang, row_id, truong, gia_tri) VALUES "
            "('cong_doan', 1, 'cong_thuc_san_luong', 'so_kem'), "
            "('giay_nguyen', 7, 'cong_thuc_luong', 'dinh_luong * to_nguyen')"
        ))
    return engine


def _chay(engine) -> None:
    with Session(engine) as db:
        _migrate_go_cong_thuc_san_luong(db)


def test_drop_ba_cot_giu_cot_khac():
    engine = _engine()
    _chay(engine)
    cots = {c["name"] for c in inspect(engine).get_columns("cong_doan")}
    assert not cots & {"cong_thuc_san_luong", "don_vi_san_luong", "he_so_ngoai_dong"}
    with engine.connect() as cn:
        assert cn.execute(text("SELECT ma, cong_thuc_gia FROM cong_doan")).one() == (
            "CD-CTP", "so_kem * don_gia")


def test_chi_xoa_lich_su_cua_cong_thuc_san_luong():
    engine = _engine()
    _chay(engine)
    with engine.connect() as cn:
        con = cn.execute(text("SELECT bang, truong FROM cong_thuc_lich_su")).all()
    assert con == [("giay_nguyen", "cong_thuc_luong")]


def test_chay_lai_khong_no():
    engine = _engine()
    _chay(engine)
    _chay(engine)
    trang = create_engine("sqlite+pysqlite:///:memory:")   # DB chưa có bảng nào
    _chay(trang)


def test_da_dang_ky():
    assert ("0324_go_cong_thuc_san_luong", _migrate_go_cong_thuc_san_luong) in MIGRATIONS
