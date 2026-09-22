"""Migration 0326: cấu hình Khoán trở thành aggregate 1–1 của Công đoạn."""
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session

from app.db_migrations import MIGRATIONS


def _chay(db: Session) -> None:
    dict(MIGRATIONS)["0326_hop_nhat_khoan_vao_cong_doan"](db)


def _cot(db: Session, bang: str) -> set[str]:
    return {c["name"] for c in inspect(db.get_bind()).get_columns(bang)}


def test_0326_tao_hai_bang_khoan_va_nguon_moi_tren_me_idempotent():
    eng = create_engine("sqlite://")
    with Session(eng) as db:
        db.execute(text("CREATE TABLE cong_doan (id INTEGER PRIMARY KEY, ten VARCHAR(150))"))
        db.execute(text("CREATE TABLE san_xuat_batch (id INTEGER PRIMARY KEY, piece_rate_id INTEGER)"))
        db.commit()

        _chay(db)

        bang = set(inspect(eng).get_table_names())
        assert {"cong_doan_khoan", "cong_doan_khoan_phat_sinh"} <= bang
        assert {"id", "cong_doan_id", "unit", "unit_price", "cong_thuc_khoan"} \
            <= _cot(db, "cong_doan_khoan")
        assert {"id", "cong_doan_khoan_id", "ten", "don_gia", "don_vi", "thu_tu"} \
            <= _cot(db, "cong_doan_khoan_phat_sinh")
        assert "khoan_cong_doan_id" in _cot(db, "san_xuat_batch")

        unique = inspect(eng).get_unique_constraints("cong_doan_khoan")
        assert any(u["column_names"] == ["cong_doan_id"] for u in unique)

        _chay(db)


def test_0326_db_trang_khong_no_va_khong_dung_du_lieu_cu():
    eng = create_engine("sqlite://")
    with Session(eng) as db:
        _chay(db)
        assert "cong_doan_khoan" not in set(inspect(eng).get_table_names())

    eng = create_engine("sqlite://")
    with Session(eng) as db:
        db.execute(text("CREATE TABLE cong_doan (id INTEGER PRIMARY KEY, ten VARCHAR(150))"))
        db.execute(text("CREATE TABLE piece_rates (id INTEGER PRIMARY KEY, ten VARCHAR(150))"))
        db.execute(text("INSERT INTO piece_rates VALUES (7, 'Việc cũ')"))
        db.commit()
        _chay(db)
        assert db.execute(text("SELECT COUNT(*) FROM cong_doan_khoan")).scalar_one() == 0
        assert db.execute(text("SELECT ten FROM piece_rates WHERE id=7")).scalar_one() == "Việc cũ"


def test_0326_go_module_quyen_cu_nhung_giu_bang_legacy():
    eng = create_engine("sqlite://")
    with Session(eng) as db:
        db.execute(text("CREATE TABLE cong_doan (id INTEGER PRIMARY KEY)"))
        db.execute(text("CREATE TABLE modules (key VARCHAR PRIMARY KEY, label VARCHAR)"))
        db.execute(text(
            "CREATE TABLE role_permissions (id INTEGER PRIMARY KEY, module_key VARCHAR)"
        ))
        db.execute(text("CREATE TABLE piece_rates (id INTEGER PRIMARY KEY)"))
        db.execute(text("INSERT INTO modules VALUES ('dm_cong_viec_khoan', 'Công việc khoán')"))
        db.execute(text("INSERT INTO role_permissions VALUES (1, 'dm_cong_viec_khoan')"))
        db.commit()

        _chay(db)

        assert db.execute(text("SELECT COUNT(*) FROM modules")).scalar_one() == 0
        assert db.execute(text("SELECT COUNT(*) FROM role_permissions")).scalar_one() == 0
        assert "piece_rates" in set(inspect(eng).get_table_names())
