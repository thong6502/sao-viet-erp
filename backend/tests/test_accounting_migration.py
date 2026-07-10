"""Regression coverage for additive Accounting schema migrations."""
from __future__ import annotations

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session

from app.db_migrations import _migrate_payment_voucher_amount_vnd


def test_payment_voucher_amount_vnd_migration_backfills_existing_rows():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    with engine.begin() as connection:
        connection.execute(text(
            "CREATE TABLE payment_vouchers ("
            "id INTEGER PRIMARY KEY, amount BIGINT NOT NULL, "
            "exchange_rate NUMERIC(18,6) NOT NULL)"
        ))
        connection.execute(text(
            "INSERT INTO payment_vouchers (id, amount, exchange_rate) "
            "VALUES (1, 100, 20000), (2, 500000, 1)"
        ))

    with Session(engine) as db:
        _migrate_payment_voucher_amount_vnd(db)
        _migrate_payment_voucher_amount_vnd(db)
        rows = db.execute(text(
            "SELECT id, amount_vnd FROM payment_vouchers ORDER BY id"
        )).all()

    columns = {column["name"] for column in inspect(engine).get_columns("payment_vouchers")}
    assert "amount_vnd" in columns
    assert rows == [(1, 2_000_000), (2, 500_000)]
