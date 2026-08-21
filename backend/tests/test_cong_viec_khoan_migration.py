"""Migration 0210 (`piece_rates` vào nền danh mục) + 0211 (ô quyền `dm_cong_viec_khoan`).

Đây là hai migration đụng DỮ LIỆU SỐNG nên phải có bằng chứng chạy được, không chỉ đọc bằng mắt:

* 0210 ĐỔI TÊN ba cột (`code`→`ma` · `name`→`ten` · `is_active`→`active`). Thứ phải đúng tuyệt đối:
  **không dòng nào mất dữ liệu** — bảng này là bảng GIÁ, mất một dòng là mất tiền của một tổ.
* 0211 chép quyền `luong` sang khoá mới. Thiếu bước đó thì ngay lần deploy kế tiếp, vai đang khai
  đơn giá khoán mất sạch màn — đúng bài học của mg `0209`.

Fixture dựng bảng ĐỜI CŨ bằng SQL thô (không dùng `create_all`): `create_all` đọc model HIỆN TẠI,
tức là đã có tên cột mới, nên nhánh rename sẽ không bao giờ chạy và test hoá vô nghĩa.
"""
from __future__ import annotations

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session

from app.db_migrations import (
    _migrate_cong_thuc_luong_may_va_khoan,
    _migrate_module_cong_viec_khoan,
    _migrate_piece_rates_ten_cot_danh_muc,
)


def _fixture(rows=(), don_vis=(), depts=()):
    """DB "cũ": `piece_rates` mang ba tên cột đời cũ.

    `rows` = (id, group_name, department_id, code, name, unit, unit_price)
    `don_vis` = (ma, ten) của danh mục Đơn vị · `depts` = (id, name) của cây tổ chức.
    """
    engine = create_engine("sqlite+pysqlite:///:memory:")
    with engine.begin() as cn:
        cn.execute(text(
            "CREATE TABLE piece_rates (id INTEGER PRIMARY KEY, group_name VARCHAR(40) NOT NULL, "
            "department_id INTEGER, code VARCHAR(20), name VARCHAR(255) NOT NULL, "
            "cong_doan VARCHAR(30), unit VARCHAR(24) NOT NULL DEFAULT 'khác', "
            "unit_price NUMERIC(14,2) NOT NULL, note VARCHAR(255), "
            "is_active BOOLEAN NOT NULL DEFAULT 1, created_at TIMESTAMP)"))
        cn.execute(text("CREATE TABLE don_vi_do (id INTEGER PRIMARY KEY, ma VARCHAR(20), "
                        "ten VARCHAR(60))"))
        cn.execute(text("CREATE TABLE departments (id INTEGER PRIMARY KEY, name VARCHAR(255))"))
        for i, (ma, ten) in enumerate(don_vis, start=1):
            cn.execute(text("INSERT INTO don_vi_do (id, ma, ten) VALUES (:i, :m, :t)"),
                       {"i": i, "m": ma, "t": ten})
        for did, name in depts:
            cn.execute(text("INSERT INTO departments (id, name) VALUES (:i, :n)"),
                       {"i": did, "n": name})
        for rid, gname, did, code, name, unit, price in rows:
            cn.execute(
                text("INSERT INTO piece_rates (id, group_name, department_id, code, name, unit, "
                     "unit_price, is_active) VALUES (:i, :g, :d, :c, :n, :u, :p, 1)"),
                {"i": rid, "g": gname, "d": did, "c": code, "n": name, "u": unit, "p": price},
            )
    return engine


def _run(engine) -> None:
    with Session(engine) as db:
        _migrate_piece_rates_ten_cot_danh_muc(db)
        db.commit()


def _rows(engine) -> list[dict]:
    with engine.begin() as cn:
        return [dict(r._mapping) for r in cn.execute(text(
            "SELECT id, ma, ten, active, unit, group_name FROM piece_rates ORDER BY id"))]


# --- 0210: đổi tên cột --------------------------------------------------------


def test_doi_ten_ba_cot_va_KHONG_MAT_DU_LIEU():
    """⭐ Chủ chốt: rename giữ nguyên từng dòng. Đây là bảng GIÁ — mất một dòng là mất tiền của tổ."""
    engine = _fixture(rows=[
        (1, "Tổ Bế", 10, "BE-01", "Bế máy tự động", "to", 250),
        (2, "Tổ Bế", 10, "BE-02", "Bế tay", "to", 400),
    ], depts=[(10, "Tổ Bế")])
    _run(engine)

    cols = {c["name"] for c in inspect(engine).get_columns("piece_rates")}
    assert {"ma", "ten", "active"} <= cols
    assert not ({"code", "name", "is_active"} & cols), "cột cũ phải biến mất, không để lại hai bộ tên"

    rows = _rows(engine)
    assert len(rows) == 2, "mất dòng sau khi rename"
    assert [r["ma"] for r in rows] == ["BE-01", "BE-02"]
    assert [r["ten"] for r in rows] == ["Bế máy tự động", "Bế tay"]
    assert all(r["active"] for r in rows)


def test_chay_lai_khong_no_va_khong_doi_gi():
    """Idempotent — migration chạy mỗi lần khởi động app."""
    engine = _fixture(rows=[(1, "Tổ Bế", 10, "BE-01", "Bế máy", "to", 250)], depts=[(10, "Tổ Bế")])
    _run(engine)
    truoc = _rows(engine)
    _run(engine)
    assert _rows(engine) == truoc


def test_db_trang_theo_model_moi_thi_bo_qua_nhanh_rename():
    """DB dựng bởi `create_all` đã có tên cột mới ⇒ migration không được nổ (CI chạy trên PG trắng)."""
    engine = create_engine("sqlite+pysqlite:///:memory:")
    with engine.begin() as cn:
        cn.execute(text(
            "CREATE TABLE piece_rates (id INTEGER PRIMARY KEY, group_name VARCHAR(40) NOT NULL, "
            "department_id INTEGER, ma VARCHAR(20), ten VARCHAR(255) NOT NULL, "
            "unit VARCHAR(24) NOT NULL DEFAULT 'khác', unit_price NUMERIC(14,2) NOT NULL, "
            "note VARCHAR(255), active BOOLEAN NOT NULL DEFAULT 1, created_at TIMESTAMP)"))
    _run(engine)   # không ném là đủ
    assert _rows(engine) == []


def test_bang_khong_ton_tai_thi_bo_qua():
    _run(create_engine("sqlite+pysqlite:///:memory:"))


# --- 0210: ba việc dọn kèm ---------------------------------------------------


def test_backfill_ma_cho_dong_trong_va_KHONG_dung_ma_cu():
    """Màn danh mục hiện mã ở cột đầu; dòng trống mã để lại một ô "null" giữa bảng.

    Mã mới phải chạy TIẾP số `KH-` lớn nhất đang có — trùng mã cũ là hai dòng cùng mã."""
    engine = _fixture(rows=[
        (1, "Tổ A", None, "KH-0007", "Việc đã có mã KH", "to", 100),
        (2, "Tổ A", None, "BE-01", "Việc mang mã cũ của xưởng", "to", 100),
        (3, "Tổ A", None, None, "Việc chưa có mã", "to", 100),
        (4, "Tổ A", None, "   ", "Việc mã toàn khoảng trắng", "to", 100),
    ])
    _run(engine)

    theo_id = {r["id"]: r["ma"] for r in _rows(engine)}
    assert theo_id[1] == "KH-0007", "mã đang có không được đụng tới"
    assert theo_id[2] == "BE-01", "mã cũ của xưởng phải giữ nguyên"
    assert theo_id[3] == "KH-0008" and theo_id[4] == "KH-0009", theo_id
    assert len(set(theo_id.values())) == 4, "mã bị trùng sau backfill"


def test_don_vi_doi_TEN_sang_MA_chi_khi_khop_chinh_xac():
    """Ô Đơn vị của màn mới lưu MÃ. Dòng cũ lưu TÊN nên phải đổi, NHƯNG chỉ khi khớp chính xác —
    không khớp thì giữ nguyên để màn báo đỏ, thà thế còn hơn đoán bừa rồi ghi sai đơn vị vào bảng giá."""
    engine = _fixture(
        rows=[
            (1, "Tổ A", None, "KH-0001", "Lưu tên", "tờ", 100),
            (2, "Tổ A", None, "KH-0002", "Đã lưu mã", "to", 100),
            (3, "Tổ A", None, "KH-0003", "Đơn vị lạ", "mét tới", 100),
            (4, "Tổ A", None, "KH-0004", "Khác hoa thường", "M²", 100),
        ],
        don_vis=[("to", "tờ"), ("m2", "m²")],
    )
    _run(engine)

    theo_id = {r["id"]: r["unit"] for r in _rows(engine)}
    assert theo_id[1] == "to", "tên khớp danh mục phải thành mã"
    assert theo_id[2] == "to", "đã là mã thì không đụng"
    assert theo_id[3] == "mét tới", "đơn vị ngoài danh mục GIỮ NGUYÊN"
    assert theo_id[4] == "m2", "so tên không phân biệt hoa/thường"


def test_dong_bo_nhan_to_theo_ten_tho_that():
    """`group_name` là nhãn tổ; service mới suy lại từ `department_id` mỗi lần ghi. Không đồng bộ thì
    panel "Đơn giá khoán của tổ" (lọc theo nhãn) nhìn vào bảng thiếu dòng cho tới lần sửa đầu tiên."""
    engine = _fixture(
        rows=[
            (1, "to_boi", 10, "KH-0001", "Bồi 3 lớp", "to", 100),      # nhãn đời cũ → đổi
            (2, "Tổ Bế", 20, "KH-0002", "Bế tay", "to", 100),          # đã khớp → giữ
            (3, "to_cat", None, "KH-0003", "Cắt", "to", 100),          # chưa gắn tổ → giữ
            (4, "to_ma", 999, "KH-0004", "Tổ đã xoá", "to", 100),      # id không có thật → giữ
        ],
        depts=[(10, "Tổ Bồi"), (20, "Tổ Bế")],
    )
    _run(engine)

    theo_id = {r["id"]: r["group_name"] for r in _rows(engine)}
    assert theo_id[1] == "Tổ Bồi"
    assert theo_id[2] == "Tổ Bế"
    assert theo_id[3] == "to_cat", "dòng chưa gắn tổ giữ nhãn cũ (nó vẫn ở một tab đọc được)"
    assert theo_id[4] == "to_ma", "tổ không còn tồn tại thì không được ghi đè bằng rỗng"


# --- 0211: ô quyền mới -------------------------------------------------------


def _fixture_quyen(rows=()):
    """`modules` + `role_permissions` đời cũ. `rows` = (role_id, module_key, can_read, can_create)."""
    engine = create_engine("sqlite+pysqlite:///:memory:")
    with engine.begin() as cn:
        cn.execute(text("CREATE TABLE modules (id INTEGER PRIMARY KEY, key VARCHAR(50) UNIQUE, "
                        "label VARCHAR(100), created_at TIMESTAMP)"))
        cn.execute(text(
            "CREATE TABLE role_permissions (id INTEGER PRIMARY KEY, role_id INTEGER, "
            "module_key VARCHAR(50), can_read BOOLEAN DEFAULT 0, can_create BOOLEAN DEFAULT 0, "
            "scope VARCHAR(20) DEFAULT 'own')"))
        cn.execute(text("INSERT INTO modules (key, label, created_at) "
                        "VALUES ('luong', 'Lương', CURRENT_TIMESTAMP)"))
        for rid, key, read, create in rows:
            cn.execute(text("INSERT INTO role_permissions (role_id, module_key, can_read, "
                            "can_create, scope) VALUES (:r, :k, :rd, :cr, 'department')"),
                       {"r": rid, "k": key, "rd": read, "cr": create})
    return engine


def _quyen(engine, key: str) -> list[dict]:
    with engine.begin() as cn:
        return [dict(r._mapping) for r in cn.execute(
            text("SELECT role_id, can_read, can_create, scope FROM role_permissions "
                 "WHERE module_key = :k ORDER BY role_id"), {"k": key})]


def test_chep_quyen_luong_sang_khoa_moi():
    """⭐ Không chép = vai đang khai đơn giá khoán mất màn ngay lần deploy kế tiếp (bài học mg 0209)."""
    engine = _fixture_quyen(rows=[(1, "luong", 1, 1), (2, "luong", 1, 0), (3, "nhan_su", 1, 1)])
    with Session(engine) as db:
        _migrate_module_cong_viec_khoan(db)
        db.commit()

    with engine.begin() as cn:
        assert cn.execute(text("SELECT label FROM modules WHERE key = 'dm_cong_viec_khoan'"))\
            .scalar_one() == "Công việc khoán"

    moi = _quyen(engine, "dm_cong_viec_khoan")
    assert [q["role_id"] for q in moi] == [1, 2], "chỉ chép từ vai có quyền `luong`"
    assert [bool(q["can_create"]) for q in moi] == [True, False], "phải chép NGUYÊN động từ"
    # Khoá mới scopeless ⇒ ghi thẳng `all`, không chép `department` (ngày có ai bật lọc theo scope
    # thì quyền bị bó âm thầm).
    assert all(q["scope"] == "all" for q in moi), moi


def test_chay_lai_khong_de_hang_trung():
    engine = _fixture_quyen(rows=[(1, "luong", 1, 1)])
    with Session(engine) as db:
        _migrate_module_cong_viec_khoan(db)
        db.commit()
        _migrate_module_cong_viec_khoan(db)
        db.commit()
    assert len(_quyen(engine, "dm_cong_viec_khoan")) == 1
    with engine.begin() as cn:
        assert cn.execute(text("SELECT COUNT(*) FROM modules WHERE key = 'dm_cong_viec_khoan'"))\
            .scalar_one() == 1


# --- 0213: ô công thức lượng cho máy + đầu việc khoán ------------------------


def _fixture_ct_luong(co_cot=False):
    """Hai bảng ĐỜI CŨ (chưa có `cong_thuc_luong`), hoặc đã có sẵn nếu `co_cot`."""
    engine = create_engine("sqlite+pysqlite:///:memory:")
    cot = ", cong_thuc_luong TEXT" if co_cot else ""
    with engine.begin() as cn:
        cn.execute(text(
            "CREATE TABLE may_thiet_bi (id INTEGER PRIMARY KEY, ma VARCHAR(30), ten VARCHAR(150), "
            f"loai_may VARCHAR(24), don_vi_toc_do VARCHAR(32){cot})"))
        cn.execute(text(
            "CREATE TABLE piece_rates (id INTEGER PRIMARY KEY, group_name VARCHAR(40) NOT NULL, "
            f"ma VARCHAR(20), ten VARCHAR(255) NOT NULL, unit VARCHAR(24), unit_price NUMERIC(14,2){cot})"))
        cn.execute(text("INSERT INTO may_thiet_bi (id, ma, ten, loai_may, don_vi_toc_do) "
                        "VALUES (1, 'MAY-01', 'Máy cán', 'finishing', 'm2_gio')"))
        cn.execute(text("INSERT INTO piece_rates (id, group_name, ma, ten, unit, unit_price) "
                        "VALUES (1, 'Tổ Đóng gói', 'KH-0001', 'Bắt tay', 'cuon', 700)"))
    return engine


def _run_ct_luong(engine) -> None:
    with Session(engine) as db:
        _migrate_cong_thuc_luong_may_va_khoan(db)
        db.commit()


def test_them_cot_cho_ca_hai_bang_va_khong_mat_du_lieu():
    """⭐ Thêm cột NULL, không backfill — dòng đang có phải còn nguyên."""
    engine = _fixture_ct_luong()
    _run_ct_luong(engine)

    insp = inspect(engine)
    for bang in ("may_thiet_bi", "piece_rates"):
        assert "cong_thuc_luong" in {c["name"] for c in insp.get_columns(bang)}, bang
    with engine.begin() as cn:
        assert cn.execute(text("SELECT ten, cong_thuc_luong FROM may_thiet_bi")).all() \
            == [("Máy cán", None)]
        assert cn.execute(text("SELECT ten, cong_thuc_luong FROM piece_rates")).all() \
            == [("Bắt tay", None)]


def test_ct_luong_chay_lai_va_db_trang_deu_khong_no():
    """Idempotent (chạy mỗi lần khởi động app) + DB dựng theo model mới đã có cột sẵn (CI trên PG trắng)."""
    engine = _fixture_ct_luong()
    _run_ct_luong(engine)
    _run_ct_luong(engine)
    _run_ct_luong(_fixture_ct_luong(co_cot=True))


def test_ct_luong_bang_khong_ton_tai_thi_bo_qua():
    _run_ct_luong(create_engine("sqlite+pysqlite:///:memory:"))
