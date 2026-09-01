"""Migration `0251_kcs_kiem_nhiem_backfill_la_kcs` — module KCS kiêm nhiệm, Task 1/12.

Bám ĐÚNG thuật toán chốt ở brief (không suy diễn rộng hơn mức chứng minh được):

  san_xuat_cong_viec.la_kcs_cuoi=true
    → lsx_cong_doan.la_kcs=true (hoặc bai_ghep_cong_doan.la_kcs=true) của ĐÚNG dòng nó neo
      → cong_doan.la_kcs=true nếu dòng routing đó còn trỏ được cong_doan_id

Fixture dựng ĐÚNG hình dạng bảng SAU khi migration `0250` đã ALTER xong (có sẵn các cột KCS),
vì `0251` phụ thuộc `0250` chạy trước. Trọng tâm test: phân biệt rõ công việc ĐÃ chứng minh là
KCS cuối với công việc khác CÙNG tổ (department) nhưng la_kcs_cuoi=false — chỉ cái đầu được đánh
dấu, KHÔNG suy rộng theo tổ.
"""
from __future__ import annotations

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.db_migrations import _migrate_kcs_kiem_nhiem_backfill_la_kcs

DEPT_KCS = 1


def _engine_da_alter():
    """Hình dạng bảng SAU `0250` (cột KCS đã có), TRƯỚC khi `0251` backfill chạy."""
    eng = create_engine("sqlite://")
    with eng.begin() as con:
        con.execute(text(
            "CREATE TABLE cong_doan (id INTEGER PRIMARY KEY, ma TEXT, "
            "la_kcs BOOLEAN NOT NULL DEFAULT 0)"
        ))
        con.execute(text(
            "CREATE TABLE lsx_cong_doan (id INTEGER PRIMARY KEY, cong_doan_id INTEGER, "
            "la_kcs BOOLEAN NOT NULL DEFAULT 0)"
        ))
        con.execute(text(
            "CREATE TABLE bai_ghep_cong_doan (id INTEGER PRIMARY KEY, cong_doan_id INTEGER, "
            "la_kcs BOOLEAN NOT NULL DEFAULT 0)"
        ))
        con.execute(text(
            "CREATE TABLE san_xuat_cong_viec (id INTEGER PRIMARY KEY, "
            "lsx_cong_doan_id INTEGER, bai_ghep_cong_doan_id INTEGER, "
            "la_kcs_cuoi BOOLEAN NOT NULL DEFAULT 0, department_id INTEGER)"
        ))
        con.execute(text(
            "CREATE TABLE san_xuat_kcs_batch (id INTEGER PRIMARY KEY, cong_viec_id INTEGER, "
            "loai VARCHAR(16) NOT NULL DEFAULT 'routing', kcs_department_id INTEGER)"
        ))

        # --- Danh mục công đoạn: 3 mã — CHỈ 2 mã (A, C) được chứng minh KCS cuối ---
        for cd_id, ma in ((1, "CD-A-IN"), (2, "CD-B-BE"), (3, "CD-C-DONG-GOI")):
            con.execute(text("INSERT INTO cong_doan (id, ma) VALUES (:i, :m)"), {"i": cd_id, "m": ma})

        # --- Routing LSX: LC1 (→ CD-A, sẽ được đánh dấu) và LC2 (→ CD-B, KHÔNG được đánh dấu) ---
        con.execute(text("INSERT INTO lsx_cong_doan (id, cong_doan_id) VALUES (1, 1)"))  # LC1 → CD-A
        con.execute(text("INSERT INTO lsx_cong_doan (id, cong_doan_id) VALUES (2, 2)"))  # LC2 → CD-B

        # --- Routing Bài ghép: BG1 (→ CD-C, sẽ được đánh dấu) ---
        con.execute(text("INSERT INTO bai_ghep_cong_doan (id, cong_doan_id) VALUES (1, 3)"))  # BG1 → CD-C

        # --- Công việc (san_xuat_cong_viec): CV1 la_kcs_cuoi=true (LSX) — PHẢI được đánh dấu.
        #     CV2 CÙNG department nhưng la_kcs_cuoi=false — KHÔNG được đánh dấu (điểm phân biệt).
        #     CV3 la_kcs_cuoi=true (Bài ghép) — PHẢI được đánh dấu qua nhánh bài ghép.
        con.execute(text(
            "INSERT INTO san_xuat_cong_viec (id, lsx_cong_doan_id, la_kcs_cuoi, department_id) "
            "VALUES (1, 1, 1, :d)"
        ), {"d": DEPT_KCS})
        con.execute(text(
            "INSERT INTO san_xuat_cong_viec (id, lsx_cong_doan_id, la_kcs_cuoi, department_id) "
            "VALUES (2, 2, 0, :d)"
        ), {"d": DEPT_KCS})
        con.execute(text(
            "INSERT INTO san_xuat_cong_viec (id, bai_ghep_cong_doan_id, la_kcs_cuoi, department_id) "
            "VALUES (3, 1, 1, :d)"
        ), {"d": DEPT_KCS})

        # --- Batch KCS cũ: trỏ CV1 (department_id = DEPT_KCS) ---
        con.execute(text("INSERT INTO san_xuat_kcs_batch (id, cong_viec_id) VALUES (1, 1)"))
    return eng


def _la_kcs(con, table, id_):
    return con.execute(text(f"SELECT la_kcs FROM {table} WHERE id = :i"), {"i": id_}).scalar()


def test_chi_danh_dau_dung_buoc_da_chung_minh():
    eng = _engine_da_alter()
    with Session(eng) as db:
        _migrate_kcs_kiem_nhiem_backfill_la_kcs(db)

    with eng.connect() as con:
        # Routing LSX: LC1 (từ CV1, la_kcs_cuoi=true) → true. LC2 (từ CV2, la_kcs_cuoi=false) → false.
        assert _la_kcs(con, "lsx_cong_doan", 1) in (1, True)
        assert _la_kcs(con, "lsx_cong_doan", 2) in (0, False, None)

        # Routing Bài ghép: BG1 (từ CV3, la_kcs_cuoi=true) → true.
        assert _la_kcs(con, "bai_ghep_cong_doan", 1) in (1, True)

        # Danh mục: CD-A (qua LC1) và CD-C (qua BG1) → true. CD-B (qua LC2, KHÔNG chứng minh) → false
        # dù CV2 nằm CÙNG department_id với CV1 — đây là điểm phân biệt bắt buộc của thuật toán.
        assert _la_kcs(con, "cong_doan", 1) in (1, True)   # CD-A
        assert _la_kcs(con, "cong_doan", 2) in (0, False, None)  # CD-B — KHÔNG được suy rộng theo tổ
        assert _la_kcs(con, "cong_doan", 3) in (1, True)   # CD-C

        # san_xuat_kcs_batch cũ: loai='routing' + kcs_department_id suy từ department_id của CV1.
        loai, dept = con.execute(
            text("SELECT loai, kcs_department_id FROM san_xuat_kcs_batch WHERE id = 1")
        ).one()
        assert loai == "routing"
        assert dept == DEPT_KCS


def test_chay_lai_lan_hai_idempotent():
    eng = _engine_da_alter()
    with Session(eng) as db:
        _migrate_kcs_kiem_nhiem_backfill_la_kcs(db)
    with eng.connect() as con:
        truoc = {
            "lc1": _la_kcs(con, "lsx_cong_doan", 1),
            "lc2": _la_kcs(con, "lsx_cong_doan", 2),
            "bg1": _la_kcs(con, "bai_ghep_cong_doan", 1),
            "cd1": _la_kcs(con, "cong_doan", 1),
            "cd2": _la_kcs(con, "cong_doan", 2),
            "cd3": _la_kcs(con, "cong_doan", 3),
            "batch": con.execute(
                text("SELECT loai, kcs_department_id FROM san_xuat_kcs_batch WHERE id = 1")
            ).one(),
        }

    with Session(eng) as db:
        _migrate_kcs_kiem_nhiem_backfill_la_kcs(db)  # KHÔNG được raise, KHÔNG được đổi kết quả

    with eng.connect() as con:
        assert _la_kcs(con, "lsx_cong_doan", 1) == truoc["lc1"]
        assert _la_kcs(con, "lsx_cong_doan", 2) == truoc["lc2"]
        assert _la_kcs(con, "bai_ghep_cong_doan", 1) == truoc["bg1"]
        assert _la_kcs(con, "cong_doan", 1) == truoc["cd1"]
        assert _la_kcs(con, "cong_doan", 2) == truoc["cd2"]
        assert _la_kcs(con, "cong_doan", 3) == truoc["cd3"]
        assert con.execute(
            text("SELECT loai, kcs_department_id FROM san_xuat_kcs_batch WHERE id = 1")
        ).one() == truoc["batch"]


def test_khong_dong_den_san_xuat_cong_viec_la_kcs_cuoi():
    """Migration CHỈ ĐỌC `la_kcs_cuoi`, không sửa lại — luồng phát hành cũ vẫn tương thích."""
    eng = _engine_da_alter()
    with Session(eng) as db:
        _migrate_kcs_kiem_nhiem_backfill_la_kcs(db)
    with eng.connect() as con:
        rows = con.execute(text("SELECT id, la_kcs_cuoi FROM san_xuat_cong_viec ORDER BY id")).all()
    assert rows == [(1, 1), (2, 0), (3, 1)]
