"""Migration 0278 — gỡ ô định khoản riêng của module Tài sản & CCDC.

Cột `ghi_chu_hach_toan` nằm ở BA bảng (`tai_san`, `tai_san_bien_dong`, `tai_san_khau_hao`) và
phải rơi hết. Cột `tai_san.ghi_chu` ở ngay cạnh, cùng kiểu `TEXT`, cùng chữ "ghi_chu" ở đầu tên —
xoá nhầm nó là mất luôn ô ghi chú duy nhất còn lại của module, nên có hẳn một phép kiểm cho việc
đó cùng nội dung dòng dữ liệu.

Idempotent: DB fresh (`create_all` dựng theo model đã bỏ cột) và DB đã xoá rồi đều là no-op.
"""
from __future__ import annotations

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session

from app.db_migrations import _migrate_go_ghi_chu_hach_toan_tai_san

BANG = ("tai_san", "tai_san_bien_dong", "tai_san_khau_hao")


def _fixture(*, con_cot: bool):
    engine = create_engine("sqlite+pysqlite:///:memory:")
    cot = "ghi_chu_hach_toan TEXT, " if con_cot else ""
    ten = "ghi_chu_hach_toan, " if con_cot else ""
    gt = "'211 / 6274 - to In', " if con_cot else ""
    with engine.begin() as cn:
        cn.execute(text(
            "CREATE TABLE tai_san (id INTEGER PRIMARY KEY, ma VARCHAR(20), "
            f"{cot}ghi_chu TEXT, nguyen_gia BIGINT NOT NULL DEFAULT 0)"
        ))
        cn.execute(text(
            f"INSERT INTO tai_san (id, ma, {ten}ghi_chu, nguyen_gia) "
            f"VALUES (1, 'TS-0001', {gt}'May chay tot', 3300000000)"
        ))
        cn.execute(text(
            "CREATE TABLE tai_san_bien_dong (id INTEGER PRIMARY KEY, tai_san_id INTEGER, "
            f"loai VARCHAR(16), ly_do VARCHAR(255), {cot}nguoi_tao_id INTEGER)"
        ))
        cn.execute(text(
            f"INSERT INTO tai_san_bien_dong (id, tai_san_id, loai, ly_do, {ten}nguoi_tao_id) "
            f"VALUES (1, 1, 'ghi_giam', 'Nhuong ban', {gt}NULL)"
        ))
        cn.execute(text(
            "CREATE TABLE tai_san_khau_hao (id INTEGER PRIMARY KEY, tai_san_id INTEGER, "
            f"ky_nam INTEGER, ky_thang INTEGER, muc_trich BIGINT, {cot}bo_phan_id INTEGER)"
        ))
        cn.execute(text(
            "INSERT INTO tai_san_khau_hao "
            f"(id, tai_san_id, ky_nam, ky_thang, muc_trich, {ten}bo_phan_id) "
            f"VALUES (1, 1, 2026, 3, 19516129, {gt}NULL)"
        ))
    return engine


def _chay(engine) -> None:
    with Session(engine) as db:
        _migrate_go_ghi_chu_hach_toan_tai_san(db)


def _cot(engine, bang: str) -> set[str]:
    return {c["name"] for c in inspect(engine).get_columns(bang)}


def test_xoa_cot_o_ca_ba_bang():
    engine = _fixture(con_cot=True)
    assert all("ghi_chu_hach_toan" in _cot(engine, b) for b in BANG)

    _chay(engine)

    assert all("ghi_chu_hach_toan" not in _cot(engine, b) for b in BANG)


def test_giu_nguyen_o_ghi_chu_va_du_lieu_con_lai():
    engine = _fixture(con_cot=True)
    _chay(engine)

    assert "ghi_chu" in _cot(engine, "tai_san")
    with engine.begin() as cn:
        assert cn.execute(text(
            "SELECT ma, ghi_chu, nguyen_gia FROM tai_san WHERE id = 1"
        )).one() == ("TS-0001", "May chay tot", 3300000000)
        assert cn.execute(text(
            "SELECT loai, ly_do FROM tai_san_bien_dong WHERE id = 1"
        )).one() == ("ghi_giam", "Nhuong ban")
        assert cn.execute(text(
            "SELECT muc_trich FROM tai_san_khau_hao WHERE id = 1"
        )).scalar() == 19_516_129


def test_chay_lai_khong_nem():
    engine = _fixture(con_cot=True)
    _chay(engine)
    _chay(engine)                      # idempotent
    assert all("ghi_chu_hach_toan" not in _cot(engine, b) for b in BANG)


def test_db_fresh_khong_co_cot_thi_bo_qua():
    engine = _fixture(con_cot=False)
    _chay(engine)
    assert "ghi_chu" in _cot(engine, "tai_san")


def test_db_trang_chua_co_bang_thi_bo_qua():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    _chay(engine)
    assert set(inspect(engine).get_table_names()) == set()
