"""Migration 0296/0297: sản xuất thôi giữ TIỀN — bỏ 3 cột `don_gia` + bảng thưởng tổ trưởng.

Chạy migration trên một DB đã có cột/bảng cũ (mô phỏng DB dev đang sống), không phải trên DB
trắng do `create_all` dựng — `create_all` không bao giờ tạo cột đã xoá khỏi model nên test trên DB
trắng chứng minh được rất ít.
"""
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session

from app.db_migrations import MIGRATIONS


def _chay(ten_tien_to: str, db: Session) -> None:
    for ten, fn in MIGRATIONS:
        if ten.startswith(ten_tien_to):
            fn(db)
            return
    raise AssertionError(f"Không thấy migration {ten_tien_to} trong MIGRATIONS")


def test_0296_bo_cot_don_gia_cua_ba_bang_phan_bo():
    eng = create_engine("sqlite://")
    with Session(eng) as db:
        for bang in ("san_xuat_phan_bo", "san_xuat_phan_bo_dong", "san_xuat_phan_bo_bu_tru"):
            db.execute(text(
                f"CREATE TABLE {bang} (id INTEGER PRIMARY KEY,"
                " don_gia NUMERIC(18,4) NOT NULL DEFAULT 0)"
            ))
        db.commit()
        _chay("0296_", db)
        insp = inspect(db.get_bind())
        for bang in ("san_xuat_phan_bo", "san_xuat_phan_bo_dong", "san_xuat_phan_bo_bu_tru"):
            assert "don_gia" not in {c["name"] for c in insp.get_columns(bang)}


def test_0296_chay_lai_khong_no():
    eng = create_engine("sqlite://")
    with Session(eng) as db:
        db.execute(text("CREATE TABLE san_xuat_phan_bo (id INTEGER PRIMARY KEY)"))
        db.commit()
        # Bảng thiếu cột + hai bảng kia chưa tồn tại ⇒ vẫn phải im lặng đi qua.
        _chay("0296_", db)
        _chay("0296_", db)


def test_0297_bo_bang_thuong_to_truong():
    eng = create_engine("sqlite://")
    with Session(eng) as db:
        db.execute(text("CREATE TABLE san_xuat_thuong_to_truong (id INTEGER PRIMARY KEY)"))
        db.commit()
        _chay("0297_", db)
        assert "san_xuat_thuong_to_truong" not in set(inspect(db.get_bind()).get_table_names())
        _chay("0297_", db)   # idempotent


def test_model_khong_con_cot_don_gia():
    from app.models.san_xuat_phan_bo import (
        SanXuatPhanBo,
        SanXuatPhanBoBuTru,
        SanXuatPhanBoDong,
    )

    for model in (SanXuatPhanBo, SanXuatPhanBoDong, SanXuatPhanBoBuTru):
        assert "don_gia" not in model.__table__.columns, model.__tablename__


def test_model_thuong_to_truong_da_go():
    import app.models as m

    assert not hasattr(m, "SanXuatThuongToTruong")
