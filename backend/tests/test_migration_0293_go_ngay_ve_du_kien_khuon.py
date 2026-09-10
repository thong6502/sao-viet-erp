"""Migration 0293 — gỡ "Ngày có khuôn (dự kiến)" (`khuon_be.ngay_ve_du_kien`).

Ô ngày CUỐI CÙNG của kho khuôn ra đi (mg `0207` đã gộp `ngay_lam_khuon` vào nó từ 16/08/2026).
Không phép tính nào đọc nó: cửa "Sẵn sàng lập kế hoạch" chỉ soi bước cần dao đã CHỌN dao chưa,
xếp lịch/phát hành không đọc, và điểm chặn thật của luật "bế phải có khuôn mới làm" là ô tổ tích
ĐÃ NHẬN KHUÔN ở bàn tổ. Nó chỉ là ràng buộc bắt người khai bịa một ngày rồi để đó lạc hậu.

Migration phải xoá được cột mà KHÔNG đụng `tinh_trang` nằm cạnh — chữ `dang_dat_lam` mới là thứ
mang tin "dao chưa trong tay" xuống bước lệnh, và nó có người chịu trách nhiệm cập nhật.

Idempotent: DB fresh (`create_all` dựng theo model đã bỏ cột) và DB đã xoá rồi đều là no-op.
"""
from __future__ import annotations

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session

from app.db_migrations import _migrate_go_ngay_ve_du_kien_khuon


def _fixture(*, con_cot: bool):
    engine = create_engine("sqlite+pysqlite:///:memory:")
    cot_ngay = "ngay_ve_du_kien DATE, " if con_cot else ""
    gia_tri = "'2026-09-20', " if con_cot else ""
    ten_ngay = "ngay_ve_du_kien, " if con_cot else ""
    with engine.begin() as cn:
        cn.execute(text(
            "CREATE TABLE khuon_be (id INTEGER PRIMARY KEY, ma VARCHAR(30), ten VARCHAR(200), "
            "khach_hang_id INTEGER, loai VARCHAR(16), so_ke VARCHAR(120), "
            f"tinh_trang VARCHAR(16) NOT NULL DEFAULT 'dang_dung', {cot_ngay}"
            "ghi_chu VARCHAR(500))"
        ))
        cn.execute(text(
            f"INSERT INTO khuon_be (id, ma, ten, loai, so_ke, tinh_trang, {ten_ngay}ghi_chu) "
            f"VALUES (1, 'KB-0013', 'Dao hộp pizza', 'khuon_be', 'Kệ C5', 'dang_dat_lam', "
            f"{gia_tri}'Đặt thợ ngoài làm dao.')"
        ))
    return engine


def _chay(engine) -> None:
    with Session(engine) as db:
        _migrate_go_ngay_ve_du_kien_khuon(db)


def _cot(engine) -> set[str]:
    return {c["name"] for c in inspect(engine).get_columns("khuon_be")}


def test_xoa_cot_ngay_va_giu_nguyen_tinh_trang():
    engine = _fixture(con_cot=True)
    assert "ngay_ve_du_kien" in _cot(engine)

    _chay(engine)

    assert "ngay_ve_du_kien" not in _cot(engine)
    assert {"ma", "ten", "loai", "so_ke", "tinh_trang", "ghi_chu"} <= _cot(engine)
    with engine.begin() as cn:
        r = cn.execute(text("SELECT ma, tinh_trang, so_ke FROM khuon_be WHERE id = 1")).one()
    # Dao đang đặt làm vẫn còn nguyên trạng thái CHẶN của nó sau khi mất ngày.
    assert list(r) == ["KB-0013", "dang_dat_lam", "Kệ C5"]


def test_chay_lai_khong_nem():
    engine = _fixture(con_cot=True)
    _chay(engine)
    _chay(engine)                      # idempotent
    assert "ngay_ve_du_kien" not in _cot(engine)


def test_db_fresh_khong_co_cot_thi_bo_qua():
    engine = _fixture(con_cot=False)
    _chay(engine)
    assert "tinh_trang" in _cot(engine)


def test_db_trang_chua_co_bang_thi_bo_qua():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    _chay(engine)
    assert set(inspect(engine).get_table_names()) == set()
