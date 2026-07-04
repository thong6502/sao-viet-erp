"""Integration tests for click_ink_rates, plate_die_rates, and norms APIs (Phase 1B).
"""
from __future__ import annotations

import pytest
from datetime import date, timedelta

@pytest.fixture
def token(client, seed_credentials) -> str:
    resp = client.post("/api/auth/login", json=seed_credentials)
    assert resp.status_code == 200
    return resp.json()["access_token"]

@pytest.fixture
def auth_headers(token) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}

# --- ClickInkRates API tests ------------------------------------------------

def test_click_ink_rates_api_crud(client, auth_headers):
    # 1. Create a rate
    payload = {
        "technology": "digital",
        "color_type": "cmyk",
        "machine_id": None,
        "unit": "click",
        "unit_price": 400,
        "setup_fee": 15000,
        "min_charge": 5000,
        "effective_from": str(date.today()),
    }
    resp = client.post("/api/click-ink-rates", json=payload, headers=auth_headers)
    assert resp.status_code == 201
    rate_id = resp.json()["id"]
    assert resp.json()["unit_price"] == 400

    # 2. List rates
    resp = client.get("/api/click-ink-rates?technology=digital", headers=auth_headers)
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert len(items) >= 1
    assert items[0]["id"] == rate_id

    # 3. Close the rate
    close_payload = {
        "effective_to": str(date.today() + timedelta(days=10))
    }
    resp = client.post(f"/api/click-ink-rates/{rate_id}/close", json=close_payload, headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["effective_to"] == str(date.today() + timedelta(days=10))

    # 4. Attempt to delete (should fail because it's already active)
    resp = client.delete(f"/api/click-ink-rates/{rate_id}", headers=auth_headers)
    assert resp.status_code == 422
    assert "Không thể xóa cứng" in resp.json()["detail"]


# --- PlateDieRates API tests ------------------------------------------------

def test_plate_die_rates_api_crud(client, auth_headers):
    # 1. Create a rate
    payload = {
        "code": "PLATE_API_T",
        "name": "Kẽm API test",
        "plate_type": "ban_kem_offset",
        "technology": "offset",
        "unit": "ban",
        "unit_price": 120000,
        "setup_fee": 0,
        "min_charge": 0,
        "reusable": False,
        "effective_from": str(date.today() + timedelta(days=5)), # future rate
    }
    resp = client.post("/api/plate-die-rates", json=payload, headers=auth_headers)
    assert resp.status_code == 201
    rate_id = resp.json()["id"]
    assert resp.json()["unit_price"] == 120000

    # 2. List rates
    resp = client.get("/api/plate-die-rates?plate_type=ban_kem_offset", headers=auth_headers)
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert len(items) >= 1

    # 3. Delete future rate (should succeed)
    resp = client.delete(f"/api/plate-die-rates/{rate_id}", headers=auth_headers)
    assert resp.status_code == 204


# --- Norms API tests --------------------------------------------------------

def test_norms_api_crud(client, auth_headers):
    # 1. Create a norm
    payload = {
        "norm_key": "yield_rate",
        "value": 0.97,
        "product_type": None,
        "machine_id": None,
        "operation_id": None,
        "qty_min": None,
        "qty_max": None,
        "context": None,
        "effective_from": str(date.today() + timedelta(days=2)),
        "note": "Standard yield rate"
    }
    resp = client.post("/api/norms", json=payload, headers=auth_headers)
    assert resp.status_code == 201
    norm_id = resp.json()["id"]
    assert resp.json()["value"] == 0.97

    # 2. List norms
    resp = client.get("/api/norms?norm_key=yield_rate", headers=auth_headers)
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert len(items) >= 1

    # 3. Close the norm
    close_payload = {
        "effective_to": str(date.today() + timedelta(days=5))
    }
    resp = client.post(f"/api/norms/{norm_id}/close", json=close_payload, headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["effective_to"] == str(date.today() + timedelta(days=5))

    # 4. Attempt to delete active/past (should fail because it's effective in future/past and is protected or already active)
    # Actually let's test a future norm deletion:
    future_payload = {
        "norm_key": "running_waste_pct",
        "value": 0.02,
        "effective_from": str(date.today() + timedelta(days=30)), # far future
    }
    resp = client.post("/api/norms", json=future_payload, headers=auth_headers)
    assert resp.status_code == 201
    future_id = resp.json()["id"]
    
    resp = client.delete(f"/api/norms/{future_id}", headers=auth_headers)
    assert resp.status_code == 204
