"""Migration 0281 — bỏ kỳ chốt khấu hao tài sản, dựng mốc cho tài sản đã có trên DB.

Ba bảng kỳ (`tai_san_ky_log`, `tai_san_khau_hao`, `tai_san_ky`) rơi, cột `tai_san.hao_mon_luy_ke`
rơi; mỗi tài sản chưa có mốc nào được một mốc từ bộ ba đang nằm trên `tai_san` với lũy kế đầu =
nguyên giá − còn phải trích (đúng cho cả mua mới lẫn nạp đầu kỳ).

Idempotent: chạy lại không nhân đôi mốc; DB fresh (`create_all` theo model mới) không có gì để gỡ.
"""
from __future__ import annotations

import sqlite3

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session

from app.db_migrations import _migrate_bo_ky_khau_hao_tai_san

SQLITE_BIET_DROP_COLUMN = sqlite3.sqlite_version_info >= (3, 35, 0)


def _fixture(*, cu: bool):
    engine = create_engine("sqlite+pysqlite:///:memory:")
    cot_luy_ke = "hao_mon_luy_ke BIGINT NOT NULL DEFAULT 0, " if cu else ""
    with engine.begin() as cn:
        cn.execute(text(
            "CREATE TABLE tai_san (id INTEGER PRIMARY KEY, ma VARCHAR(32), "
            "nguyen_gia BIGINT NOT NULL DEFAULT 0, co_so_trich BIGINT NOT NULL DEFAULT 0, "
            "so_thang_con INTEGER NOT NULL DEFAULT 0, moc_tu_ngay DATE NOT NULL, "
            f"{cot_luy_ke}nguon_vao VARCHAR(8) NOT NULL DEFAULT 'ghi_tang', "
            "hao_mon_dau_ky BIGINT NOT NULL DEFAULT 0)"
        ))
        # `create_all` chạy TRƯỚC migration nên tới lúc này bảng mốc đã có sẵn (rỗng).
        cn.execute(text(
            "CREATE TABLE tai_san_moc (id INTEGER PRIMARY KEY, tai_san_id INTEGER NOT NULL, "
            "tu_ngay DATE NOT NULL, nguyen_gia BIGINT NOT NULL DEFAULT 0, "
            "co_so_trich BIGINT NOT NULL DEFAULT 0, so_thang_con INTEGER NOT NULL DEFAULT 0, "
            "luy_ke_dau BIGINT NOT NULL DEFAULT 0, nguon VARCHAR(16) NOT NULL, "
            "created_at DATETIME NOT NULL)"
        ))
        # Komori mua mới (mốc = ngày sử dụng) · Polar nạp đầu kỳ (mang sang 116,25tr).
        cn.execute(text(
            "INSERT INTO tai_san (id, ma, nguyen_gia, co_so_trich, so_thang_con, moc_tu_ngay, "
            "nguon_vao, hao_mon_dau_ky) VALUES "
            "(1, 'TS-0001', 3300000000, 3300000000, 120, '2026-03-10', 'ghi_tang', 0), "
            "(2, 'TS-0002', 450000000, 333750000, 89, '2026-01-01', 'dau_ky', 116250000)"
        ))
        if cu:
            cn.execute(text(
                "CREATE TABLE tai_san_khau_hao (id INTEGER PRIMARY KEY, tai_san_id INTEGER, "
                "ky_nam INTEGER, ky_thang INTEGER, muc_trich BIGINT)"
            ))
            cn.execute(text(
                "CREATE TABLE tai_san_ky (id INTEGER PRIMARY KEY, ky_nam INTEGER, "
                "ky_thang INTEGER, trang_thai VARCHAR(8))"
            ))
            cn.execute(text(
                "CREATE TABLE tai_san_ky_log (id INTEGER PRIMARY KEY, ky_nam INTEGER, "
                "ky_thang INTEGER, hanh_dong VARCHAR(8))"
            ))
    return engine


def _chay(engine) -> None:
    with Session(engine) as db:
        _migrate_bo_ky_khau_hao_tai_san(db)


def _bang(engine) -> set[str]:
    return set(inspect(engine).get_table_names())


def _cot(engine, bang: str) -> set[str]:
    return {c["name"] for c in inspect(engine).get_columns(bang)}


def _moc(engine) -> list[tuple]:
    with engine.begin() as cn:
        return list(cn.execute(text(
            "SELECT tai_san_id, tu_ngay, nguyen_gia, co_so_trich, so_thang_con, luy_ke_dau, nguon "
            "FROM tai_san_moc ORDER BY tai_san_id"
        )))


def test_dung_moc_tu_bo_ba_tren_tai_san():
    engine = _fixture(cu=True)
    _chay(engine)
    assert _moc(engine) == [
        (1, "2026-03-10", 3300000000, 3300000000, 120, 0, "ghi_tang"),
        (2, "2026-01-01", 450000000, 333750000, 89, 116250000, "dau_ky"),
    ]


def test_go_ba_bang_ky_va_cot_luy_ke():
    engine = _fixture(cu=True)
    assert {"tai_san_khau_hao", "tai_san_ky", "tai_san_ky_log"} <= _bang(engine)
    _chay(engine)
    assert not ({"tai_san_khau_hao", "tai_san_ky", "tai_san_ky_log"} & _bang(engine))
    if SQLITE_BIET_DROP_COLUMN:
        assert "hao_mon_luy_ke" not in _cot(engine, "tai_san")
    assert {"ma", "nguyen_gia", "co_so_trich", "hao_mon_dau_ky"} <= _cot(engine, "tai_san")


def test_chay_lai_khong_nhan_doi_moc():
    engine = _fixture(cu=True)
    _chay(engine)
    _chay(engine)
    assert len(_moc(engine)) == 2


def test_db_fresh_van_dung_moc_cho_tai_san_chua_co():
    engine = _fixture(cu=False)
    _chay(engine)
    assert len(_moc(engine)) == 2
    assert "hao_mon_dau_ky" in _cot(engine, "tai_san")


def test_db_trang_chua_co_bang_thi_bo_qua():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    _chay(engine)
    assert _bang(engine) == set()
