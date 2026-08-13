"""Regression coverage for additive Accounting schema migrations."""
from __future__ import annotations

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session

from app.db_migrations import (
    _migrate_payment_doc_no_and_accounts,
    _migrate_payment_voucher_amount_vnd,
    _migrate_sales_invoices_legacy_compat,
)
from app.models.document_sequence import SEQ_YEAR_GLOBAL


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


def _legacy_payment_db(voucher_rows: int = 0, receipt_rows: int = 0):
    """DB kiểu 'đã chạy trước migration 0040': bảng chưa có doc_no/định khoản."""
    engine = create_engine("sqlite+pysqlite:///:memory:")
    with engine.begin() as c:
        c.execute(text("CREATE TABLE payment_vouchers (id INTEGER PRIMARY KEY, code VARCHAR(32))"))
        c.execute(text("CREATE TABLE payment_receipts (id INTEGER PRIMARY KEY, code VARCHAR(32))"))
        c.execute(text(
            "CREATE TABLE document_sequences (doc_type VARCHAR(32), year INTEGER, "
            "current_number INTEGER NOT NULL, PRIMARY KEY (doc_type, year))"
        ))
        for i in range(1, voucher_rows + 1):
            c.execute(text("INSERT INTO payment_vouchers (id, code) VALUES (:i, :c)"),
                      {"i": i, "c": f"PC-2607{i:02d}-XXXX"})
        for i in range(1, receipt_rows + 1):
            c.execute(text("INSERT INTO payment_receipts (id, code) VALUES (:i, :c)"),
                      {"i": i, "c": f"PT-2607{i:02d}-XXXX"})
    return engine


def _counter(db, doc_type: str):
    return db.execute(
        text("SELECT current_number FROM document_sequences WHERE doc_type = :t AND year = :y"),
        {"t": doc_type, "y": SEQ_YEAR_GLOBAL},
    ).scalar()


def test_doc_no_migration_backfills_and_seeds_counter():
    engine = _legacy_payment_db(voucher_rows=3, receipt_rows=1)
    with Session(engine) as db:
        _migrate_payment_doc_no_and_accounts(db)
        _migrate_payment_doc_no_and_accounts(db)  # idempotent: chạy 2 lần không đổi kết quả
        vouchers = db.execute(text("SELECT id, doc_no FROM payment_vouchers ORDER BY id")).all()
        receipts = db.execute(text("SELECT id, doc_no FROM payment_receipts ORDER BY id")).all()
        assert _counter(db, "payment_voucher") == 3
        assert _counter(db, "payment_receipt") == 1

    assert vouchers == [(1, "PC00001"), (2, "PC00002"), (3, "PC00003")]
    assert receipts == [(1, "PT00001")]

    insp = inspect(engine)
    columns = {c["name"] for c in insp.get_columns("payment_vouchers")}
    assert {"doc_no", "debit_account", "credit_account"} <= columns
    assert "payer_address" in {c["name"] for c in insp.get_columns("payment_receipts")}
    # ALTER ADD COLUMN không tạo index — migration phải tự tạo.
    indexes = {i["name"] for i in insp.get_indexes("payment_vouchers")}
    assert "ix_payment_vouchers_doc_no" in indexes


def test_doc_no_migration_noop_on_empty_tables():
    """DB rỗng (fresh) → KHÔNG tạo dòng bộ đếm, phiếu đầu tiên vẫn ra PC00001."""
    engine = _legacy_payment_db()
    with Session(engine) as db:
        _migrate_payment_doc_no_and_accounts(db)
        assert _counter(db, "payment_voucher") is None
        assert _counter(db, "payment_receipt") is None


def test_doc_no_migration_does_not_rewind_counter():
    """Bộ đếm đang cao hơn (phiếu cũ đã bị xóa) → không được tụt số."""
    engine = _legacy_payment_db(voucher_rows=2)
    with Session(engine) as db:
        db.execute(
            text(
                "INSERT INTO document_sequences (doc_type, year, current_number) "
                "VALUES ('payment_voucher', :y, 10)"
            ),
            {"y": SEQ_YEAR_GLOBAL},
        )
        db.commit()
        _migrate_payment_doc_no_and_accounts(db)
        rows = db.execute(text("SELECT doc_no FROM payment_vouchers ORDER BY id")).all()
        assert [r[0] for r in rows] == ["PC00011", "PC00012"]  # nối tiếp, không đè
        assert _counter(db, "payment_voucher") == 12


def test_sales_invoice_legacy_migration_backfills_current_ar_columns():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    with engine.begin() as connection:
        connection.execute(text(
            "CREATE TABLE sales_invoices ("
            "id INTEGER PRIMARY KEY, code VARCHAR(32) NOT NULL UNIQUE, "
            "invoice_series VARCHAR(20), invoice_no VARCHAR(32), "
            "payment_term_days INTEGER, customer_name_snapshot VARCHAR(255), "
            "created_at TIMESTAMP, subtotal_vnd BIGINT NOT NULL, "
            "vat_vnd BIGINT NOT NULL, amount_vnd BIGINT NOT NULL)"
        ))
        connection.execute(text(
            "INSERT INTO sales_invoices "
            "(id, code, invoice_series, invoice_no, payment_term_days, "
            "customer_name_snapshot, created_at, subtotal_vnd, vat_vnd, amount_vnd) "
            "VALUES (1, 'HDB-0001', '1C26TAA', '000001', 30, 'Khách A', "
            "CURRENT_TIMESTAMP, 1000000, 100000, 1100000)"
        ))

    with Session(engine) as db:
        _migrate_sales_invoices_legacy_compat(db)
        _migrate_sales_invoices_legacy_compat(db)
        row = db.execute(text(
            "SELECT invoice_symbol, invoice_number, payment_term_days_snapshot, "
            "customer_name_snapshot, updated_at FROM sales_invoices WHERE id = 1"
        )).one()

    assert row.invoice_symbol == "1C26TAA"
    assert row.invoice_number == "000001"
    assert row.payment_term_days_snapshot == 30
    assert row.customer_name_snapshot == "Khách A"
    assert row.updated_at is not None
    indexes = {item["name"] for item in inspect(engine).get_indexes("sales_invoices")}
    assert "uq_sales_invoice_symbol_number" in indexes
