"""Migration 0219 — Xếp lịch công đoạn 2 thay hẳn màn cũ (19/08/2026).

Cùng bài học mg `0209`/`0211`/`0216`: migration này đụng DỮ LIỆU SỐNG (`role_permissions` của DB
thật) nên phải có bằng chứng chạy được — quên chép quyền là lần deploy kế tiếp cả xưởng mở lên thấy
menu Xếp lịch trống.

KHÔNG test bảng `xep_lich_cong_doan` ở đây vì migration cố ý không đụng tới: hai màn (cũ + v2) dùng
CHUNG một bảng lịch, gỡ màn cũ không mất dòng lịch nào.
"""
from __future__ import annotations

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.db_migrations import _migrate_xep_lich_2_thay_ban_cu


def _fixture(quyen=(), modules=("xep_lich", "xep_lich_2")):
    """`modules` + `role_permissions` đời cũ. `quyen` = (role_id, module_key, read, delete, scope)."""
    engine = create_engine("sqlite+pysqlite:///:memory:")
    _nhan = {"xep_lich": "Xếp lịch công đoạn", "xep_lich_2": "Xếp lịch công đoạn 2"}
    with engine.begin() as cn:
        cn.execute(text("CREATE TABLE modules (id INTEGER PRIMARY KEY, key VARCHAR(50) UNIQUE, "
                        "label VARCHAR(100), created_at TIMESTAMP)"))
        cn.execute(text(
            "CREATE TABLE role_permissions (id INTEGER PRIMARY KEY, role_id INTEGER, "
            "module_key VARCHAR(50), can_read BOOLEAN DEFAULT 0, can_delete BOOLEAN DEFAULT 0, "
            "scope VARCHAR(20) DEFAULT 'own')"))
        for key in modules:
            cn.execute(text("INSERT INTO modules (key, label, created_at) "
                            "VALUES (:k, :l, CURRENT_TIMESTAMP)"),
                       {"k": key, "l": _nhan.get(key, key)})
        for rid, key, read, delete, scope in quyen:
            cn.execute(text("INSERT INTO role_permissions (role_id, module_key, can_read, "
                            "can_delete, scope) VALUES (:r, :k, :rd, :dl, :sc)"),
                       {"r": rid, "k": key, "rd": read, "dl": delete, "sc": scope})
    return engine


def _run(engine) -> None:
    with Session(engine) as db:
        _migrate_xep_lich_2_thay_ban_cu(db)


def _quyen(engine, key: str) -> list[dict]:
    with engine.begin() as cn:
        return [dict(r._mapping) for r in cn.execute(text(
            "SELECT role_id, can_read, can_delete, scope FROM role_permissions "
            "WHERE module_key = :k ORDER BY role_id"), {"k": key})]


def test_chep_du_quyen_roi_moi_xoa_khoa_cu():
    """⭐ Chủ chốt: vai nào từng có màn cũ thì nay có màn mới, chép NGUYÊN động từ."""
    engine = _fixture(quyen=[
        (1, "xep_lich", 1, 1, "all"),          # điều độ: đủ quyền
        (2, "xep_lich", 1, 0, "department"),   # tổ trưởng: chỉ xem/sửa
        (3, "san_xuat", 1, 1, "all"),          # vai khác: không được đụng tới
    ])
    _run(engine)

    moi = _quyen(engine, "xep_lich_2")
    assert [q["role_id"] for q in moi] == [1, 2], "chỉ chép từ vai có quyền `xep_lich`"
    assert [bool(q["can_delete"]) for q in moi] == [True, False], "phải chép NGUYÊN động từ"
    # Khoá mới scopeless ⇒ ghi thẳng `all`, không chép `department` (ngày có ai bật lọc theo scope
    # thì quyền bị bó âm thầm).
    assert all(q["scope"] == "all" for q in moi), moi

    assert _quyen(engine, "xep_lich") == [], "khoá cũ phải sạch, không để hai ô song song"
    assert _quyen(engine, "san_xuat") == [
        {"role_id": 3, "can_read": 1, "can_delete": 1, "scope": "all"}
    ], "module khác không được đụng"


def test_go_dong_modules_cu_va_doi_nhan():
    """Ma trận quyền lấy dòng từ bảng `modules`: còn dòng cũ là admin thấy hai dòng Xếp lịch;
    nhãn `xep_lich_2` phải rụng số 2."""
    _run(engine := _fixture(quyen=[(1, "xep_lich", 1, 1, "all")]))
    with engine.begin() as cn:
        assert cn.execute(text("SELECT key, label FROM modules ORDER BY key")).all() \
            == [("xep_lich_2", "Xếp lịch công đoạn")]


def test_vai_da_co_ca_hai_khoa_thi_giu_nguyen_quyen_dang_co():
    """Hai màn từng chạy song song (mg 0218 đã chép) nên có vai đã mang `xep_lich_2`. Chép đè lên
    là đổi quyền sau lưng người quản trị — NOT EXISTS phải chặn."""
    _run(engine := _fixture(quyen=[
        (1, "xep_lich", 1, 1, "all"),
        (1, "xep_lich_2", 1, 0, "all"),   # đã có sẵn, hẹp hơn bản cũ
    ]))
    assert _quyen(engine, "xep_lich_2") == [
        {"role_id": 1, "can_read": 1, "can_delete": 0, "scope": "all"}
    ]


def test_chay_lai_khong_de_hang_trung():
    """Idempotent: lần hai `xep_lich` đã sạch nên chép/xoá đều 0 dòng, không vỡ."""
    engine = _fixture(quyen=[(1, "xep_lich", 1, 1, "all")])
    _run(engine)
    _run(engine)
    assert _quyen(engine, "xep_lich_2") == [
        {"role_id": 1, "can_read": 1, "can_delete": 1, "scope": "all"}
    ]
    assert _quyen(engine, "xep_lich") == []
