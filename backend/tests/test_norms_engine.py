"""Backend tests for the Norms Specificity engine (Phase 1B).
"""
from __future__ import annotations

import pytest
from datetime import date, timedelta
from app.db import SessionLocal
from app.repositories.norm_repo import NormRepository
from app.services.norm_service import (
    NormService,
    NormValidationError,
    NormNotFoundError,
    NormLookupContext,
    canonicalize_context,
)
from app.repositories.audit_repo import AuditLogRepository
from app.models.norm import Norm
from app.models.product_type_catalog import ProductTypeCatalog
from app.models.machine import Machine
from app.models.operation import Operation

class MockActor:
    def __init__(self, user_id: int = 1) -> None:
        self.id = user_id

@pytest.fixture
def service_and_actor():
    db = SessionLocal()
    repo = NormRepository(db)
    audit = AuditLogRepository(db)
    service = NormService(repo, audit)
    actor = MockActor()
    yield service, actor, db
    db.close()

def test_canonicalize_context():
    # Empty
    assert canonicalize_context(None) == "{}"
    assert canonicalize_context({}) == "{}"
    # Alphabetical sorting check
    assert canonicalize_context({"sides": 2, "colors": 4}) == "colors=4|sides=2"
    assert canonicalize_context({"colors": 4, "sides": 2}) == "colors=4|sides=2"

def test_exclusivity_check_constraint(client, service_and_actor):
    service, actor, db = service_and_actor
    
    # Try creating with both operation_id and operation_key
    with pytest.raises(NormValidationError, match="Chỉ được nhập một trong hai"):
        # The service validation throws NormValidationError
        service.create_norm(
            norm_key="yield_rate",
            value=0.95,
            operation_id=1,
            operation_key="some_key",
            effective_from=date(2026, 1, 1),
            actor=actor,
        )

def test_yield_rate_bounds_validation(client, service_and_actor):
    service, actor, db = service_and_actor
    
    # yield_rate cannot be 0
    with pytest.raises(NormValidationError, match="Tỷ lệ thành phẩm"):
        service.create_norm(
            norm_key="yield_rate",
            value=0.0,
            effective_from=date(2026, 1, 1),
            actor=actor,
        )

    # yield_rate cannot be > 1
    with pytest.raises(NormValidationError, match="Tỷ lệ thành phẩm"):
        service.create_norm(
            norm_key="yield_rate",
            value=1.05,
            effective_from=date(2026, 1, 1),
            actor=actor,
        )

def test_norm_quantity_ranges(client, service_and_actor):
    service, actor, db = service_and_actor
    
    # Rule 1: No quantity range (applies only when lookup quantity is None)
    service.create_norm(
        norm_key="running_waste_pct",
        value=0.05,
        qty_min=None,
        qty_max=None,
        effective_from=date(2026, 1, 1),
        actor=actor,
    )
    
    # Rule 2: Quantity range [100, 500]
    service.create_norm(
        norm_key="running_waste_pct",
        value=0.03,
        qty_min=100,
        qty_max=500,
        effective_from=date(2026, 1, 1),
        actor=actor,
    )

    # Rule 3: Quantity range [501, None]
    service.create_norm(
        norm_key="running_waste_pct",
        value=0.015,
        qty_min=501,
        qty_max=None,
        effective_from=date(2026, 1, 1),
        actor=actor,
    )

    # Test 1: Lookup quantity is None
    # Should match Rule 1 only
    ctx_none = NormLookupContext(quantity=None)
    val = service.get_norm("running_waste_pct", ctx_none)
    assert val == 0.05

    # Test 2: Lookup quantity is 300
    # Should match Rule 2
    ctx_300 = NormLookupContext(quantity=300)
    val = service.get_norm("running_waste_pct", ctx_300)
    assert val == 0.03

    # Test 3: Lookup quantity is 1000
    # Should match Rule 3
    ctx_1000 = NormLookupContext(quantity=1000)
    val = service.get_norm("running_waste_pct", ctx_1000)
    assert val == 0.015

def test_specificity_priority_sorting(client, service_and_actor):
    service, actor, db = service_and_actor
    
    # Create product type catalog entry for catalog checks (idempotent)
    from sqlalchemy import select
    existing = db.execute(select(ProductTypeCatalog).where(ProductTypeCatalog.product_type == "brochure")).scalar_one_or_none()
    if not existing:
        pt = ProductTypeCatalog(product_type="brochure", name="Tờ gấp", calculation_strategy="sheet_based")
        db.add(pt)
        db.commit()

    # Seed different norms with varying specificity:
    # 1. Fallback default (Score: 0)
    service.create_norm(
        norm_key="makeready_per_color_side",
        value=10.0,
        effective_from=date(2026, 1, 1),
        actor=actor,
    )
    
    # 2. Product type specific (Score: 10)
    service.create_norm(
        norm_key="makeready_per_color_side",
        value=15.0,
        product_type="brochure",
        effective_from=date(2026, 1, 1),
        actor=actor,
    )
    
    # 3. Product type + context specific (Score: 10 + 2 = 12)
    service.create_norm(
        norm_key="makeready_per_color_side",
        value=25.0,
        product_type="brochure",
        context={"colors": 4, "sides": 2},
        effective_from=date(2026, 1, 1),
        actor=actor,
    )

    # Test 1: General lookup for unknown product type
    # Should hit Default (Score 0)
    ctx_gen = NormLookupContext(product_type="book", colors=1, sides=1)
    assert service.get_norm("makeready_per_color_side", ctx_gen) == 10.0

    # Test 2: Lookup brochure with basic colors
    # Should hit brochure rule (Score 10) since context colors/sides don't matchcolors=4,sides=2
    ctx_brochure = NormLookupContext(product_type="brochure", colors=1, sides=1)
    assert service.get_norm("makeready_per_color_side", ctx_brochure) == 15.0

    # Test 3: Lookup brochure with colors=4, sides=2
    # Should hit brochure + context rule (Score 12)
    ctx_brochure_specific = NormLookupContext(product_type="brochure", colors=4, sides=2)
    assert service.get_norm("makeready_per_color_side", ctx_brochure_specific) == 25.0

def test_norm_date_overlap_validation(client, service_and_actor):
    service, actor, db = service_and_actor
    
    # Create norm starting 2026-03-01
    service.create_norm(
        norm_key="yield_rate",
        value=0.98,
        effective_from=date(2026, 3, 1),
        actor=actor,
    )
    
    # Creating a new norm backdated or equal effective_from raises validation error
    with pytest.raises(NormValidationError, match="Ngày hiệu lực mới"):
        service.create_norm(
            norm_key="yield_rate",
            value=0.99,
            effective_from=date(2026, 3, 1),
            actor=actor,
        )
