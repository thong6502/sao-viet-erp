"""Migration 0206 — đoán `khuon_be.loai` từ TÊN dao cho các dòng khai trước mg 0205.

Sinh ra từ một lỗi HỎNG CÂM: bản đầu viết backfill này trong `0205`, gác bằng inspector tạo TRƯỚC
vòng `ALTER TABLE`. `Inspector` cache reflection nên guard luôn ra False ⇒ cả khối bị bỏ qua, không
lỗi, không log, migration vẫn ghi "đã chạy". Đo trên DB dev: 6/6 dòng còn NULL.

Test cuối cùng trong file dựng lại ĐÚNG cái bẫy đó — nó là lý do file này tồn tại.
"""
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db_migrations import _existing_columns, _migrate_doan_loai_khuon


def _db(co_cot_loai: bool = True):
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    db = sessionmaker(bind=eng)()
    cot_loai = ", loai VARCHAR(16)" if co_cot_loai else ""
    db.execute(text(
        f"CREATE TABLE khuon_be (id INTEGER PRIMARY KEY AUTOINCREMENT, ten TEXT NOT NULL{cot_loai})"
    ))
    db.commit()
    return db


def _them(db, *tens: str) -> None:
    for t in tens:
        db.execute(text("INSERT INTO khuon_be (ten) VALUES (:t)"), {"t": t})
    db.commit()


def _loai(db) -> dict[str, str | None]:
    return {ten: loai for ten, loai in db.execute(text("SELECT ten, loai FROM khuon_be")).all()}


def test_doan_dung_theo_ten():
    db = _db()
    _them(db, "Khuôn bế hộp bánh Trung thu", "Khuôn ép nhũ vàng bìa sách",
          "Khuôn bế tem decal tròn Ø40")
    _migrate_doan_loai_khuon(db)
    assert _loai(db) == {
        "Khuôn bế hộp bánh Trung thu": "khuon_be",
        "Khuôn ép nhũ vàng bìa sách": "khuon_ep",
        "Khuôn bế tem decal tròn Ø40": "khuon_be",
    }


def test_ten_KHONG_noi_ro_thi_de_TRONG_chu_khong_doan_bua():
    """Đoán bừa "không ép thì là bế" sai với dao dập nổi / dao cắt — mà đoán sai thì ô chọn dao
    LỌC MẤT con dao đúng. Để trống thì nó vẫn hiện ở mọi loại bước, tệ hơn nhưng không giấu."""
    db = _db()
    _them(db, "Dao dập nổi logo", "Khuôn cắt góc tròn", "KB cũ chưa đặt tên rõ")
    _migrate_doan_loai_khuon(db)
    assert set(_loai(db).values()) == {None}


def test_KHONG_de_len_dong_da_co_loai():
    """Người dùng đã tự phân loại thì migration không được ghi đè — kể cả khi tên nói khác."""
    db = _db()
    _them(db, "Khuôn bế hộp Ivory")
    db.execute(text("UPDATE khuon_be SET loai = 'khuon_ep'"))
    db.commit()
    _migrate_doan_loai_khuon(db)
    assert _loai(db) == {"Khuôn bế hộp Ivory": "khuon_ep"}


def test_chay_lai_khong_doi_gi():
    db = _db()
    _them(db, "Khuôn bế thùng carton")
    _migrate_doan_loai_khuon(db)
    truoc = _loai(db)
    _migrate_doan_loai_khuon(db)
    assert _loai(db) == truoc


def test_chua_co_cot_loai_thi_bo_qua_khong_no():
    """DB chưa chạy mg 0205 (cột `loai` chưa có) → im lặng đi qua."""
    _migrate_doan_loai_khuon(_db(co_cot_loai=False))


def test_BAY_inspector_cache_dung_cai_da_giet_backfill_o_0205():
    """Ghim CÁI BẪY, không phải ghim migration.

    `Inspector` cache kết quả reflection: cái tạo TRƯỚC `ALTER TABLE ADD COLUMN` sẽ mãi mãi báo
    danh sách cột CŨ. Mọi guard kiểu `if "cot_moi" in _existing_columns(insp, ...)` viết sau một
    ALTER trong CÙNG hàm đều sai — và sai một cách im lặng.

    Ai định gộp backfill trở lại vào hàm có ALTER thì đọc test này trước.
    """
    db = _db(co_cot_loai=False)
    insp_cu = inspect(db.get_bind())
    assert "loai" not in _existing_columns(insp_cu, "khuon_be")

    db.execute(text("ALTER TABLE khuon_be ADD COLUMN loai VARCHAR(16)"))
    db.commit()

    # Inspector CŨ vẫn không thấy cột mới…
    assert "loai" not in _existing_columns(insp_cu, "khuon_be"), \
        "Inspector hết cache rồi? Nếu vậy đọc lại chú thích mg 0206 — nền tảng đã đổi."
    # …trong khi inspector MỚI thấy ngay.
    assert "loai" in _existing_columns(inspect(db.get_bind()), "khuon_be")
