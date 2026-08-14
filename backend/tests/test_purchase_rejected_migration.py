"""Dữ liệu YCMH cũ không được mở lại khi PMH bị Kế toán từ chối."""
from __future__ import annotations

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.db_migrations import _migrate_rejected_pmh_keeps_ycmh_reserved


def test_migration_giu_lai_ycmh_cua_pmh_bi_tu_choi_va_co_lich_su():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    with engine.begin() as connection:
        connection.execute(text(
            "CREATE TABLE department_purchase_requests ("
            "id INTEGER PRIMARY KEY, status VARCHAR(24) NOT NULL, updated_at TIMESTAMP)"
        ))
        connection.execute(text(
            "CREATE TABLE purchase_requests (id INTEGER PRIMARY KEY, status VARCHAR(24) NOT NULL)"
        ))
        connection.execute(text(
            "CREATE TABLE purchase_request_sources ("
            "purchase_request_id INTEGER NOT NULL, department_request_id INTEGER NOT NULL)"
        ))
        connection.execute(text(
            "CREATE TABLE purchase_status_history ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, doc_type VARCHAR(8) NOT NULL, "
            "doc_id INTEGER NOT NULL, from_status VARCHAR(24), to_status VARCHAR(24) NOT NULL, "
            "changed_by_user_id INTEGER, source VARCHAR(8) NOT NULL, reason TEXT, "
            "created_at TIMESTAMP NOT NULL)"
        ))
        connection.execute(text(
            "INSERT INTO department_purchase_requests (id, status) "
            "VALUES (1, 'open'), (2, 'open')"
        ))
        connection.execute(text(
            "INSERT INTO purchase_requests (id, status) VALUES (10, 'rejected'), (20, 'cancelled')"
        ))
        connection.execute(text(
            "INSERT INTO purchase_request_sources (purchase_request_id, department_request_id) "
            "VALUES (10, 1), (20, 2)"
        ))

    with Session(engine) as db:
        _migrate_rejected_pmh_keeps_ycmh_reserved(db)
        _migrate_rejected_pmh_keeps_ycmh_reserved(db)
        statuses = dict(db.execute(text(
            "SELECT id, status FROM department_purchase_requests ORDER BY id"
        )).all())
        histories = db.execute(text(
            "SELECT doc_id, from_status, to_status, source FROM purchase_status_history"
        )).all()

    assert statuses == {1: "pending_approval", 2: "open"}
    assert histories == [(1, "open", "pending_approval", "may")]
