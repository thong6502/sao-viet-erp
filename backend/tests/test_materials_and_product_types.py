"""Tests for Materials Catalog config (read-only surface).

Đường ghi CRUD của router materials đã gỡ (chỉ còn list/detail/cost-history/toggle);
dữ liệu ghi trực tiếp qua model, test kiểm đường ĐỌC mà engine + Báo giá dựa vào.
"""
from __future__ import annotations

from datetime import date

import pytest

from app.db import SessionLocal
from app.models.material import Material, MaterialCost


@pytest.fixture
def token(client, seed_credentials) -> str:
    resp = client.post("/api/auth/login", json=seed_credentials)
    assert resp.status_code == 200
    return resp.json()["access_token"]


@pytest.fixture
def auth_headers(token) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


# --- Materials & Costs: đường ĐỌC (list/detail/stats/cost-history) ------------

def test_materials_read_list_detail_and_history(client, auth_headers):
    # Ghi thẳng qua model (router không còn create/costs) rồi kiểm đường đọc.
    db = SessionLocal()
    try:
        mat = Material(
            code="GY-RDONLY-1", name="Couche 150gsm 65x86 Test", material_type="paper",
            unit="to", min_fee=1000, width_cm=65, height_cm=86, gsm=150,
            default_waste_pct=5, min_purchase_qty=100, paper_family="Couche",
            surface="bong", is_active=True,
        )
        db.add(mat)
        db.flush()
        mid = mat.id
        # 2 bản giá "ram" khác NCC → không đụng unique index (partial theo NCC).
        db.add(MaterialCost(material_id=mid, price_unit="ram", unit_price=850000,
                            effective_from=date.today(), supplier=None))
        db.add(MaterialCost(material_id=mid, price_unit="ram", unit_price=900000,
                            effective_from=date.today(), supplier="NCC B"))
        db.commit()
    finally:
        db.close()

    # Detail.
    resp = client.get(f"/api/materials/{mid}", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["name"] == "Couche 150gsm 65x86 Test"
    assert resp.json()["code"].startswith("GY")

    # List + stats.
    resp = client.get("/api/materials", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["total"] >= 1
    assert resp.json()["stats"]["total_papers"] >= 1

    # Cost history.
    resp = client.get(f"/api/materials/{mid}/costs/history", headers=auth_headers)
    assert resp.status_code == 200
    assert len(resp.json()) >= 2
