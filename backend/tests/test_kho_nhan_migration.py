"""Migration 0204 — mồi kho nhãn khách (`customer_tag_catalog`).

Kiểm ở mức HÀM trên một SQLite rời, không qua fixture `db`: fixture đó chỉ `create_all` chứ không
chạy migration, nên không thấy được hạt mồi. Mà thứ đáng kiểm nhất ở đây lại chính là cái GUARD —
"chỉ mồi khi bảng RỖNG HOÀN TOÀN".

Vì sao guard đó quan trọng: yêu cầu của chủ dự án là XOÁ ĐƯỢC nhãn. Nếu seeder kiểm theo từng nhãn
("thiếu nhãn nào thêm nhãn đó") thì lần khởi động sau nó mọc lại đúng nhãn vừa xoá — người dùng xoá
xong tưởng xong, restart một phát nó về. Đó đúng là bệnh của bản viết cứng cũ, chỉ đổi chỗ nấp.
"""
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db_migrations import NHAN_KHACH_MOI, _migrate_kho_nhan_khach


def _db(tao_bang: bool = True):
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    db = sessionmaker(bind=eng)()
    if tao_bang:
        db.execute(text(
            "CREATE TABLE customer_tag_catalog ("
            " id INTEGER PRIMARY KEY AUTOINCREMENT,"
            " label VARCHAR(50) NOT NULL UNIQUE,"
            " created_by INTEGER,"
            " created_at TIMESTAMP NOT NULL)"
        ))
        db.commit()
    return db


def _nhan(db) -> set[str]:
    return {r for (r,) in db.execute(text("SELECT label FROM customer_tag_catalog")).all()}


def test_moi_du_13_nhan_cua_ban_viet_cung_cu():
    db = _db()
    _migrate_kho_nhan_khach(db)
    assert _nhan(db) == set(NHAN_KHACH_MOI)
    assert len(NHAN_KHACH_MOI) == 13
    # Ba nhãn có mặt trong ảnh chụp màn hình chủ dự án gửi — mở lên không được mất.
    assert {"VIP", "Nhạy giá", "Khó tính"} <= _nhan(db)


def test_chay_lai_khong_de_them_dong():
    db = _db()
    _migrate_kho_nhan_khach(db)
    _migrate_kho_nhan_khach(db)
    assert db.execute(text("SELECT count(*) FROM customer_tag_catalog")).scalar() == 13


def test_KHONG_moc_lai_nhan_vua_bi_xoa():
    """Chốt chặn của cả tính năng: xoá rồi restart thì nhãn phải Ở YÊN dưới mồ."""
    db = _db()
    _migrate_kho_nhan_khach(db)
    db.execute(text("DELETE FROM customer_tag_catalog WHERE label = 'Khó tính'"))
    db.commit()

    _migrate_kho_nhan_khach(db)          # khởi động lại

    assert "Khó tính" not in _nhan(db), "seeder mọc lại nhãn đã xoá — xoá thành vô nghĩa"
    assert len(_nhan(db)) == 12


def test_bang_chua_ton_tai_thi_bo_qua_khong_no():
    """DB cũ chưa có bảng (create_all chưa chạy) → im lặng đi qua, không dựng ngược migration."""
    _migrate_kho_nhan_khach(_db(tao_bang=False))
