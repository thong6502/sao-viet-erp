"""Tests for Materials and Product Types Catalog config.
"""
from __future__ import annotations

import pytest
from datetime import date, timedelta
from app.models.material import Material, MaterialCost
from app.models.product_type_catalog import ProductTypeCatalog

@pytest.fixture
def token(client, seed_credentials) -> str:
    resp = client.post("/api/auth/login", json=seed_credentials)
    assert resp.status_code == 200
    return resp.json()["access_token"]

@pytest.fixture
def auth_headers(token) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}

# --- ProductTypeCatalog tests -----------------------------------------------

def test_product_type_catalog_crud(client, auth_headers):
    # 1. Create product type config
    payload = {
        "product_type": "flyer_test",
        "name": "Tờ rơi Test",
        "calculation_strategy": "sheet_based",
        "required_fields": ["gsm", "finished_w", "finished_h"],
        "default_operations": [],
        "allowed_materials": ["paper"],
        "compatible_technologies": ["offset", "digital"],
        "is_active": True
    }
    resp = client.post("/api/product-types-catalog", json=payload, headers=auth_headers)
    assert resp.status_code == 201
    item_id = resp.json()["id"]
    assert resp.json()["product_type"] == "flyer_test"

    # 2. Get detail
    resp = client.get(f"/api/product-types-catalog/{item_id}", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["calculation_strategy"] == "sheet_based"

    # 3. Update
    update_payload = {
        "name": "Tờ rơi in màu",
        "calculation_strategy": "page_based",
        "required_fields": ["gsm"],
        "is_active": False
    }
    resp = client.put(f"/api/product-types-catalog/{item_id}", json=update_payload, headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["name"] == "Tờ rơi in màu"
    assert resp.json()["calculation_strategy"] == "page_based"
    assert resp.json()["is_active"] is False

    # 4. List configs
    resp = client.get("/api/product-types-catalog", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["total"] >= 1
    assert any(x["product_type"] == "flyer_test" for x in resp.json()["items"])

    # 5. Delete
    resp = client.delete(f"/api/product-types-catalog/{item_id}", headers=auth_headers)
    assert resp.status_code == 204

    # Get should be 404 now
    resp = client.get(f"/api/product-types-catalog/{item_id}", headers=auth_headers)
    assert resp.status_code == 404

def test_product_type_catalog_validation(client, auth_headers):
    # Invalid calculation strategy
    payload = {
        "product_type": "brochure_test",
        "name": "Brochure Test",
        "calculation_strategy": "invalid_strategy"
    }
    resp = client.post("/api/product-types-catalog", json=payload, headers=auth_headers)
    assert resp.status_code == 422
    assert "Chiến lược tính giá không hợp lệ" in resp.json()["detail"]

    # Duplicate product_type
    payload["calculation_strategy"] = "sheet_based"
    resp = client.post("/api/product-types-catalog", json=payload, headers=auth_headers)
    assert resp.status_code == 201
    
    # Try creating duplicate
    resp = client.post("/api/product-types-catalog", json=payload, headers=auth_headers)
    assert resp.status_code == 409

# --- Materials & Costs tests -----------------------------------------------

def test_materials_crud(client, auth_headers):
    # 1. Create a paper material
    paper_payload = {
        "name": "Couche 150gsm 65x86 Test",
        "material_type": "paper",
        "unit": "to",
        "min_fee": 1000,
        "width_cm": 65,
        "height_cm": 86,
        "gsm": 150,
        "default_waste_pct": 5,
        "min_purchase_qty": 100,
        "paper_family": "Couche",
        "surface": "bong",
        "is_active": True
    }
    resp = client.post("/api/materials", json=paper_payload, headers=auth_headers)
    assert resp.status_code == 201
    material_id = resp.json()["id"]
    # GY### code auto-generation
    assert resp.json()["code"].startswith("GY")

    # 2. Get detail
    resp = client.get(f"/api/materials/{material_id}", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["name"] == "Couche 150gsm 65x86 Test"

    # 3. Add pricing version
    today = date.today().isoformat()
    price_payload = {
        "price_unit": "ram",
        "unit_price": 850000,
        "effective_from": today
    }
    resp = client.post(f"/api/materials/{material_id}/costs", json=price_payload, headers=auth_headers)
    assert resp.status_code == 201
    assert resp.json()["unit_price"] == 850000

    # 4. Check overlapping active price
    # Adding a price starting today or earlier should overlap/fail
    resp = client.post(f"/api/materials/{material_id}/costs", json=price_payload, headers=auth_headers)
    assert resp.status_code == 422
    assert "Ngày hiệu lực mới phải sau" in resp.json()["detail"]

    # Add a future price
    tomorrow = (date.today() + timedelta(days=2)).isoformat()
    future_price_payload = {
        "price_unit": "ram",
        "unit_price": 900000,
        "effective_from": tomorrow
    }
    resp = client.post(f"/api/materials/{material_id}/costs", json=future_price_payload, headers=auth_headers)
    assert resp.status_code == 201

    # 5. List and stats
    resp = client.get("/api/materials", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["total"] >= 1
    assert resp.json()["stats"]["total_papers"] >= 1

    # 6. Clone paper
    clone_payload = {
        "gsm": 200,
        "width_cm": 79,
        "height_cm": 109
    }
    resp = client.post(f"/api/materials/{material_id}/clone", json=clone_payload, headers=auth_headers)
    assert resp.status_code == 201
    assert resp.json()["gsm"] == 200
    assert resp.json()["width_cm"] == 79
    assert resp.json()["code"].startswith("GY")
    clone_id = resp.json()["id"]

    # 7. Delete material — SEAM-22 đã back-fill (Kho P0): vật tư KHÔNG có tồn trong Kho
    # thì xóa được. (Nếu có lô/sổ tồn thì bị chặn 422 "đang được sử dụng trong Kho".)
    resp = client.delete(f"/api/materials/{material_id}", headers=auth_headers)
    assert resp.status_code in (200, 204)

    # Toggle active vẫn hoạt động (thử trên bản clone).
    resp = client.patch(f"/api/materials/{clone_id}/toggle-active", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["is_active"] is False

def test_paper_dimensions_convention(client, auth_headers):
    # Try creating paper where width > height (fails width <= height convention)
    bad_paper = {
        "name": "Ivory 300gsm 109x79",
        "material_type": "paper",
        "unit": "to",
        "width_cm": 109,
        "height_cm": 79,
        "gsm": 300,
        "paper_family": "Ivory"
    }
    resp = client.post("/api/materials", json=bad_paper, headers=auth_headers)
    assert resp.status_code == 422
    assert "Cạnh ngắn viết trước" in resp.json()["detail"]
