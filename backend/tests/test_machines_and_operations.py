"""Tests for Machines and Operations Catalog configs.
"""
from __future__ import annotations

import pytest
from datetime import date, timedelta
from app.models.machine import Machine, MachineRate
from app.models.operation import Operation, OperationRate

@pytest.fixture
def token(client, seed_credentials) -> str:
    resp = client.post("/api/auth/login", json=seed_credentials)
    assert resp.status_code == 200
    return resp.json()["access_token"]

@pytest.fixture
def auth_headers(token) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}

# --- Machines tests ---------------------------------------------------------

def test_machines_crud(client, auth_headers):
    # 1. Create a machine
    payload = {
        "name": "KBA Rapida 105",
        "machine_type": "offset",
        "process_type": "in",
        "speed": 15000,
        "speed_unit": "to/gio",
        "max_width_cm": 72,
        "max_height_cm": 105,
        "min_width_cm": 35,
        "min_height_cm": 50,
        "setup_time_mins": 20,
        "changeover_time_mins": 10,
        "setup_waste_sheets": 150,
        "supported_materials": ["paper"],
        "is_active": True
    }
    resp = client.post("/api/machines", json=payload, headers=auth_headers)
    assert resp.status_code == 201
    machine_id = resp.json()["id"]
    # MY### code auto-generation
    assert resp.json()["code"].startswith("MY")

    # 2. Get detail
    resp = client.get(f"/api/machines/{machine_id}", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["name"] == "KBA Rapida 105"

    # 3. Add rate version
    today = date.today().isoformat()
    rate_payload = {
        "hourly_rate": 450000,
        "min_charge": 1000000,
        "min_run_time_mins": 30,
        "effective_from": today
    }
    resp = client.post(f"/api/machines/{machine_id}/rates", json=rate_payload, headers=auth_headers)
    assert resp.status_code == 201
    assert resp.json()["hourly_rate"] == 450000

    # 4. Check overlapping active rate
    resp = client.post(f"/api/machines/{machine_id}/rates", json=rate_payload, headers=auth_headers)
    assert resp.status_code == 422
    assert "Ngày hiệu lực mới phải sau" in resp.json()["detail"]

    # 5. List
    resp = client.get("/api/machines", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["total"] >= 1
    assert any(x["id"] == machine_id for x in resp.json()["items"])

    # 6. Delete
    resp = client.delete(f"/api/machines/{machine_id}", headers=auth_headers)
    assert resp.status_code == 204

def test_machine_speed_constraint(client, auth_headers):
    # Try creating machine with speed <= 0
    payload = {
        "name": "Bad Machine",
        "machine_type": "offset",
        "process_type": "in",
        "speed": 0,  # Fails speed > 0
        "speed_unit": "to/gio"
    }
    resp = client.post("/api/machines", json=payload, headers=auth_headers)
    assert resp.status_code == 422
    assert "greater than 0" in str(resp.json()["detail"])

# --- Operations tests -------------------------------------------------------

def test_operations_crud(client, auth_headers):
    # 1. Create an operation
    payload = {
        "name": "Cán màng nhung",
        "operation_type": "can_mang",
        "unit": "m2",
        "allow_outsource": True,
        "is_active": True
    }
    resp = client.post("/api/operations", json=payload, headers=auth_headers)
    assert resp.status_code == 201
    op_id = resp.json()["id"]
    # CD### code auto-generation
    assert resp.json()["code"].startswith("CD")

    # 2. Get detail
    resp = client.get(f"/api/operations/{op_id}", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["name"] == "Cán màng nhung"

    # 3. Add rate version
    today = date.today().isoformat()
    rate_payload = {
        "setup_fee": 150000,
        "run_rate": 3500,
        "labor_rate": 500,
        "min_charge": 300000,
        "speed": 2000.0,
        "effective_from": today
    }
    resp = client.post(f"/api/operations/{op_id}/rates", json=rate_payload, headers=auth_headers)
    assert resp.status_code == 201
    assert resp.json()["run_rate"] == 3500

    # 4. Check overlapping active rate
    resp = client.post(f"/api/operations/{op_id}/rates", json=rate_payload, headers=auth_headers)
    assert resp.status_code == 422
    assert "Ngày hiệu lực mới phải sau" in resp.json()["detail"]

    # 5. List
    resp = client.get("/api/operations", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["total"] >= 1

    # 6. Delete
    resp = client.delete(f"/api/operations/{op_id}", headers=auth_headers)
    assert resp.status_code == 204
