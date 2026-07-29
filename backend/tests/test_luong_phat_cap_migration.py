"""Migration 0126 — thêm cột `payroll_params.phat_cap_pct` (trần khấu trừ kỷ luật).

Cột MỚI ⇒ bắt buộc migration: `create_all` chỉ tạo bảng thiếu, KHÔNG bao giờ ALTER bảng đã có.
Không có migration này thì DB prod thiếu cột và mọi lần đọc tham số lương sẽ nổ.

Thứ phải đúng: DB cũ (chưa có cột) sau migration phải có cột với **đúng 0.3** — tức hành vi y hệt
mức 30% viết cứng trước đây, chủ không phải khai lại gì.
"""
from __future__ import annotations

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session

from app.db_migrations import _migrate_payroll_phat_cap_pct


def _engine_cu():
    """DB "cũ": bảng payroll_params CHƯA có cột phat_cap_pct, đã có sẵn 1 dòng tham số."""
    engine = create_engine("sqlite+pysqlite:///:memory:")
    with engine.begin() as cn:
        cn.execute(text(
            "CREATE TABLE payroll_params (id INTEGER PRIMARY KEY, "
            "bhxh_rate NUMERIC(6,4) NOT NULL DEFAULT 0.08)"))
        cn.execute(text("INSERT INTO payroll_params (id, bhxh_rate) VALUES (1, 0.08)"))
    return engine


def test_them_cot_voi_mac_dinh_dung_30_phan_tram():
    """⭐ DB cũ nâng cấp lên phải giữ NGUYÊN hành vi 30% — không bắt chủ khai lại."""
    engine = _engine_cu()
    with Session(engine) as db:
        _migrate_payroll_phat_cap_pct(db)
        db.commit()

    assert "phat_cap_pct" in {c["name"] for c in inspect(engine).get_columns("payroll_params")}
    with engine.begin() as cn:
        assert float(cn.execute(text("SELECT phat_cap_pct FROM payroll_params")).scalar()) == 0.3


def test_chay_lai_lan_hai_khong_no_va_khong_de_len_so_chu_da_khai():
    """Migration chạy MỖI lần khởi động app. Guard theo cột ⇒ lần 2 phải là no-op.

    Quan trọng hơn: nếu chủ đã đổi thành 0 (tắt trần), lần chạy sau KHÔNG được kéo về 0.3."""
    engine = _engine_cu()
    with Session(engine) as db:
        _migrate_payroll_phat_cap_pct(db)
        db.commit()
    with engine.begin() as cn:
        cn.execute(text("UPDATE payroll_params SET phat_cap_pct = 0"))

    with Session(engine) as db:
        _migrate_payroll_phat_cap_pct(db)   # không được nổ
        db.commit()

    with engine.begin() as cn:
        assert float(cn.execute(text("SELECT phat_cap_pct FROM payroll_params")).scalar()) == 0.0


def test_bo_qua_khi_chua_co_bang():
    """DB trắng: `create_all` chưa chạy ⇒ chưa có bảng. Migration phải im lặng bỏ qua."""
    engine = create_engine("sqlite+pysqlite:///:memory:")
    with Session(engine) as db:
        _migrate_payroll_phat_cap_pct(db)   # không được nổ
        db.commit()
    assert "payroll_params" not in inspect(engine).get_table_names()
