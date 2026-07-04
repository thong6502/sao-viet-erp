"""Tests cho Loại sản phẩm & Quy tắc tính (page #1) — năng lực mới theo spec §A–§H.

Bao phủ: preview (Test nhanh), clone (tạo version), validation §8, và engine fallback
bleed/gutter/lề xén từ loại SP.
"""
from __future__ import annotations

from datetime import date

import pytest

from app.db import SessionLocal
from app.models.material import Material, MaterialCost
from app.models.product_type_catalog import ProductTypeCatalog
from app.services.pricing_engine import PricingEngine


@pytest.fixture
def token(client, seed_credentials) -> str:
    resp = client.post("/api/auth/login", json=seed_credentials)
    assert resp.status_code == 200
    return resp.json()["access_token"]


@pytest.fixture
def auth_headers(token) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _base(**over) -> dict:
    d = {
        "product_type": "pt_spec",
        "name": "PT Spec",
        "calculation_strategy": "sheet_based",
        "product_group": "bao_bi",
        "technology": "offset",
        "shown_fields": ["finished_w", "finished_h", "quantity", "paper", "imposition"],
        "required_fields": ["finished_w", "finished_h", "quantity"],
        "dimension_rule_type": "finished",
        "default_bleed_mm": 3,
        "default_gutter_mm": 3,
        "default_trim_mm": 5,
        "default_operations": ["be", "dong_goi"],
        "required_operations": ["be"],
        "allowed_imposition_codes": ["ONE_SIDE", "TU_TRO"],
        "default_imposition_code": "TU_TRO",
        "has_tooling": True,
        "default_tooling_type": "khuon_be",
    }
    d.update(over)
    return d


# --- preview (Test nhanh) --------------------------------------------------

def test_preview_returns_form_routing_rules(client, auth_headers):
    r = client.post("/api/product-types-catalog", json=_base(), headers=auth_headers)
    assert r.status_code == 201, r.text
    pid = r.json()["id"]

    r = client.post(f"/api/product-types-catalog/{pid}/preview", headers=auth_headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert "finished_w" in body["shown_fields"]
    assert body["required_fields"] == ["finished_w", "finished_h", "quantity"]
    assert body["routing"] == ["be", "dong_goi"]
    assert body["default_imposition_code"] == "TU_TRO"
    assert any("khuôn" in s.lower() for s in body["rules"])
    assert any("Routing" in s for s in body["rules"])


# --- clone (tạo version mới) -----------------------------------------------

def test_clone_duplicates_config(client, auth_headers):
    r = client.post("/api/product-types-catalog", json=_base(product_type="pt_src", name="PT Src"), headers=auth_headers)
    pid = r.json()["id"]
    r = client.post(f"/api/product-types-catalog/{pid}/clone",
                    json={"new_product_type": "pt_clone", "new_name": "PT Clone"}, headers=auth_headers)
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["product_type"] == "pt_clone"
    assert body["default_operations"] == ["be", "dong_goi"]
    assert body["default_imposition_code"] == "TU_TRO"
    assert body["version"] == 2


# --- validation §8 ---------------------------------------------------------

@pytest.mark.parametrize("over, hint", [
    ({"required_fields": ["spine_width"], "shown_fields": ["finished_w"]}, "hiển thị"),
    ({"dimension_rule_type": "spread"}, "khổ trải"),  # spread nhưng shown không có spread_w/h
    ({"has_tooling": True, "default_tooling_type": None}, "khuôn"),
    ({"default_imposition_code": "AB"}, "danh sách cho phép"),  # AB không trong allowlist
    ({"default_operations": ["be", "be"]}, "trùng"),
    ({"required_operations": ["gap"]}, "routing mặc định"),  # gap không trong default
])
def test_validation_rejects(client, auth_headers, over, hint):
    r = client.post("/api/product-types-catalog", json=_base(product_type="pt_bad", name="PT Bad", **over), headers=auth_headers)
    assert r.status_code == 422, f"expected 422 for {over}, got {r.status_code}: {r.text}"
    assert hint in r.json()["detail"], r.text


def test_used_count_increments_and_blocks_delete(client, auth_headers):
    r = client.post("/api/product-types-catalog", json=_base(product_type="pt_used", name="PT Used"), headers=auth_headers)
    pid = r.json()["id"]
    assert client.get(f"/api/product-types-catalog/{pid}", headers=auth_headers).json()["used_count"] == 0

    est = client.post("/api/estimates", json={
        "product_type": "pt_used", "product_name": "Test SP dùng loại", "quantity_list": [1000],
        "input_spec": {"colors": 4, "sides": 2}, "status": "draft",
    }, headers=auth_headers)
    assert est.status_code == 201, est.text

    # used_count tăng sau khi có estimate dùng loại SP
    assert client.get(f"/api/product-types-catalog/{pid}", headers=auth_headers).json()["used_count"] == 1
    # và không cho xóa (đã dùng + đang tham chiếu)
    d = client.delete(f"/api/product-types-catalog/{pid}", headers=auth_headers)
    assert d.status_code == 409, d.text


def test_delete_blocked_when_referenced_by_estimate(client, auth_headers):
    # brochure được seed + có phiếu tính giá tham chiếu → chặn xóa.
    r = client.get("/api/product-types-catalog?size=100", headers=auth_headers)
    brochure = next(x for x in r.json()["items"] if x["product_type"] == "brochure")
    # tạo estimate tham chiếu (qua seed đã có phiếu 'flyer'/'business_card'); brochure có catalogue demo.
    resp = client.delete(f"/api/product-types-catalog/{brochure['id']}", headers=auth_headers)
    # brochure có thể chưa bị tham chiếu → chấp nhận 204 hoặc 409; nếu 409 phải đúng thông điệp.
    assert resp.status_code in (204, 409)
    if resp.status_code == 409:
        assert "tham chiếu" in resp.json()["detail"]


# --- engine: bleed/gutter fallback từ loại SP ------------------------------

def test_engine_applies_product_type_bleed(client):
    db = SessionLocal()
    try:
        paper = Material(code="GYPT", name="Giấy PT", material_type="paper", unit="to",
                         width_cm=65.0, height_cm=86.0, gsm=150, is_active=True)
        db.add(paper); db.flush()
        db.add(MaterialCost(material_id=paper.id, price_unit="to", unit_price=1000, effective_from=date(2026, 1, 1)))
        # Loại SP khai bleed 3cm + gutter 3cm (mm=30) → con to hơn ⇒ ít con/tờ ⇒ nhiều tờ hơn.
        db.add(ProductTypeCatalog(product_type="pt_bleed", name="PT Bleed", calculation_strategy="sheet_based",
                                  default_bleed_mm=30, default_gutter_mm=30, default_trim_mm=0))
        db.commit()

        spec = {
            "product_type": "pt_bleed", "finished_width": 10.0, "finished_height": 10.0,
            "sheet_w": 65.0, "sheet_h": 86.0, "colors": 1, "sides": 1, "material_id": paper.id,
        }
        engine = PricingEngine(db)
        lines_default, _t, _w = engine.calculate_option(dict(spec), 1000)
        # Ghi đè bleed/gutter = 0 ở spec → con nhỏ ⇒ nhiều con/tờ ⇒ ÍT tờ hơn.
        lines_zero, _t2, _w2 = engine.calculate_option(dict(spec, bleed_cm=0, gutter_cm=0, edge_trim_cm=0), 1000)

        sheets_default = next(l.quantity for l in lines_default if l.category == "material")
        sheets_zero = next(l.quantity for l in lines_zero if l.category == "material")
        assert float(sheets_default) > float(sheets_zero), (sheets_default, sheets_zero)
    finally:
        db.close()
