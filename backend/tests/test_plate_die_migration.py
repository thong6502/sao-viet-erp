"""Migration 0008 — patch plate_die_rates schema CŨ tiến lên full spec + operations.tooling_rate_id.

Backfill code/name từ plate_type, đổi unique 'bản mở' → (code), thêm tooling_rate_id; idempotent.
"""
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db_migrations import _migrate_plate_die_full_fields


def _old_db():
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    db = sessionmaker(bind=eng)()
    db.execute(text(
        "CREATE TABLE plate_die_rates ("
        " id INTEGER PRIMARY KEY AUTOINCREMENT,"
        " plate_type VARCHAR(32) NOT NULL, technology VARCHAR(32) NOT NULL, unit VARCHAR(16) NOT NULL,"
        " unit_price BIGINT NOT NULL, setup_fee BIGINT NOT NULL DEFAULT 0,"
        " min_charge BIGINT NOT NULL DEFAULT 0, reusable BOOLEAN NOT NULL DEFAULT 0,"
        " effective_from DATE NOT NULL, effective_to DATE, is_active BOOLEAN NOT NULL DEFAULT 1)"
    ))
    db.execute(text(
        "CREATE UNIQUE INDEX uix_plate_die_rates_current ON plate_die_rates "
        "(plate_type, technology, unit) WHERE effective_to IS NULL"
    ))
    db.execute(text("INSERT INTO plate_die_rates (plate_type,technology,unit,unit_price,effective_from) "
                    "VALUES ('ban_kem_offset','offset','ban',150000,'2026-01-01')"))
    db.execute(text("INSERT INTO plate_die_rates (plate_type,technology,unit,unit_price,effective_from) "
                    "VALUES ('khuon_be','be','bo',450000,'2026-01-01')"))
    db.execute(text(
        "CREATE TABLE operations (id INTEGER PRIMARY KEY AUTOINCREMENT, code VARCHAR(20) NOT NULL,"
        " name VARCHAR(255) NOT NULL, operation_type VARCHAR(32) NOT NULL, unit VARCHAR(16) NOT NULL)"
    ))
    db.commit()
    return db


def test_migration_adds_columns_and_backfills():
    db = _old_db()
    _migrate_plate_die_full_fields(db)
    insp = inspect(db.get_bind())
    cols = {c["name"] for c in insp.get_columns("plate_die_rates")}
    for c in ("code", "name", "pricing_method", "machine_ids", "unit_price_area",
              "reuse_price_method", "maintenance_fee", "supplier", "used_count", "created_by"):
        assert c in cols, f"missing {c}"
    # code/name backfilled from plate_type
    rows = dict(db.execute(text("SELECT plate_type, code FROM plate_die_rates")).all())
    assert rows["ban_kem_offset"] == "BAN_KEM_OFFSET"
    assert rows["khuon_be"] == "KHUON_BE"
    # unique index now on (code)
    idx = {i["name"]: i for i in insp.get_indexes("plate_die_rates")}
    assert "uix_plate_die_rates_current" in idx
    assert idx["uix_plate_die_rates_current"]["column_names"] == ["code"]
    # operations.tooling_rate_id
    assert "tooling_rate_id" in {c["name"] for c in insp.get_columns("operations")}


def test_migration_idempotent():
    db = _old_db()
    _migrate_plate_die_full_fields(db)
    _migrate_plate_die_full_fields(db)
    assert "code" in {c["name"] for c in inspect(db.get_bind()).get_columns("plate_die_rates")}
