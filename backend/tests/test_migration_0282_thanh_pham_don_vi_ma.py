"""mg `0282`: ĐVT của thành phẩm — đổi TÊN đã lỡ ghi sang MÃ danh mục.

Lỗi thật (08/09/2026): mở dòng "Bìa sách" ở màn Thành phẩm thì ô Đơn vị tính báo đỏ
*"cái · không có trong danh mục"*, trong khi `cái` CÓ trong danh mục — dưới mã `cai`.

Nguồn: `thanh_pham_khai_bao` chép thẳng `order_lines.don_vi_tinh` (một cái TÊN, vì nó in lên báo
giá gửi khách) sang `vat_tu_in_an.don_vi_gia` (cột giữ MÃ, vì kho tra bằng mã).

Khuôn lấy từ `test_migration_0281_go_so_nguoi_bo_tri.py`.
"""
from __future__ import annotations

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.db_migrations import MIGRATIONS, _migrate_thanh_pham_don_vi_ten_sang_ma

#: (mã, tên) của danh mục đơn vị — đúng bộ mà `seed_rebuild.seed_don_vi_do` khai.
DON_VI = [("cai", "cái"), ("hop", "hộp"), ("thung", "thùng"), ("to", "tờ")]


def _fixture(dong: list[tuple[int, str | None]], *, don_vi=DON_VI, co_bang=True):
    """DB tí hon: `don_vi_do` + `vat_tu_in_an` với các giá trị ĐVT cho trước."""
    engine = create_engine("sqlite+pysqlite:///:memory:")
    with engine.begin() as cn:
        if not co_bang:
            return engine
        cn.execute(text("CREATE TABLE don_vi_do (id INTEGER PRIMARY KEY, ma TEXT, ten TEXT)"))
        for i, (ma, ten) in enumerate(don_vi, start=1):
            cn.execute(text("INSERT INTO don_vi_do (id, ma, ten) VALUES (:i, :m, :t)"),
                       {"i": i, "m": ma, "t": ten})
        cn.execute(text(
            "CREATE TABLE vat_tu_in_an (id INTEGER PRIMARY KEY, ma TEXT, don_vi_gia TEXT)"
        ))
        for rid, dv in dong:
            cn.execute(text(
                "INSERT INTO vat_tu_in_an (id, ma, don_vi_gia) VALUES (:i, :m, :d)"
            ), {"i": rid, "m": f"TP-{rid:05d}", "d": dv})
    return engine


def _chay(engine) -> None:
    with Session(engine) as db:
        _migrate_thanh_pham_don_vi_ten_sang_ma(db)


def _dvt(engine) -> dict[int, str | None]:
    with engine.begin() as cn:
        return {r[0]: r[1] for r in cn.execute(
            text("SELECT id, don_vi_gia FROM vat_tu_in_an ORDER BY id")).all()}


def test_ten_doi_thanh_MA():
    """⭐ Đúng cái dòng trên ảnh chụp: "cái" → "cai" thì ô hết báo đỏ."""
    engine = _fixture([(1, "cái"), (2, "hộp"), (3, "thùng")])
    _chay(engine)
    assert _dvt(engine) == {1: "cai", 2: "hop", 3: "thung"}


def test_da_la_MA_thi_khong_dung_toi():
    engine = _fixture([(1, "cai"), (2, "to")])
    _chay(engine)
    assert _dvt(engine) == {1: "cai", 2: "to"}


def test_khong_khop_gi_thi_GIU_NGUYEN_khong_xoa_trang():
    """Thà để màn báo đỏ một dòng cho người ta sửa tay, còn hơn tự ý bỏ mất đơn vị của một mặt
    hàng có thể đang có lô tồn. Cùng luật mg `0210` dùng cho `piece_rates.unit`."""
    engine = _fixture([(1, "chiếc"), (2, None), (3, "")])
    _chay(engine)
    assert _dvt(engine) == {1: "chiếc", 2: None, 3: ""}


def test_MA_thang_khi_ten_don_vi_nay_trung_ma_don_vi_kia():
    """Cột này là cột MÃ: giá trị đã là mã hợp lệ thì không đổi, dù nó cũng là tên của dòng khác."""
    engine = _fixture([(1, "to")], don_vi=[("to", "tờ"), ("x", "to")])
    _chay(engine)
    assert _dvt(engine) == {1: "to"}


def test_ten_TRUNG_NHAU_thi_bo_qua_khong_doan_bua():
    engine = _fixture([(1, "cái")], don_vi=[("cai", "cái"), ("cai2", "cái")])
    _chay(engine)
    assert _dvt(engine) == {1: "cái"}


def test_chay_lai_khong_nem():
    engine = _fixture([(1, "cái")])
    _chay(engine)
    _chay(engine)                      # idempotent
    assert _dvt(engine) == {1: "cai"}


def test_db_trang_chua_co_bang_thi_bo_qua():
    _chay(_fixture([], co_bang=False))


def test_da_dang_ky_vao_chuoi_migration():
    """Không đăng ký thì DB live/prod không bao giờ chạy tới — lỗi câm kinh điển của repo này."""
    ten = [t for t, _ in MIGRATIONS]
    assert "0282_thanh_pham_don_vi_ten_sang_ma" in ten
    assert ten.index("0282_thanh_pham_don_vi_ten_sang_ma") > ten.index("0281_go_so_nguoi_bo_tri")
