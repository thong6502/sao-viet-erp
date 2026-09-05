"""Migration 0127 (danh mục bậc tay nghề) + 0128 (% hoa hồng).

0127 đụng HỒ SƠ NHÂN SỰ THẬT: nó gom bậc từ hai cột cũ về `job_grade_id`. Thứ phải đúng tuyệt đối
là **không ai mất bậc** — người đang có bậc trước khi chạy thì sau khi chạy vẫn phải có đúng bậc đó.
"""
from __future__ import annotations

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session

from app.db_migrations import (
    _migrate_bac_tay_nghe_he_so,
    _migrate_employee_salary_commission_pct,
    _migrate_job_grade_catalog,
    _migrate_job_grade_drop_phu,
    _migrate_job_grade_ten_dan_da,
)

_SEED_CODES = ["bac_1", "bac_2", "bac_3", "bac_4", "bac_5"]


def _fixture(rows=()):
    """DB "cũ": có `job_grades` (create_all vừa tạo) nhưng `employees` CHƯA có `job_grade_id`.

    `rows` = (id, pay_grade_key, job_grade) — dựng đúng các kiểu dữ liệu cũ cần backfill."""
    engine = create_engine("sqlite+pysqlite:///:memory:")
    with engine.begin() as cn:
        cn.execute(text(
            "CREATE TABLE job_grades (id INTEGER PRIMARY KEY, code VARCHAR(20) UNIQUE, "
            "name VARCHAR(60), seq INTEGER DEFAULT 0, is_active BOOLEAN DEFAULT 1, "
            "note VARCHAR(255), created_at TIMESTAMP)"))
        cn.execute(text(
            "CREATE TABLE employees (id INTEGER PRIMARY KEY, full_name VARCHAR(255), "
            "pay_grade_key VARCHAR(20), job_grade VARCHAR(50))"))
        for eid, key, grade in rows:
            cn.execute(
                text("INSERT INTO employees (id, full_name, pay_grade_key, job_grade) "
                     "VALUES (:i, :n, :k, :g)"),
                {"i": eid, "n": f"NV {eid}", "k": key, "g": grade},
            )
    return engine


def _run(engine) -> None:
    with Session(engine) as db:
        _migrate_job_grade_catalog(db)
        db.commit()


def _grades(engine) -> list[tuple]:
    with engine.begin() as cn:
        return cn.execute(text(
            "SELECT code, name, seq, is_active FROM job_grades ORDER BY seq")).all()


def test_seed_ra_dung_5_bac_dung_thu_tu():
    """⭐ Chủ chốt 5 BẬC CHÍNH, Bậc 1 đứng đầu (bậc CAO NHẤT). Bậc phụ đã bỏ."""
    engine = _fixture()
    _run(engine)

    rows = _grades(engine)
    assert [r[0] for r in rows] == _SEED_CODES
    assert [r[1] for r in rows] == ["Bậc 1", "Bậc 2", "Bậc 3", "Bậc 4", "Bậc 5"]
    assert all(r[3] for r in rows), "cả 5 bậc phải đang hoạt động"


def test_danh_muc_khong_gan_tien_va_khong_gan_he_so():
    """⭐ "Khai bậc thôi, chứ không cần điền tiền đâu" (chủ 29/07).

    Test này canh THIẾT KẾ, không canh dữ liệu: nếu ai đó thêm cột tiền/hệ số vào danh mục thì
    phải quay lại hỏi chủ, không phải lặng lẽ thêm."""
    engine = _fixture()
    _run(engine)

    cols = {c["name"] for c in inspect(engine).get_columns("job_grades")}
    assert cols == {"id", "code", "name", "seq", "is_active", "note", "created_at"}


def test_backfill_tu_pay_grade_key_va_tu_chu_khong_ai_mat_bac():
    """⭐ Ba đường vào, không ai mất bậc.

    A: có `pay_grade_key` chuẩn ⇒ khớp MÃ.
    B: chỉ có chữ, viết thường + thừa dấu cách ⇒ vẫn khớp đúng bậc chuẩn, KHÔNG đẻ bậc mới.
    C: chữ lạ ⇒ sinh bậc riêng nhưng phải TẮT, để danh sách chọn vẫn sạch 5 bậc."""
    engine = _fixture([
        (1, "tho_2", None),
        (2, None, "  bậc 3 "),
        (3, None, "Thợ cắt"),
        (4, None, None),          # chưa khai bậc — phải giữ nguyên null
    ])
    _run(engine)

    with engine.begin() as cn:
        got = dict(cn.execute(text(
            "SELECT e.id, g.code FROM employees e "
            "LEFT JOIN job_grades g ON g.id = e.job_grade_id")).all())
    assert got[1] == "bac_2", "mã pay_grade_key CŨ tho_2 phải ánh xạ sang Bậc 2"
    assert got[2] == "bac_3", "chữ thường + dấu cách thừa vẫn phải gộp vào Bậc 3"
    assert got[3] is not None and got[3] not in _SEED_CODES, "chữ lạ phải có bậc riêng, không vứt"
    assert got[4] is None, "người chưa khai bậc thì đừng gán bừa"

    rows = _grades(engine)
    assert [r[0] for r in rows if r[3]] == _SEED_CODES, "danh sách CHỌN vẫn đúng 5 bậc"
    la = [r for r in rows if not r[3]]
    assert len(la) == 1 and la[0][1] == "Thợ cắt", "bậc tự sinh phải bị tắt sẵn"


def test_chay_lai_lan_hai_khong_de_len_ten_chu_da_sua():
    """Migration chạy MỖI lần khởi động app. Chủ đổi tên "Bậc 1" → "Bậc 1 (thợ cả)" thì lần chạy
    sau KHÔNG được kéo về tên seed."""
    engine = _fixture([(1, "tho_1", None)])
    _run(engine)
    with engine.begin() as cn:
        cn.execute(text("UPDATE job_grades SET name = 'Bậc 1 (thợ cả)' WHERE code = 'bac_1'"))

    _run(engine)   # lần hai — không được nổ, không được đè

    with engine.begin() as cn:
        assert cn.execute(text(
            "SELECT name FROM job_grades WHERE code = 'bac_1'")).scalar() == "Bậc 1 (thợ cả)"
        assert cn.execute(text("SELECT COUNT(*) FROM job_grades")).scalar() == 5


def test_bo_qua_khi_chua_co_bang():
    """DB trắng, `create_all` chưa chạy ⇒ migration im lặng bỏ qua, không nổ."""
    engine = create_engine("sqlite+pysqlite:///:memory:")
    with Session(engine) as db:
        _migrate_job_grade_catalog(db)
        db.commit()
    assert "job_grades" not in inspect(engine).get_table_names()


# --- 0128: % hoa hồng ------------------------------------------------------

def _engine_salaries():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    with engine.begin() as cn:
        cn.execute(text(
            "CREATE TABLE employee_salaries (id INTEGER PRIMARY KEY, employee_id INTEGER, "
            "luong_vi_tri NUMERIC(14,2) NOT NULL DEFAULT 0)"))
        cn.execute(text("INSERT INTO employee_salaries (id, employee_id) VALUES (1, 7)"))
    return engine


def test_commission_pct_them_cot_mac_dinh_0():
    """Người đang có lương mà chưa khai hoa hồng ⇒ 0, không phải NULL (cột NOT NULL)."""
    engine = _engine_salaries()
    with Session(engine) as db:
        _migrate_employee_salary_commission_pct(db)
        db.commit()

    with engine.begin() as cn:
        assert float(cn.execute(text(
            "SELECT commission_pct FROM employee_salaries")).scalar()) == 0.0


def test_commission_pct_chay_lai_khong_de_len_so_da_khai():
    engine = _engine_salaries()
    with Session(engine) as db:
        _migrate_employee_salary_commission_pct(db)
        db.commit()
    with engine.begin() as cn:
        cn.execute(text("UPDATE employee_salaries SET commission_pct = 0.05"))

    with Session(engine) as db:
        _migrate_employee_salary_commission_pct(db)   # lần hai
        db.commit()

    with engine.begin() as cn:
        assert float(cn.execute(text(
            "SELECT commission_pct FROM employee_salaries")).scalar()) == 0.05


# --- 0129: bỏ bậc PHỤ, còn 5 bậc chính -------------------------------------
# Chủ chốt lại trong ngày: "bỏ phụ đi cho 5 bậc chính đánh từ bậc 1 đến bậc 5". DB nào đã chạy
# bản đầu (3 chính + 2 phụ) phải đổi được sang bộ mới mà KHÔNG ai mất bậc.

def _engine_bo_cu(ten_bac_1="Bậc 1"):
    """DB đã chạy bản đầu: danh mục còn tho_1..phu_2, và có người đang mang bậc Phụ 1."""
    engine = create_engine("sqlite+pysqlite:///:memory:")
    with engine.begin() as cn:
        cn.execute(text(
            "CREATE TABLE job_grades (id INTEGER PRIMARY KEY, code VARCHAR(20) UNIQUE, "
            "name VARCHAR(60), seq INTEGER DEFAULT 0, is_active BOOLEAN DEFAULT 1, "
            "note VARCHAR(255), created_at TIMESTAMP)"))
        cn.execute(text(
            "CREATE TABLE employees (id INTEGER PRIMARY KEY, full_name VARCHAR(255), "
            "job_grade_id INTEGER)"))
        for i, (code, name, seq) in enumerate(
            (("tho_1", ten_bac_1, 1), ("tho_2", "Bậc 2", 2), ("tho_3", "Bậc 3", 3),
             ("phu_1", "Phụ 1", 4), ("phu_2", "Phụ 2", 5)), start=1
        ):
            cn.execute(text("INSERT INTO job_grades (id, code, name, seq, is_active) "
                            "VALUES (:i, :c, :n, :s, 1)"),
                       {"i": i, "c": code, "n": name, "s": seq})
        # NV1 mang Phụ 1 (id 4), NV2 mang Bậc 2 (id 2)
        cn.execute(text("INSERT INTO employees (id, full_name, job_grade_id) "
                        "VALUES (1,'Thợ phụ',4), (2,'Thợ chính',2)"))
    return engine


def test_0129_doi_ten_tai_cho_khong_ai_mat_bac():
    """⭐ Người đang ở "Phụ 1" phải thành "Bậc 4" — KHÔNG bị mất bậc, KHÔNG phải gán lại.

    Đây là lý do migration đổi tên TẠI CHỖ giữ nguyên `id`, thay vì xoá rồi seed lại."""
    engine = _engine_bo_cu()
    with Session(engine) as db:
        _migrate_job_grade_drop_phu(db)
        db.commit()

    # Kiểm HỒ SƠ trước — đây mới là thứ hỏng thì đau. Làm kiểu xoá-rồi-seed-lại sẽ mất sạch ở
    # đây (hồ sơ trỏ vào id cũ đã bị xoá), còn danh mục thì trông vẫn "đúng 5 bậc".
    with engine.begin() as cn:
        mang = dict(cn.execute(text(
            "SELECT e.full_name, g.name FROM employees e "
            "JOIN job_grades g ON g.id = e.job_grade_id")).all())
    assert mang == {"Thợ phụ": "Bậc 4", "Thợ chính": "Bậc 2"}, \
        "đổi tên tại chỗ ⇒ hồ sơ vẫn trỏ đúng dòng, không ai mất bậc"
    assert _grades(engine) == [
        ("bac_1", "Bậc 1", 1, 1), ("bac_2", "Bậc 2", 2, 1), ("bac_3", "Bậc 3", 3, 1),
        ("bac_4", "Bậc 4", 4, 1), ("bac_5", "Bậc 5", 5, 1),
    ]


def test_0129_khong_de_len_ten_chu_da_sua():
    """Chủ đã đổi tên bậc thì giữ tên đó — chỉ chuẩn hoá mã, không đè công khai báo."""
    engine = _engine_bo_cu(ten_bac_1="Thợ cả")
    with Session(engine) as db:
        _migrate_job_grade_drop_phu(db)
        db.commit()

    ten = dict((r[0], r[1]) for r in _grades(engine))
    assert ten["bac_1"] == "Thợ cả", "tên chủ tự đặt phải giữ nguyên"
    assert ten["bac_4"] == "Bậc 4", "tên còn nguyên seed cũ thì mới đổi"


# --- 0155: đổi 5 bậc sang tên DÂN DÃ ---------------------------------------

def test_0155_doi_ten_dan_da():
    """⭐ Bậc 1…5 (còn nguyên tên seed) → tên dân dã, GIỮ mã/hạng, không ai mất bậc."""
    engine = _fixture()
    _run(engine)   # 0127 seed "Bậc 1…Bậc 5"
    with Session(engine) as db:
        _migrate_job_grade_ten_dan_da(db)
        db.commit()

    ten = dict((r[0], r[1]) for r in _grades(engine))
    assert ten == {"bac_1": "Thợ lành nghề", "bac_2": "Thợ vững", "bac_3": "Thợ thường",
                   "bac_4": "Tập việc", "bac_5": "Lính mới"}


def test_0155_khong_de_len_ten_chu_da_sua():
    """Chủ đã đổi tên một bậc thì giữ tên đó; bậc còn nguyên seed cũ mới đổi. Chạy lại = no-op."""
    engine = _fixture()
    _run(engine)
    with engine.begin() as cn:
        cn.execute(text("UPDATE job_grades SET name = 'Thợ cả' WHERE code = 'bac_1'"))

    with Session(engine) as db:
        _migrate_job_grade_ten_dan_da(db)
        _migrate_job_grade_ten_dan_da(db)   # lần hai — idempotent
        db.commit()

    ten = dict((r[0], r[1]) for r in _grades(engine))
    assert ten["bac_1"] == "Thợ cả", "tên chủ tự đặt phải giữ nguyên"
    assert ten["bac_2"] == "Thợ vững", "bậc còn nguyên seed cũ thì đổi"


def test_0129_chay_lai_va_chay_tren_db_moi_deu_khong_sao():
    """DB mới đã seed thẳng bac_* ⇒ không có gì để đổi. Chạy lại lần hai ⇒ no-op."""
    engine = _engine_bo_cu()
    with Session(engine) as db:
        _migrate_job_grade_drop_phu(db)
        db.commit()
        _migrate_job_grade_drop_phu(db)      # lần hai
        db.commit()
    assert [r[0] for r in _grades(engine)] == _SEED_CODES

    moi = _fixture()
    _run(moi)                                 # 0127 seed thẳng bac_*
    with Session(moi) as db:
        _migrate_job_grade_drop_phu(db)
        db.commit()
    assert [r[0] for r in _grades(moi)] == _SEED_CODES


# --- 0263: rót hệ số sản lượng mặc định -------------------------------------


def _fixture_he_so(rows):
    """DB đã có `job_grades` KÈM cột `output_coefficient` (mg 0220 chạy rồi).

    `rows` = (code, output_coefficient) — None nghĩa là chưa ai khai."""
    engine = create_engine("sqlite+pysqlite:///:memory:")
    with engine.begin() as cn:
        cn.execute(text(
            "CREATE TABLE job_grades (id INTEGER PRIMARY KEY, code VARCHAR(20) UNIQUE, "
            "name VARCHAR(60), seq INTEGER DEFAULT 0, is_active BOOLEAN DEFAULT 1, "
            "note VARCHAR(255), output_coefficient NUMERIC(6,3), created_at TIMESTAMP)"))
        for i, (code, heso) in enumerate(rows, start=1):
            cn.execute(
                text("INSERT INTO job_grades (id, code, name, seq, output_coefficient) "
                     "VALUES (:i, :c, :n, :s, :h)"),
                {"i": i, "c": code, "n": f"Bậc {i}", "s": i, "h": heso},
            )
    return engine


def _he_so(engine) -> dict[str, float | None]:
    with engine.begin() as cn:
        return {
            r[0]: (None if r[1] is None else float(r[1]))
            for r in cn.execute(text("SELECT code, output_coefficient FROM job_grades"))
        }


def test_0263_rot_he_so_cho_bac_dang_trong():
    """⭐ NULL hệ số = CHẶN chốt phân bổ sản lượng (§8), không phải "coi như 1.0".

    Đây là lý do migration tồn tại: DB đang chạy có đủ 5 bậc nhưng hệ số trống, nên mẻ khoán đầu
    tiên sẽ treo. Sau migration cả 5 bậc phải có số của chủ."""
    engine = _fixture_he_so([(c, None) for c in _SEED_CODES])
    with Session(engine) as db:
        _migrate_bac_tay_nghe_he_so(db)
    assert _he_so(engine) == {
        "bac_1": 1.3, "bac_2": 1.15, "bac_3": 1.0, "bac_4": 0.9, "bac_5": 0.8}


def test_0263_khong_de_so_xuong_da_sua_va_khong_dung_bac_tu_them():
    """⭐ Chạy lại migration KHÔNG được đè số xưởng đã sửa tay, và không đụng bậc người dùng tự thêm."""
    engine = _fixture_he_so(
        [("bac_1", 2.5), ("bac_2", None), ("bac_3", None), ("bac_4", None), ("bac_5", None),
         ("bac_tu_them", None)])
    with Session(engine) as db:
        _migrate_bac_tay_nghe_he_so(db)
        _migrate_bac_tay_nghe_he_so(db)   # chạy chồng phải vô hại
    got = _he_so(engine)
    assert got["bac_1"] == 2.5, "số xưởng tự sửa bị migration đè mất"
    assert got["bac_2"] == 1.15 and got["bac_5"] == 0.8, "dòng còn trống vẫn phải được rót"
    assert got["bac_tu_them"] is None, "bậc do người dùng tự thêm để họ tự khai, migration không đoán"


def test_0263_bo_qua_khi_chua_co_cot():
    """DB trung gian chưa chạy mg 0220 (chưa có cột) — migration phải im lặng bỏ qua, không nổ."""
    engine = create_engine("sqlite+pysqlite:///:memory:")
    with engine.begin() as cn:
        cn.execute(text(
            "CREATE TABLE job_grades (id INTEGER PRIMARY KEY, code VARCHAR(20) UNIQUE, "
            "name VARCHAR(60))"))
    with Session(engine) as db:
        _migrate_bac_tay_nghe_he_so(db)   # không được ném
    with engine.begin() as cn:
        assert "output_coefficient" not in {
            c["name"] for c in inspect(engine).get_columns("job_grades")}
