"""Migration 0292 — khoá quyền `xep_lich_3` (10/09/2026).

Cùng bài học mg `0216`/`0218`/`0219`: migration này đụng DỮ LIỆU SỐNG (`role_permissions` của DB
thật). Quên chép quyền là lần deploy kế tiếp cả tổ điều độ mở màn mới ra thấy 403 — không có gì
báo, vì "thiếu quyền" trông y hệt "chưa được cấp".

KHÔNG test bảng `xep_lich_lenh` ở đây: nó là việc của mg `0291` (đã có bộ test riêng). Cũng KHÔNG
test việc xoá `xep_lich_2` — migration cố ý GIỮ, vì màn 2 chỉ bị ẩn ở FE bằng cờ chứ chưa gỡ.
"""
from __future__ import annotations

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.db_migrations import _migrate_xep_lich_3

CU, MOI = "xep_lich_2", "xep_lich_3"


def _fixture(quyen=()):
    """`role_permissions` đời cũ. `quyen` = (role_id, module_key, read, approve, scope)."""
    engine = create_engine("sqlite+pysqlite:///:memory:")
    with engine.begin() as cn:
        cn.execute(text("CREATE TABLE modules (id INTEGER PRIMARY KEY, key VARCHAR(50) UNIQUE, "
                        "label VARCHAR(100), created_at TIMESTAMP)"))
        cn.execute(text(
            "CREATE TABLE role_permissions (id INTEGER PRIMARY KEY, role_id INTEGER, "
            "module_key VARCHAR(50), can_read BOOLEAN DEFAULT 0, can_approve BOOLEAN DEFAULT 0, "
            "scope VARCHAR(20) DEFAULT 'own')"))
        cn.execute(text("INSERT INTO modules (key, label, created_at) "
                        "VALUES (:k, :l, CURRENT_TIMESTAMP)"),
                   {"k": CU, "l": "Xếp lịch công đoạn"})
        for rid, key, read, approve, scope in quyen:
            cn.execute(text("INSERT INTO role_permissions (role_id, module_key, can_read, "
                            "can_approve, scope) VALUES (:r, :k, :rd, :ap, :sc)"),
                       {"r": rid, "k": key, "rd": read, "ap": approve, "sc": scope})
    return engine


def _run(engine) -> None:
    with Session(engine) as db:
        _migrate_xep_lich_3(db)


def _quyen(engine, key: str) -> list[dict]:
    with engine.begin() as cn:
        return [dict(r._mapping) for r in cn.execute(text(
            "SELECT role_id, can_read, can_approve, scope FROM role_permissions "
            "WHERE module_key = :k ORDER BY role_id"), {"k": key})]


def test_chep_nguyen_quyen_sang_khoa_moi():
    """⭐ Chủ chốt: vai nào đang xếp lịch thì mở màn 3 ra là dùng được ngay, kể cả bit phát hành."""
    engine = _fixture(quyen=[
        (1, CU, 1, 1, "all"),            # trưởng điều độ: có bit phát hành
        (2, CU, 1, 0, "department"),     # tổ trưởng: chỉ xem
        (3, "san_xuat", 1, 1, "all"),    # vai khác: không được ăn theo
    ])
    _run(engine)
    assert _quyen(engine, MOI) == [
        {"role_id": 1, "can_read": 1, "can_approve": 1, "scope": "all"},
        # scope ghi thẳng 'all': `xep_lich_3` nằm trong SCOPELESS_MODULES, không router nào đọc.
        {"role_id": 2, "can_read": 1, "can_approve": 0, "scope": "all"},
    ]


def test_khoa_cu_con_nguyen():
    """Màn 2 chỉ ẨN ở FE — quyền phải còn để bật lại được nếu màn 3 vỡ khi pilot."""
    engine = _fixture(quyen=[(1, CU, 1, 1, "all")])
    _run(engine)
    assert len(_quyen(engine, CU)) == 1


def test_tao_khoa_module_cho_man_hinh_phan_quyen():
    engine = _fixture(quyen=[(1, CU, 1, 1, "all")])
    _run(engine)
    with engine.begin() as cn:
        assert cn.execute(text("SELECT COUNT(*) FROM modules WHERE key = :k"),
                          {"k": MOI}).scalar_one() == 1


def test_chay_lai_khong_de_hang_trung():
    engine = _fixture(quyen=[(1, CU, 1, 1, "all"), (2, CU, 1, 0, "all")])
    _run(engine)
    _run(engine)
    assert len(_quyen(engine, MOI)) == 2
    with engine.begin() as cn:
        assert cn.execute(text("SELECT COUNT(*) FROM modules WHERE key = :k"),
                          {"k": MOI}).scalar_one() == 1


def test_db_chua_ai_co_quyen_cu_thi_khong_no():
    """DB trắng (prod mới dựng): không có gì để chép, migration vẫn phải chạy trót lọt."""
    engine = _fixture()
    _run(engine)
    assert _quyen(engine, MOI) == []
