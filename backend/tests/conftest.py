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

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402


@pytest.fixture
def client():
    # `with TestClient` triggers the lifespan (init_db + seed_admin).
    with TestClient(app) as c:
        yield c


@pytest.fixture
def seed_credentials() -> dict[str, str]:
    # Login is by username (spec-0001).
    return {"username": "admin", "password": "admin123"}
