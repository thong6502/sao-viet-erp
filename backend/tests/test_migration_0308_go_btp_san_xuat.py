"""Migration 0308: gỡ hẳn bán thành phẩm (BTP) khỏi kho sản xuất và lot đầu vào.

Chạy trên DB còn cột cũ (mô phỏng DB dev đang sống) — `create_all` không tạo lại cột đã xoá khỏi
model nên DB trắng chứng minh được rất ít.
"""
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session

from app.db_migrations import MIGRATIONS


def _chay(db: Session) -> None:
    dict(MIGRATIONS)["0308_go_btp_san_xuat"](db)


def _cot(db: Session, bang: str) -> set[str]:
    return {c["name"] for c in inspect(db.get_bind()).get_columns(bang)}


def _dung_bang_cu(db: Session) -> None:
    db.execute(text(
        "CREATE TABLE san_xuat_kho_hang (id INTEGER PRIMARY KEY, ma VARCHAR(40),"
        " loai_hang VARCHAR(16) NOT NULL DEFAULT 'thanh_pham', order_id INTEGER, nhom_id INTEGER,"
        " lsx_id INTEGER, cong_doan_ref_id INTEGER, ten VARCHAR(255))"
    ))
    db.execute(text("CREATE INDEX ix_san_xuat_kho_hang_lsx_id ON san_xuat_kho_hang (lsx_id)"))
    db.execute(text(
        "CREATE TABLE san_xuat_nhap_kho_yc (id INTEGER PRIMARY KEY, hang_id INTEGER)"
    ))
    db.execute(text(
        "CREATE TABLE san_xuat_kho_lot (id INTEGER PRIMARY KEY, hang_id INTEGER,"
        " loai_hang VARCHAR(16) NOT NULL DEFAULT 'thanh_pham', order_id INTEGER, lsx_id INTEGER,"
        " cong_doan_ref_id INTEGER, nguon_batch_id INTEGER, phan_loai VARCHAR(16),"
        " so_luong NUMERIC(14,3))"
    ))
    db.execute(text("CREATE INDEX ix_san_xuat_kho_lot_phan_loai ON san_xuat_kho_lot (phan_loai)"))
    db.execute(text(
        "CREATE TABLE san_xuat_batch_lot_vao (id INTEGER PRIMARY KEY, batch_id INTEGER,"
        " nguon_loai VARCHAR(16) NOT NULL DEFAULT 'batch', nguon_batch_id INTEGER,"
        " nguon_lot_id INTEGER, so_luong NUMERIC(14,3))"
    ))
    db.execute(text("CREATE INDEX ix_san_xuat_batch_lot_vao_nguon_lot_id ON san_xuat_batch_lot_vao (nguon_lot_id)"))


def test_0308_xoa_dong_btp_roi_bo_cot():
    eng = create_engine("sqlite://")
    with Session(eng) as db:
        _dung_bang_cu(db)
        db.execute(text("INSERT INTO san_xuat_kho_hang (id, ma, loai_hang) VALUES (1, 'TP', 'thanh_pham')"))
        db.execute(text("INSERT INTO san_xuat_kho_hang (id, ma, loai_hang) VALUES (2, 'BTP', 'btp')"))
        db.execute(text(
            "INSERT INTO san_xuat_kho_lot (hang_id, loai_hang, so_luong) VALUES (1, 'thanh_pham', 20)"
        ))
        db.execute(text(
            "INSERT INTO san_xuat_kho_lot (hang_id, loai_hang, phan_loai, so_luong)"
            " VALUES (2, 'btp', 'nhap_btp', 5)"
        ))
        db.execute(text("INSERT INTO san_xuat_batch_lot_vao (nguon_loai, nguon_batch_id, so_luong) VALUES ('batch', 7, 60)"))
        db.execute(text("INSERT INTO san_xuat_batch_lot_vao (nguon_loai, nguon_lot_id, so_luong) VALUES ('kho_lot', 3, 9)"))
        db.commit()

        _chay(db)

        assert _cot(db, "san_xuat_kho_hang") == {"id", "ma", "order_id", "nhom_id", "ten"}
        assert _cot(db, "san_xuat_kho_lot") == {"id", "hang_id", "order_id", "so_luong"}
        assert _cot(db, "san_xuat_batch_lot_vao") == {"id", "batch_id", "nguon_batch_id", "so_luong"}
        # Dòng BTP bị xoá TRƯỚC khi mất cột phân biệt — không thành thành phẩm giả.
        assert db.execute(text("SELECT ma FROM san_xuat_kho_hang")).scalars().all() == ["TP"]
        assert db.execute(text("SELECT so_luong FROM san_xuat_kho_lot")).scalars().all() == [20]
        assert db.execute(text("SELECT nguon_batch_id FROM san_xuat_batch_lot_vao")).scalars().all() == [7]
        _chay(db)   # idempotent


def test_0308_giu_hang_btp_con_lot_hoac_yeu_cau():
    """Hàng `btp` còn yêu cầu nhập kho trỏ tới thì không xoá (FK) — chỉ mất cột phân loại."""
    with Session(create_engine("sqlite://")) as db:
        _dung_bang_cu(db)
        db.execute(text("INSERT INTO san_xuat_kho_hang (id, ma, loai_hang) VALUES (2, 'BTP', 'btp')"))
        db.execute(text("INSERT INTO san_xuat_nhap_kho_yc (hang_id) VALUES (2)"))
        db.commit()
        _chay(db)
        assert db.execute(text("SELECT ma FROM san_xuat_kho_hang")).scalars().all() == ["BTP"]


def test_0308_db_trang_khong_no():
    with Session(create_engine("sqlite://")) as db:
        _chay(db)


def test_model_va_schema_khong_con_btp():
    # Sổ kho riêng của sản xuất (`app.models.san_xuat_kho`) đã gỡ hẳn ở mg 0310 — chỉ còn soi lot đầu vào.
    import app.models.san_xuat_san_luong as ms
    from app.models.san_xuat_san_luong import SanXuatBatchLotVao
    from app.schemas.san_xuat import BanGiaoDeXuatIn, LotVaoIn, LotVaoOut

    assert not any(hasattr(ms, x) for x in ("LOT_TU_BATCH", "LOT_TU_KHO", "NGUON_LOT"))
    assert not {"nguon_loai", "nguon_lot_id"} & set(SanXuatBatchLotVao.__table__.columns.keys())
    assert not {"nguon_loai", "nguon_lot_id"} & (set(LotVaoIn.model_fields) | set(LotVaoOut.model_fields))
    assert BanGiaoDeXuatIn.model_fields["dich_cong_viec_id"].is_required()
