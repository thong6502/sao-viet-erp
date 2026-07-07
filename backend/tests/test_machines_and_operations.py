"""Tests for the Operations Catalog config.

The admin/write surface of the operations catalog was removed; the router is
now read-only (GET list + GET detail) so the pricing engine / Báo giá can still
read it. Test data is therefore seeded straight through the model instead of the
(deleted) POST endpoints. The former HTTP CRUD test was deleted with the write
endpoints.
"""
from __future__ import annotations

from datetime import date

import pytest

from app.db import SessionLocal
from app.models.operation import Operation, OperationRate


@pytest.fixture
def token(client, seed_credentials) -> str:
    resp = client.post("/api/auth/login", json=seed_credentials)
    assert resp.status_code == 200
    return resp.json()["access_token"]


@pytest.fixture
def auth_headers(token) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _seed_operation() -> int:
    """Insert one operation + its current rate directly via the model.

    SessionLocal binds to the same StaticPool connection the app uses, so the
    committed row is visible to the read endpoints under test.
    """
    db = SessionLocal()
    try:
        op = Operation(
            code="CD900",
            name="Cán màng nhung",
            operation_type="can_mang",
            unit="m2",
            allow_outsource=True,
            is_active=True,
        )
        db.add(op)
        db.flush()
        db.add(
            OperationRate(
                operation_id=op.id,
                setup_fee=150000,
                run_rate=3500,
                labor_rate=500,
                min_charge=300000,
                speed=2000.0,
                effective_from=date.today(),
            )
        )
        db.commit()
        return op.id
    finally:
        db.close()


def test_operations_read_path(client, auth_headers):
    op_id = _seed_operation()

    # List returns the seeded operation.
    resp = client.get("/api/operations", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] >= 1
    assert any(x["id"] == op_id for x in body["items"])

    # Detail read works.
    resp = client.get(f"/api/operations/{op_id}", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["name"] == "Cán màng nhung"


def test_operations_write_endpoints_removed(client, auth_headers):
    op_id = _seed_operation()

    payload = {"name": "X", "operation_type": "can_mang", "unit": "m2"}

    # create / update / delete / add-rate / preview are all gone (405 on an
    # existing path with a dropped verb, 404 on a path that no longer exists).
    assert client.post(
        "/api/operations", json=payload, headers=auth_headers
    ).status_code in (404, 405)
    assert client.put(
        f"/api/operations/{op_id}", json=payload, headers=auth_headers
    ).status_code in (404, 405)
    assert client.delete(
        f"/api/operations/{op_id}", headers=auth_headers
    ).status_code in (404, 405)
    assert client.post(
        f"/api/operations/{op_id}/rates", json={}, headers=auth_headers
    ).status_code in (404, 405)
    assert client.post(
        f"/api/operations/{op_id}/preview", json={}, headers=auth_headers
    ).status_code in (404, 405)
