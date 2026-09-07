"""Migration 0275 — mọi bước routing đều BẮT BUỘC.

Ô tick "Bước bắt buộc" đã gỡ khỏi drawer bước và `LsxCongDoanIn` thôi nhận field, nên dòng cũ nào
lỡ để `false` sẽ kẹt ngoài vòng kiểm (`xep_lich_van_de_service._thieu_du_lieu` bỏ qua bước không
bắt buộc) mà không còn cửa nào sửa lại — migration phải dọn nốt.

Chạm ĐÚNG hai bảng có cột này (`lsx_cong_doan`, `bai_ghep_cong_doan`); `san_xuat_cong_viec` là
snapshot đã phát hành và cũng không có cột, không được đụng. Idempotent: chạy lại là no-op, bảng
chưa tồn tại hoặc DB fresh thiếu cột thì bỏ qua.
"""
from __future__ import annotations

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.db_migrations import _migrate_moi_buoc_deu_bat_buoc

BANG = ("lsx_cong_doan", "bai_ghep_cong_doan")


def _fixture(*, co_cot: bool = True):
    engine = create_engine("sqlite+pysqlite:///:memory:")
    with engine.begin() as cn:
        for bang in BANG:
            them = ", bat_buoc BOOLEAN NOT NULL DEFAULT 1" if co_cot else ""
            cn.execute(text(f"CREATE TABLE {bang} (id INTEGER PRIMARY KEY, ten VARCHAR(80){them})"))
            if co_cot:
                cn.execute(text(
                    f"INSERT INTO {bang} (id, ten, bat_buoc) VALUES "
                    "(1, 'In offset', 1), (2, 'Cán màng', 0), (3, 'Bế', 0)"
                ))
            else:
                cn.execute(text(f"INSERT INTO {bang} (id, ten) VALUES (1, 'In offset')"))
    return engine


def _chay(engine) -> None:
    with Session(engine) as db:
        _migrate_moi_buoc_deu_bat_buoc(db)


def _con_tuy_chon(engine, bang: str) -> int:
    with engine.begin() as cn:
        return cn.execute(text(f"SELECT COUNT(*) FROM {bang} WHERE bat_buoc = 0")).scalar_one()


def test_bat_buoc_false_duoc_nang_len_true():
    engine = _fixture()
    for bang in BANG:
        assert _con_tuy_chon(engine, bang) == 2, f"{bang}: fixture phải có bước tuỳ chọn"

    _chay(engine)

    for bang in BANG:
        assert _con_tuy_chon(engine, bang) == 0, f"{bang}: không còn bước tuỳ chọn"
        with engine.begin() as cn:
            assert cn.execute(text(f"SELECT COUNT(*) FROM {bang}")).scalar_one() == 3, \
                f"{bang}: chỉ SỬA cờ, không được xoá dòng nào"


def test_chay_lai_va_db_thieu_cot_deu_khong_no():
    engine = _fixture()
    _chay(engine)
    _chay(engine)  # idempotent
    for bang in BANG:
        assert _con_tuy_chon(engine, bang) == 0

    _chay(_fixture(co_cot=False))  # DB chưa có cột → bỏ qua, không ném
