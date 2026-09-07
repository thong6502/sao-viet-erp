"""Migration 0268 — ba ô kích thước đổi chủ từ bước khung lụa sang bước khuôn ép nhũ.

Hai việc phải đúng, sai là mất dữ liệu người dùng đã khai:

  · đổi tên cột `phieu_thanh_pham.dai_khung_lua/rong_khung_lua/so_khung_lua` →
    `dai_khuon/rong_khuon/so_khuon` mà GIỮ NGUYÊN số đã nhập (RENAME chứ không ADD + DROP);
  · viết lại chuỗi công thức người dùng đã lưu — chip trong công thức là TÊN BIẾN, để nguyên là
    validator coi biến lạ rồi chặn ngay lần lưu sau.

Idempotent: DB fresh (`create_all` dựng thẳng tên mới) và DB đã đổi rồi đều phải là no-op.
"""
from __future__ import annotations

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session

from app.db_migrations import _migrate_doi_ten_ba_o_khuon

_CT = "dai_khung_lua * rong_khung_lua * so_khung_lua * 3000"
_CT_MOI = "dai_khuon * rong_khuon * so_khuon * 3000"


def _fixture(*, ten_moi: bool):
    """DB "cũ" chỉ dựng đúng phần migration đụng tới: bảng phiếu + một bảng có ô công thức."""
    engine = create_engine("sqlite+pysqlite:///:memory:")
    hau = "khuon" if ten_moi else "khung_lua"
    with engine.begin() as cn:
        cn.execute(text(
            "CREATE TABLE phieu_thanh_pham (id INTEGER PRIMARY KEY, thu_tu INTEGER, "
            "phi_khuon NUMERIC(18,2) NOT NULL DEFAULT 0, "
            f"dai_{hau} NUMERIC(10,2) NOT NULL DEFAULT 0, "
            f"rong_{hau} NUMERIC(10,2) NOT NULL DEFAULT 0, "
            f"so_{hau} INTEGER NOT NULL DEFAULT 0)"
        ))
        cn.execute(text(
            f"INSERT INTO phieu_thanh_pham (id, thu_tu, phi_khuon, dai_{hau}, rong_{hau}, so_{hau}) "
            "VALUES (1, 3, 250000, 50, 100, 2)"
        ))
        cn.execute(text(
            "CREATE TABLE cong_doan (id INTEGER PRIMARY KEY, ma VARCHAR(20), "
            "cong_thuc_gia TEXT, cong_thuc_san_luong VARCHAR(200))"
        ))
        cn.execute(text(
            "INSERT INTO cong_doan (id, ma, cong_thuc_gia, cong_thuc_san_luong) "
            "VALUES (1, 'CD-0003', :ct, NULL), (2, 'CD-0105', '120000 * so_khung_lua', NULL), "
            "       (3, 'CD-0009', 'sl_ra * 40', 'sl_vao / 2')"
        ), {"ct": _CT if not ten_moi else _CT_MOI})
    return engine


def _chay(engine) -> None:
    with Session(engine) as db:
        _migrate_doi_ten_ba_o_khuon(db)


def _cot(engine, bang: str = "phieu_thanh_pham") -> set[str]:
    return {c["name"] for c in inspect(engine).get_columns(bang)}


def test_doi_ten_cot_va_giu_nguyen_so_da_khai():
    engine = _fixture(ten_moi=False)
    assert "dai_khung_lua" in _cot(engine)

    _chay(engine)

    assert {"dai_khuon", "rong_khuon", "so_khuon"} <= _cot(engine)
    assert not {"dai_khung_lua", "rong_khung_lua", "so_khung_lua"} & _cot(engine)
    with engine.begin() as cn:
        r = cn.execute(text(
            "SELECT phi_khuon, dai_khuon, rong_khuon, so_khuon FROM phieu_thanh_pham WHERE id = 1"
        )).one()
    assert [float(x) for x in r] == [250000, 50, 100, 2]


def test_viet_lai_chip_trong_cong_thuc_da_luu():
    engine = _fixture(ten_moi=False)

    _chay(engine)

    with engine.begin() as cn:
        ct = dict(cn.execute(text("SELECT ma, cong_thuc_gia FROM cong_doan")).all())
    assert ct["CD-0003"] == _CT_MOI
    assert ct["CD-0105"] == "120000 * so_khuon"
    assert ct["CD-0009"] == "sl_ra * 40", "công thức không dính chip khuôn thì phải nguyên si"


def test_chay_lai_khong_nem():
    engine = _fixture(ten_moi=False)
    _chay(engine)
    _chay(engine)                      # idempotent
    assert {"dai_khuon", "rong_khuon", "so_khuon"} <= _cot(engine)
    with engine.begin() as cn:
        assert cn.execute(text(
            "SELECT cong_thuc_gia FROM cong_doan WHERE ma = 'CD-0003'"
        )).scalar() == _CT_MOI


def test_db_fresh_da_ten_moi_thi_bo_qua():
    """DB mới dựng bằng `create_all` (model đã khai tên mới) rồi mới chạy migration."""
    engine = _fixture(ten_moi=True)
    _chay(engine)
    assert {"dai_khuon", "rong_khuon", "so_khuon"} <= _cot(engine)


def test_db_trang_chua_co_bang_thi_bo_qua():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    _chay(engine)
    assert set(inspect(engine).get_table_names()) == set()
