"""Regression cho DB đã tạo bảng thông báo trước khi có người nhận đích danh."""
from __future__ import annotations

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session

from app.db_migrations import _migrate_module_notification_recipient


def test_migration_bo_sung_recipient_cho_bang_thong_bao_da_ton_tai():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE users (id INTEGER PRIMARY KEY)"))
        connection.execute(text(
            "CREATE TABLE module_notifications ("
            "id INTEGER PRIMARY KEY, channel VARCHAR(32) NOT NULL, "
            "event_type VARCHAR(64) NOT NULL, source_code VARCHAR(64), "
            "actor_user_id INTEGER REFERENCES users(id), created_at TIMESTAMP NOT NULL)"
        ))
        connection.execute(text("INSERT INTO users (id) VALUES (1)"))

    with Session(engine) as db:
        _migrate_module_notification_recipient(db)
        _migrate_module_notification_recipient(db)
        db.execute(text(
            "INSERT INTO module_notifications "
            "(id, channel, event_type, recipient_user_id, created_at) "
            "VALUES (1, 'thu_mua', 'purchase_decision', 1, CURRENT_TIMESTAMP)"
        ))
        db.commit()
        recipient = db.execute(text(
            "SELECT recipient_user_id FROM module_notifications WHERE id = 1"
        )).scalar_one()

    insp = inspect(engine)
    columns = {column["name"] for column in insp.get_columns("module_notifications")}
    indexes = {index["name"] for index in insp.get_indexes("module_notifications")}
    assert "recipient_user_id" in columns
    assert "ix_module_notifications_recipient_user_id" in indexes
    assert recipient == 1


def test_migration_recipient_bo_qua_khi_bang_chua_ton_tai():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    with Session(engine) as db:
        _migrate_module_notification_recipient(db)
