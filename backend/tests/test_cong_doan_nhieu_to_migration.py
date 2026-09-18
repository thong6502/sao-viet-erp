"""Migration 0312 — công đoạn do NHIỀU tổ phụ trách (bảng nối `cong_doan_to`), gỡ
`cong_doan.department_id`.

Fixture dựng bảng ĐỜI CŨ bằng SQL thô: `create_all` đọc model HIỆN TẠI (đã gỡ cột), nhánh chép dữ
liệu sẽ không bao giờ chạy.
"""
from __future__ import annotations

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session

from app.db_migrations import _migrate_cong_doan_nhieu_to


def _fixture(rows=()):
    """`rows` = (id, department_id)."""
    engine = create_engine("sqlite+pysqlite:///:memory:")
    with engine.begin() as cn:
        cn.execute(text(
            "CREATE TABLE cong_doan (id INTEGER PRIMARY KEY, ma VARCHAR(30) NOT NULL, "
            "ten VARCHAR(150) NOT NULL, nhom VARCHAR(12) NOT NULL, department_id INTEGER)"))
        cn.execute(text("CREATE INDEX ix_cong_doan_department_id ON cong_doan (department_id)"))
        for cid, did in rows:
            cn.execute(text(
                "INSERT INTO cong_doan (id, ma, ten, nhom, department_id) "
                "VALUES (:i, :m, :t, 'finishing', :d)"),
                {"i": cid, "m": f"CD-{cid:04d}", "t": f"Công đoạn {cid}", "d": did})
    return engine


def _run(engine) -> None:
    with Session(engine) as db:
        _migrate_cong_doan_nhieu_to(db)
        db.commit()


def _noi(engine) -> set[tuple[int, int, int]]:
    with engine.begin() as cn:
        return {tuple(r) for r in cn.execute(text(
            "SELECT cong_doan_id, department_id, thu_tu FROM cong_doan_to")).all()}


def test_chep_to_sang_bang_noi_roi_go_cot():
    engine = _fixture(rows=[(1, 10), (2, 999), (3, None)])
    _run(engine)

    # Tổ đã xoá khỏi cây tổ chức (999) VẪN chép — màn đánh dấu để người khai tự gỡ.
    assert _noi(engine) == {(1, 10, 0), (2, 999, 0)}
    cot = {c["name"] for c in inspect(engine).get_columns("cong_doan")}
    assert "department_id" not in cot, cot
    with engine.begin() as cn:
        assert cn.execute(text("SELECT COUNT(*) FROM cong_doan")).scalar_one() == 3, \
            "gỡ cột không được mất dòng công đoạn nào"


def test_chay_lai_khong_chep_trung():
    engine = _fixture(rows=[(1, 10)])
    _run(engine)
    _run(engine)
    assert _noi(engine) == {(1, 10, 0)}


def test_db_trang_theo_model_moi_khong_no():
    """DB dựng theo model mới: không có cột cũ, bảng nối đã có — migration chỉ lướt qua."""
    from app.db import Base
    import app.models  # noqa: F401  (đăng ký mọi model)

    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    _run(engine)
    assert "department_id" not in {c["name"] for c in inspect(engine).get_columns("cong_doan")}
    assert _noi(engine) == set()
