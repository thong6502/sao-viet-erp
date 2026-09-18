"""Migration 0311 — công việc khoán làm được ở NHIỀU tổ (bảng nối `cong_viec_khoan_to`), gỡ
`piece_rates.department_id` + `piece_rates.group_name`.

Migration GỠ CỘT của một bảng GIÁ: thứ phải đúng tuyệt đối là tổ của từng việc sang bảng nối TRƯỚC
khi cột mất — sai một dòng là một tổ nhìn vào panel lương không thấy việc của mình.

Fixture dựng bảng ĐỜI CŨ bằng SQL thô: `create_all` đọc model HIỆN TẠI (đã gỡ hai cột), nhánh chép
dữ liệu sẽ không bao giờ chạy.
"""
from __future__ import annotations

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session

from app.db_migrations import _migrate_cong_viec_khoan_nhieu_to, _migrate_piece_rates_ten_cot_danh_muc


def _fixture(rows=(), depts=()):
    """`rows` = (id, group_name, department_id) · `depts` = (id, name)."""
    engine = create_engine("sqlite+pysqlite:///:memory:")
    with engine.begin() as cn:
        cn.execute(text(
            "CREATE TABLE piece_rates (id INTEGER PRIMARY KEY, group_name VARCHAR(40) NOT NULL, "
            "department_id INTEGER, ma VARCHAR(20), ten VARCHAR(255) NOT NULL, "
            "unit VARCHAR(24) NOT NULL DEFAULT 'khác', unit_price NUMERIC(14,2) NOT NULL, "
            "note VARCHAR(255), active BOOLEAN NOT NULL DEFAULT 1, created_at TIMESTAMP)"))
        cn.execute(text("CREATE INDEX ix_piece_rates_group_name ON piece_rates (group_name)"))
        cn.execute(text("CREATE INDEX ix_piece_rates_department_id ON piece_rates (department_id)"))
        cn.execute(text("CREATE TABLE departments (id INTEGER PRIMARY KEY, name VARCHAR(255))"))
        for did, name in depts:
            cn.execute(text("INSERT INTO departments (id, name) VALUES (:i, :n)"),
                       {"i": did, "n": name})
        for rid, gname, did in rows:
            cn.execute(text(
                "INSERT INTO piece_rates (id, group_name, department_id, ma, ten, unit, unit_price) "
                "VALUES (:i, :g, :d, :m, :t, 'to', 100)"),
                {"i": rid, "g": gname, "d": did, "m": f"KH-{rid:04d}", "t": f"Việc {rid}"})
    return engine


def _run(engine) -> None:
    with Session(engine) as db:
        _migrate_cong_viec_khoan_nhieu_to(db)
        db.commit()


def _noi(engine) -> set[tuple[int, int]]:
    with engine.begin() as cn:
        return {tuple(r) for r in cn.execute(text(
            "SELECT piece_rate_id, department_id FROM cong_viec_khoan_to")).all()}


def test_chep_to_sang_bang_noi_roi_go_hai_cot():
    engine = _fixture(
        rows=[
            (1, "Tổ Bế", 10),        # có tổ ⇒ đúng tổ đó
            (2, "to_boi", 999),      # tổ đã xoá khỏi cây tổ chức ⇒ VẪN chép (màn đánh dấu để gỡ)
            (3, "Tổ In", None),      # chưa gắn tổ, nhãn trùng TÊN tổ đang có ⇒ tổ đó
            (4, "to_cat", None),     # chưa gắn tổ, nhãn lạ ⇒ để trống
        ],
        depts=[(10, "Tổ Bế"), (20, "Tổ In")],
    )
    _run(engine)

    assert _noi(engine) == {(1, 10), (2, 999), (3, 20)}
    cot = {c["name"] for c in inspect(engine).get_columns("piece_rates")}
    assert "group_name" not in cot and "department_id" not in cot, cot
    with engine.begin() as cn:
        assert cn.execute(text("SELECT COUNT(*) FROM piece_rates")).scalar_one() == 4, \
            "gỡ cột không được mất dòng giá nào"


def test_chay_lai_khong_chep_trung():
    engine = _fixture(rows=[(1, "Tổ Bế", 10)], depts=[(10, "Tổ Bế")])
    _run(engine)
    _run(engine)
    assert _noi(engine) == {(1, 10)}


def test_db_trang_theo_model_moi_khong_no():
    """DB dựng bởi `create_all` không có hai cột cũ ⇒ migration chỉ đảm bảo bảng nối, không nổ."""
    engine = create_engine("sqlite+pysqlite:///:memory:")
    with engine.begin() as cn:
        cn.execute(text(
            "CREATE TABLE piece_rates (id INTEGER PRIMARY KEY, ma VARCHAR(20), "
            "ten VARCHAR(255) NOT NULL, unit VARCHAR(24) NOT NULL DEFAULT 'khác', "
            "unit_price NUMERIC(14,2) NOT NULL, active BOOLEAN NOT NULL DEFAULT 1)"))
    _run(engine)
    assert _noi(engine) == set()


def test_bang_khong_ton_tai_thi_bo_qua():
    _run(create_engine("sqlite+pysqlite:///:memory:"))


def test_mg_0210_khong_no_khi_hai_cot_da_go():
    """DB trắng: `create_all` theo model mới không có `group_name` ⇒ bước đồng bộ nhãn tổ của 0210
    phải tự bỏ qua, không thì CI trên PG trắng vỡ ngay lượt migration đầu."""
    engine = create_engine("sqlite+pysqlite:///:memory:")
    with engine.begin() as cn:
        cn.execute(text(
            "CREATE TABLE piece_rates (id INTEGER PRIMARY KEY, ma VARCHAR(20), "
            "ten VARCHAR(255) NOT NULL, unit VARCHAR(24) NOT NULL DEFAULT 'khác', "
            "unit_price NUMERIC(14,2) NOT NULL, active BOOLEAN NOT NULL DEFAULT 1)"))
        cn.execute(text("CREATE TABLE departments (id INTEGER PRIMARY KEY, name VARCHAR(255))"))
        cn.execute(text("INSERT INTO piece_rates (id, ma, ten, unit_price) VALUES (1, 'KH-0001', 'X', 1)"))
    with Session(engine) as db:
        _migrate_piece_rates_ten_cot_danh_muc(db)
        db.commit()
