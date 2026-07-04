"""Migration 0004 — patch một DB paper_sizes schema CŨ tiến lên full spec (production Postgres
giữ volume, create_all không ALTER → phải qua db_migrations). Kiểm: thêm cột, backfill loại khổ
từ size_type cũ, swap unique(code)→unique(code,version), thêm cột costing links, và idempotent.
"""
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db_migrations import _migrate_paper_size_full_fields


def _old_schema_db():
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    db = sessionmaker(bind=eng)()
    # OLD paper_sizes shape (before this feature).
    db.execute(text(
        "CREATE TABLE paper_sizes ("
        " id INTEGER PRIMARY KEY AUTOINCREMENT,"
        " code VARCHAR(20) NOT NULL,"
        " name VARCHAR(255) NOT NULL,"
        " width_cm NUMERIC(10,2) NOT NULL,"
        " height_cm NUMERIC(10,2) NOT NULL,"
        " size_type VARCHAR(16) NOT NULL DEFAULT 'mua',"
        " note VARCHAR(255),"
        " is_active BOOLEAN NOT NULL DEFAULT 1,"
        " created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,"
        " updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP)"
    ))
    db.execute(text("CREATE UNIQUE INDEX ix_paper_sizes_code ON paper_sizes (code)"))
    db.execute(text("INSERT INTO paper_sizes (code,name,width_cm,height_cm,size_type) VALUES ('KG001','Khổ 79×109',79,109,'mua')"))
    db.execute(text("INSERT INTO paper_sizes (code,name,width_cm,height_cm,size_type) VALUES ('KG005','Khổ 39×54',39,54,'in')"))
    # OLD costing_paper_options (minimal — just needs to exist to get the 2 new columns).
    db.execute(text(
        "CREATE TABLE costing_paper_options ("
        " id INTEGER PRIMARY KEY AUTOINCREMENT,"
        " costing_id INTEGER NOT NULL,"
        " sheet_w NUMERIC(10,2) NOT NULL DEFAULT 0)"
    ))
    db.commit()
    return db


def test_migration_adds_columns_and_backfills():
    db = _old_schema_db()
    _migrate_paper_size_full_fields(db)

    insp = inspect(db.get_bind())
    cols = {c["name"] for c in insp.get_columns("paper_sizes")}
    for expected in ("size_group", "is_purchase_size", "is_print_sheet_size", "is_cut_size",
                     "allow_rotation", "compatible_machine_ids", "parent_size_id",
                     "version", "effective_from", "used_count", "created_by"):
        assert expected in cols, f"missing {expected}"

    # Backfill loại khổ từ size_type cũ.
    rows = dict(db.execute(text(
        "SELECT size_type, is_purchase_size || ',' || is_print_sheet_size FROM paper_sizes ORDER BY id"
    )).all())
    assert rows["mua"] == "1,0"   # 'mua' → khổ mua, không tờ in
    assert rows["in"] == "0,1"    # 'in' → khổ tờ in

    # costing links added.
    ccols = {c["name"] for c in insp.get_columns("costing_paper_options")}
    assert "print_sheet_size_id" in ccols and "purchase_size_id" in ccols

    # unique(code, version) index present.
    idx = {i["name"] for i in insp.get_indexes("paper_sizes")}
    assert "uq_paper_size_code_version" in idx


def test_migration_idempotent():
    db = _old_schema_db()
    _migrate_paper_size_full_fields(db)
    # Second run must be a clean no-op (columns already there, IF NOT EXISTS on indexes).
    _migrate_paper_size_full_fields(db)
    insp = inspect(db.get_bind())
    assert "version" in {c["name"] for c in insp.get_columns("paper_sizes")}
