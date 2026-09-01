"""Backend test fixtures.

Runs the real app against an in-memory SQLite DB (StaticPool keeps the single
connection alive), so tests never need Postgres or Docker. Environment is set
BEFORE the app is imported so config picks it up.
"""
from __future__ import annotations

import os

# Must be set before any `app.*` import so Settings reads them.
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["JWT_SECRET"] = "test-secret"
os.environ["SEED_ADMIN_USERNAME"] = "admin"
os.environ["SEED_ADMIN_PASSWORD"] = "admin123"
os.environ["SEED_ADMIN_NAME"] = "Admin"
# Keep the test dataset minimal + deterministic regardless of any local .env
# (spec-06 demo staff/customers would otherwise break RBAC delete-guard assumptions).
os.environ["SEED_DEMO"] = "false"
# Tắt ticker nhắc lịch hẹn (SSE) trong test — tránh đụng DB in-memory + treo loop.
os.environ["CARE_REMINDER_SECONDS"] = "0"
# Hạ tầng: ÉP về chế độ offline, bất kể `backend/.env` của máy đang trỏ đi đâu.
# Rỗng ⇒ hub SSE chạy in-process (app/realtime.py), khoá thành no-op (app/locks.py), file ghi
# thẳng đĩa (app/storage.py) — đúng giả định của bộ test, và giữ CI không cần service ngoài.
# ĐÃ VỠ THẬT: máy dev trỏ REDIS_URL/MINIO_ENDPOINT vào container → 7 test đỏ vì test đi hỏi
# Redis/MinIO thật. Đừng gỡ hai dòng này.
os.environ["REDIS_URL"] = ""
os.environ["MINIO_ENDPOINT"] = ""
# Hạ bcrypt về số vòng tối thiểu — CHỈ trong test. Mỗi test seed admin (1 lượt băm) rồi đăng nhập
# (1 lượt kiểm), ở 12 vòng là ~0,9s/test tiêu vào việc băm một mật khẩu ai cũng biết là "admin123".
# Production KHÔNG hạ được: `assert_secure_config` chặn khởi động nếu BCRYPT_ROUNDS < 12.
os.environ["BCRYPT_ROUNDS"] = "4"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.db import Base, engine  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture
def client():
    # The in-memory SQLite DB is shared across the whole session (StaticPool keeps the
    # single connection alive). Wipe + recreate the schema before each test so mutating
    # tests (e.g. change-password, lock user) can't leak seeded state into later tests;
    # the lifespan below re-seeds a clean admin + RBAC catalog.
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    # `with TestClient` triggers the lifespan (init_db + seed_all).
    with TestClient(app) as c:
        yield c


@pytest.fixture
def seed_credentials() -> dict[str, str]:
    # Login is by username (spec-0001).
    return {"username": "admin", "password": "admin123"}
