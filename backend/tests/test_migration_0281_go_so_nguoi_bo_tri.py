"""mg `0281`: gỡ cột `so_nhan_cong` (số người bố trí) ở bước lệnh và bước chung bài ghép.

Nhân lực của hệ nay chỉ còn MỘT con số: `so_nhan_cong_tieu_chuan` (kíp chuẩn). Cột bỏ đi chưa
bao giờ có nguồn riêng — mọi đường sinh đều chép từ `cong_doan_dau_viec.so_nguoi_tieu_chuan`.

Khuôn lấy từ `test_migration_0270_gop_dinh_muc_nhan_luc.py` (đợt trước, cùng lý lẽ).
"""
from __future__ import annotations

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session

from app.db_migrations import MIGRATIONS, _migrate_go_so_nguoi_bo_tri

# (bảng, cột bị xoá, cột phải còn nguyên)
BANG_COT = {
    "lsx_cong_doan": ("so_nhan_cong", "so_nhan_cong_tieu_chuan"),
    "bai_ghep_cong_doan": ("so_nhan_cong", "so_nhan_cong_tieu_chuan"),
}


def _fixture(*, con_cot: bool):
    engine = create_engine("sqlite+pysqlite:///:memory:")
    with engine.begin() as cn:
        for bang, (xoa, giu) in BANG_COT.items():
            them = f", {xoa} INTEGER NOT NULL DEFAULT 1" if con_cot else ""
            cn.execute(text(
                f"CREATE TABLE {bang} "
                f"(id INTEGER PRIMARY KEY, {giu} INTEGER NOT NULL DEFAULT 1{them})"
            ))
            cot_them = f", {xoa}" if con_cot else ""
            val_them = ", 6" if con_cot else ""
            cn.execute(text(
                f"INSERT INTO {bang} (id, {giu}{cot_them}) VALUES (1, 2{val_them})"
            ))
    return engine


def _chay(engine) -> None:
    with Session(engine) as db:
        _migrate_go_so_nguoi_bo_tri(db)


def _cot(engine, bang: str) -> set[str]:
    return {c["name"] for c in inspect(engine).get_columns(bang)}


def test_go_cot_bo_tri_va_giu_nguyen_kip_chuan():
    """Xoá đúng ô bố trí, KHÔNG đụng kíp chuẩn — và không backfill 6 sang 2."""
    engine = _fixture(con_cot=True)
    for bang, (xoa, _) in BANG_COT.items():
        assert xoa in _cot(engine, bang)

    _chay(engine)

    for bang, (xoa, giu) in BANG_COT.items():
        cot = _cot(engine, bang)
        assert xoa not in cot, bang
        assert giu in cot, bang
        with engine.begin() as cn:
            (con_lai,) = cn.execute(text(f"SELECT {giu} FROM {bang} WHERE id = 1")).one()
        # Kíp chuẩn giữ NGUYÊN 2 — bước đang bố trí tay 6 người thì số 6 mất theo cột, cố ý:
        # chép 6 vào kíp chuẩn là nhân 6 vào công thức thời lượng, bịa số còn tệ hơn mất số.
        assert con_lai == 2, bang


def test_chay_lai_khong_nem():
    engine = _fixture(con_cot=True)
    _chay(engine)
    _chay(engine)                      # idempotent
    assert "so_nhan_cong" not in _cot(engine, "lsx_cong_doan")


def test_db_fresh_khong_co_cot_thi_bo_qua():
    """DB trắng dựng bằng `create_all` theo model đã bỏ cột — nhánh DROP phải bị bỏ qua."""
    engine = _fixture(con_cot=False)
    _chay(engine)
    assert _cot(engine, "bai_ghep_cong_doan") == {"id", "so_nhan_cong_tieu_chuan"}


def test_db_trang_chua_co_bang_thi_bo_qua():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    _chay(engine)
    assert set(inspect(engine).get_table_names()) == set()


def test_da_dang_ky_vao_chuoi_migration():
    """Không đăng ký thì DB live/prod không bao giờ chạy tới — lỗi câm kinh điển của repo này."""
    ten = [t for t, _ in MIGRATIONS]
    assert "0281_go_so_nguoi_bo_tri" in ten
    assert ten.index("0281_go_so_nguoi_bo_tri") > ten.index("0270_gop_dinh_muc_nhan_luc")
