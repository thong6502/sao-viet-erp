"""Backend test fixtures.

Runs the real app against an in-memory SQLite DB (StaticPool keeps the single
connection alive), so tests never need Postgres or Docker. Environment is set
BEFORE the app is imported so config picks it up.
"""
from __future__ import annotations

import os
import sqlite3

# Must be set before any `app.*` import so Settings reads them.
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["JWT_SECRET"] = "test-secret"
os.environ["SEED_ADMIN_USERNAME"] = "admin"
os.environ["SEED_ADMIN_PASSWORD"] = "admin123"
os.environ["SEED_ADMIN_NAME"] = "Admin"
# Keep the test dataset minimal + deterministic regardless of any local .env
# (spec-06 demo staff/customers would otherwise break RBAC delete-guard assumptions).
os.environ["SEED_DEMO"] = "false"
# Luật "ca phải khớp giờ công chuẩn" (07/09/2026) mặc định BẬT ở dev/prod; bộ test TẮT qua seed vì
# hàng chục test cố ý khai ca 9h/10h/24h làm số tròn (540', 600'…). Test của chính luật này bật
# lại bằng PUT /api/luong/params {"ca_khop_gio_chuan": true}.
os.environ["SEED_CA_KHOP_GIO_CHUAN"] = "false"
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

from app.db import Base, SessionLocal, engine  # noqa: E402
from app.db_migrations import run_migrations  # noqa: E402
from app.seed import seed_all  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture
def client():
    # The in-memory SQLite DB is shared across the whole session (StaticPool keeps the
    # single connection alive). Wipe the schema before each test so mutating tests (e.g.
    # change-password, lock user) can't leak seeded state into later tests.
    # Dán lại ảnh đã seed thay cho drop_all + create_all 192 bảng — xem `phien_da_seed`.
    # Lifespan bên dưới vẫn chạy init_db + run_migrations + seed_all y như thật; nó chỉ
    # rẻ đi vì mọi thứ đã có sẵn nên các bước đó thành no-op.
    _anh_da_seed().backup(_sqlite_that())
    # `with TestClient` triggers the lifespan (init_db + seed_all).
    with TestClient(app) as c:
        yield c


@pytest.fixture
def seed_credentials() -> dict[str, str]:
    # Login is by username (spec-0001).
    return {"username": "admin", "password": "admin123"}


# --- DB sạch cho mỗi test: chụp MỘT ảnh, sau đó dán đè -------------------------
# Dựng lại từ đầu tốn ~1,3s mỗi test (create_all 192 bảng ~0,35s + seed_all ~0,8s) trong khi thân
# test chỉ 0,01–0,2s — cả bộ đi ngủ ở fixture chứ không ở logic. SQLite in-memory copy được
# nguyên khối bằng `Connection.backup()` (~4ms), nên chụp một ảnh sau khi seed rồi mỗi test dán
# đè ảnh đó. Trạng thái sau khi dán y hệt trạng thái sau khi dựng, nên không test nào phải đổi
# cách viết — chỉ ruột fixture `db` của từng file đổi thành `yield from phien_da_seed()`.
_ANH: dict[str, sqlite3.Connection] = {}


def _sqlite_that() -> sqlite3.Connection:
    """Connection DBAPI thật của engine test. StaticPool ⇒ cả bộ test dùng chung đúng một cái."""
    fairy = engine.raw_connection()
    try:
        return fairy.driver_connection
    finally:
        # Trả về pool = rollback giao dịch còn dở. Còn giao dịch mở thì `backup()` báo khoá đích.
        fairy.close()


def _anh_da_seed() -> sqlite3.Connection:
    if "da_seed" not in _ANH:
        Base.metadata.drop_all(bind=engine)
        Base.metadata.create_all(bind=engine)
        s = SessionLocal()
        try:
            # `schema_migrations` do raw SQL tạo nên `drop_all` không đụng tới — trước đây nghĩa là
            # từ test thứ HAI trở đi migrations bị bỏ qua. Ảnh chụp giữ luôn cả bảng đó, nên mọi
            # test giờ đều đứng trên cùng một lượt migrations đã chạy thật.
            run_migrations(s)
            seed_all(s)
            s.commit()
        finally:
            s.close()
        anh = sqlite3.connect(":memory:")
        _sqlite_that().backup(anh)
        _ANH["da_seed"] = anh
    return _ANH["da_seed"]


def phien_da_seed():
    """Phiên trên DB vừa seed xong. Dùng trong fixture: `yield from phien_da_seed()`."""
    _anh_da_seed().backup(_sqlite_that())
    s = SessionLocal()
    try:
        yield s
    finally:
        s.close()
