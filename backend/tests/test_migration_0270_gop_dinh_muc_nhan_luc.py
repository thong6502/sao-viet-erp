"""Migration 0270 — gộp định mức nhân lực về MỘT con số.

Bốn ô cùng trả lời "việc này mấy người làm" (ba mốc ở định mức đầu việc + ô riêng của máy) nay
còn đúng một: `cong_doan_dau_viec.so_nguoi_tieu_chuan`. Migration xoá các mốc thừa ở 4 bảng mà
KHÔNG được đụng số tiêu chuẩn / số bố trí thật nằm cạnh — đó là hai số cả hệ còn đọc.

Idempotent: DB fresh (`create_all` dựng theo model đã bỏ cột) và DB đã xoá rồi đều là no-op;
bảng chưa tồn tại thì bỏ qua.
"""
from __future__ import annotations

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session

from app.db_migrations import _migrate_gop_dinh_muc_nhan_luc

# (bảng, cột bị xoá, cột phải còn nguyên)
BANG = {
    "cong_doan_dau_viec": (("so_nguoi_toi_thieu", "so_nguoi_toi_da"), "so_nguoi_tieu_chuan"),
    "may_thiet_bi": (("so_nhan_cong",), "ten"),
    "lsx_cong_doan": (("so_nhan_cong_toi_thieu", "so_nhan_cong_toi_da"), "so_nhan_cong_tieu_chuan"),
    "bai_ghep_cong_doan": (
        ("so_nhan_cong_toi_thieu", "so_nhan_cong_toi_da"), "so_nhan_cong_tieu_chuan",
    ),
}


def _fixture(*, con_cot: bool):
    engine = create_engine("sqlite+pysqlite:///:memory:")
    with engine.begin() as cn:
        for bang, (xoa, giu) in BANG.items():
            kieu_giu = "VARCHAR(80)" if giu == "ten" else "INTEGER NOT NULL DEFAULT 1"
            them = "".join(f", {c} INTEGER" for c in xoa) if con_cot else ""
            cn.execute(text(
                f"CREATE TABLE {bang} (id INTEGER PRIMARY KEY, {giu} {kieu_giu}{them})"
            ))
            gia_tri_giu = "'Bế Yawa'" if giu == "ten" else "4"
            cot_them = ("".join(f", {c}" for c in xoa)) if con_cot else ""
            val_them = ("".join(", 9" for _ in xoa)) if con_cot else ""
            cn.execute(text(
                f"INSERT INTO {bang} (id, {giu}{cot_them}) VALUES (1, {gia_tri_giu}{val_them})"
            ))
    return engine


def _chay(engine) -> None:
    with Session(engine) as db:
        _migrate_gop_dinh_muc_nhan_luc(db)


def _cot(engine, bang: str) -> set[str]:
    return {c["name"] for c in inspect(engine).get_columns(bang)}


def test_xoa_moc_thua_va_giu_so_tieu_chuan():
    engine = _fixture(con_cot=True)
    for bang, (xoa, _) in BANG.items():
        assert set(xoa) <= _cot(engine, bang)

    _chay(engine)

    for bang, (xoa, giu) in BANG.items():
        cot = _cot(engine, bang)
        assert not (set(xoa) & cot), bang
        assert giu in cot, bang
        with engine.begin() as cn:
            (con_lai,) = cn.execute(text(f"SELECT {giu} FROM {bang} WHERE id = 1")).one()
        assert con_lai == ("Bế Yawa" if giu == "ten" else 4), bang


def test_chay_lai_khong_nem():
    engine = _fixture(con_cot=True)
    _chay(engine)
    _chay(engine)                      # idempotent
    assert "so_nguoi_toi_da" not in _cot(engine, "cong_doan_dau_viec")


def test_db_fresh_khong_co_cot_thi_bo_qua():
    engine = _fixture(con_cot=False)
    _chay(engine)
    assert _cot(engine, "may_thiet_bi") == {"id", "ten"}


def test_db_trang_chua_co_bang_thi_bo_qua():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    _chay(engine)
    assert set(inspect(engine).get_table_names()) == set()
