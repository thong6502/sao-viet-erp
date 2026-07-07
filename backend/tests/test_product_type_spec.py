"""Tests cho Loại sản phẩm & Quy tắc tính (page #1) — engine fallback bleed/gutter/lề xén.

Các test cho write HTTP endpoints (create/update/delete/preview/clone/validation §8) đã bỏ
cùng với admin surface của module; chỉ còn read path + engine. Giữ test engine dùng
service/DB trực tiếp (không qua endpoint ghi).
"""
from __future__ import annotations

from datetime import date

from app.db import SessionLocal
from app.models.material import Material, MaterialCost
from app.models.product_type_catalog import ProductTypeCatalog
from app.services.pricing_engine import PricingEngine


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
