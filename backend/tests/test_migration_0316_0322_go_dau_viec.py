"""Migration 0316 → 0322 (spec 2026-09-18): gỡ đầu việc định mức, mẻ ghi theo công việc khoán.

Chạy trên DB đã có bảng/cột cũ (mô phỏng DB dev đang sống): `create_all` không bao giờ tạo lại thứ
đã xoá khỏi model nên test trên DB trắng chứng minh được rất ít. Thứ tự ràng buộc DUY NHẤT của đợt:
0316 + 0317 CHÉP dữ liệu ra khỏi hai bảng đầu việc TRƯỚC khi 0320 xoá chúng.
"""
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session

from app.db_migrations import MIGRATIONS


def _chay(db: Session, *ids: str) -> None:
    fns = dict(MIGRATIONS)
    for mid in ids:
        fns[mid](db)


def _bang(db: Session) -> set[str]:
    return set(inspect(db.get_bind()).get_table_names())


def _cot(db: Session, bang: str) -> set[str]:
    return {c["name"] for c in inspect(db.get_bind()).get_columns(bang)}


def _dung_db_cu(db: Session) -> None:
    for ddl in (
        "CREATE TABLE cong_doan (id INTEGER PRIMARY KEY, ten VARCHAR(100))",
        "CREATE TABLE piece_rates (id INTEGER PRIMARY KEY, ten VARCHAR(150))",
        "CREATE TABLE cong_doan_dau_viec (id INTEGER PRIMARY KEY, cong_doan_id INTEGER,"
        " piece_rate_id INTEGER, cong_thuc_khoan TEXT)",
        "CREATE TABLE cong_doan_dau_viec_vat_tu (id INTEGER PRIMARY KEY,"
        " cong_doan_dau_viec_id INTEGER, vat_tu_id INTEGER, thu_tu INTEGER,"
        " cong_thuc_luong TEXT)",
        # Bảng đích MỚI — `create_all` đã dựng trước khi runner chạy.
        "CREATE TABLE cong_doan_vat_tu (id INTEGER PRIMARY KEY, cong_doan_id INTEGER,"
        " vat_tu_id INTEGER, thu_tu INTEGER, cong_thuc_luong TEXT,"
        " UNIQUE(cong_doan_id, vat_tu_id))",
    ):
        db.execute(text(ddl))
    db.execute(text("INSERT INTO cong_doan VALUES (1, 'Ghi kẽm CTP'), (2, 'In offset')"))
    db.execute(text("INSERT INTO piece_rates VALUES (10, 'Bình bài'), (11, 'Ra kẽm'), (12, 'In')"))
    # Công đoạn 1 có HAI đầu việc cùng khai kẽm → về MỘT dòng; dòng có công thức thắng dòng trống.
    db.execute(text(
        "INSERT INTO cong_doan_dau_viec VALUES (100, 1, 10, 'so_mau'), (101, 1, 11, NULL),"
        " (102, 2, 12, 'so_to')"
    ))
    db.execute(text(
        "INSERT INTO cong_doan_dau_viec_vat_tu VALUES"
        " (1, 100, 7, 0, NULL), (2, 101, 7, 1, 'so_mau * 1.02'), (3, 101, 8, 2, 'so_mau'),"
        " (4, 102, 9, 0, 'so_to * 0.001')"
    ))
    db.commit()


def test_0316_0317_chep_roi_0320_moi_xoa():
    eng = create_engine("sqlite://")
    with Session(eng) as db:
        _dung_db_cu(db)
        _chay(db, "0316_cong_doan_vat_tu", "0317_piece_rates_cong_thuc_khoan")

        vt = db.execute(text(
            "SELECT cong_doan_id, vat_tu_id, thu_tu, cong_thuc_luong FROM cong_doan_vat_tu "
            "ORDER BY cong_doan_id, vat_tu_id")).all()
        assert [tuple(r) for r in vt] == [
            (1, 7, 0, "so_mau * 1.02"), (1, 8, 2, "so_mau"), (2, 9, 0, "so_to * 0.001")]
        ct = dict(db.execute(text("SELECT id, cong_thuc_khoan FROM piece_rates")).all())
        assert ct == {10: "so_mau", 11: None, 12: "so_to"}

        # Người khai đã tự gõ ở tab mới trước khi migration chạy lại ⇒ không bị đè.
        db.execute(text("UPDATE piece_rates SET cong_thuc_khoan = 'tay' WHERE id = 10"))
        db.execute(text("UPDATE cong_doan_vat_tu SET cong_thuc_luong = 'tay' WHERE vat_tu_id = 9"))
        db.commit()
        _chay(db, "0316_cong_doan_vat_tu", "0317_piece_rates_cong_thuc_khoan")
        assert db.execute(text("SELECT COUNT(*) FROM cong_doan_vat_tu")).scalar_one() == 3
        assert db.execute(text(
            "SELECT cong_thuc_khoan FROM piece_rates WHERE id = 10")).scalar_one() == "tay"
        assert db.execute(text(
            "SELECT cong_thuc_luong FROM cong_doan_vat_tu WHERE vat_tu_id = 9")).scalar_one() == "tay"

        _chay(db, "0320_go_dau_viec_dinh_muc")
        assert not {"cong_doan_dau_viec", "cong_doan_dau_viec_vat_tu"} & _bang(db)
        assert db.execute(text("SELECT COUNT(*) FROM cong_doan_vat_tu")).scalar_one() == 3
        _chay(db, "0316_cong_doan_vat_tu", "0317_piece_rates_cong_thuc_khoan",
              "0320_go_dau_viec_dinh_muc")   # idempotent sau khi bảng nguồn đã đi


def test_0322_xoa_bon_bang_chia_va_ty_le_giu_phieu_ho_tro():
    eng = create_engine("sqlite://")
    with Session(eng) as db:
        for ddl in (
            "CREATE TABLE san_xuat_phan_bo (id INTEGER PRIMARY KEY)",
            "CREATE TABLE san_xuat_phan_bo_dong (id INTEGER PRIMARY KEY, phan_bo_id INTEGER)",
            "CREATE TABLE san_xuat_phan_bo_bu_tru (id INTEGER PRIMARY KEY, phan_bo_id INTEGER)",
            "CREATE TABLE san_xuat_phan_bo_loai_tru (id INTEGER PRIMARY KEY, phan_bo_id INTEGER)",
            "CREATE TABLE san_xuat_ho_tro (id INTEGER PRIMARY KEY, employee_id INTEGER,"
            " ty_le_phan_tram NUMERIC(5,2) NOT NULL DEFAULT 100)",
        ):
            db.execute(text(ddl))
        db.execute(text("INSERT INTO san_xuat_ho_tro (id, employee_id) VALUES (1, 5)"))
        db.commit()

        _chay(db, "0322_go_tang_chia_san_luong")

        assert not {"san_xuat_phan_bo", "san_xuat_phan_bo_dong", "san_xuat_phan_bo_bu_tru",
                    "san_xuat_phan_bo_loai_tru"} & _bang(db)
        assert _cot(db, "san_xuat_ho_tro") == {"id", "employee_id"}
        assert db.execute(text("SELECT employee_id FROM san_xuat_ho_tro")).scalar_one() == 5
        _chay(db, "0322_go_tang_chia_san_luong")   # idempotent


def test_0321_go_kip_va_dau_viec_o_buoc():
    eng = create_engine("sqlite://")
    with Session(eng) as db:
        db.execute(text(
            "CREATE TABLE lsx_cong_doan (id INTEGER PRIMARY KEY, ten VARCHAR(100),"
            " so_nhan_cong_tieu_chuan INTEGER, khoan_json TEXT, nang_suat NUMERIC(14,2),"
            " don_vi_nang_suat VARCHAR(24))"
        ))
        db.execute(text(
            "CREATE TABLE san_xuat_phien_chay (id INTEGER PRIMARY KEY, ly_do_so_nguoi TEXT)"))
        db.execute(text("INSERT INTO lsx_cong_doan (id, ten, so_nhan_cong_tieu_chuan) VALUES (1, 'In', 3)"))
        db.commit()

        _chay(db, "0321_go_kip_va_dau_viec_o_buoc")

        assert _cot(db, "lsx_cong_doan") == {"id", "ten"}
        assert _cot(db, "san_xuat_phien_chay") == {"id"}
        assert db.execute(text("SELECT ten FROM lsx_cong_doan")).scalar_one() == "In"


def test_db_trang_khong_no():
    eng = create_engine("sqlite://")
    with Session(eng) as db:
        _chay(db, "0316_cong_doan_vat_tu", "0317_piece_rates_cong_thuc_khoan",
              "0318_batch_viec_khoan", "0319_so_gio_ke_hoach", "0320_go_dau_viec_dinh_muc",
              "0321_go_kip_va_dau_viec_o_buoc", "0322_go_tang_chia_san_luong")


def test_model_khong_con_tang_dau_viec_va_chia():
    import app.models as m
    from app.models.lsx import LsxCongDoan
    from app.models.san_xuat_phan_bo import SanXuatHoTro

    for ten in ("CongDoanDauViec", "CongDoanDauViecVatTu", "SanXuatPhanBo", "SanXuatPhanBoDong",
                "SanXuatPhanBoBuTru", "SanXuatPhanBoLoaiTru"):
        assert not hasattr(m, ten), ten
    assert not {"so_nhan_cong_tieu_chuan", "khoan_json", "nang_suat", "don_vi_nang_suat"} \
        & set(LsxCongDoan.__table__.columns.keys())
    assert "so_gio_ke_hoach" in LsxCongDoan.__table__.columns
    assert "ty_le_phan_tram" not in SanXuatHoTro.__table__.columns
