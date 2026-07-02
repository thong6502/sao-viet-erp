"""Backend tests for Click/Ink Rates (Phase 1B).
"""
from __future__ import annotations

import pytest
from datetime import date, timedelta
from app.db import SessionLocal
from app.repositories.click_ink_rate_repo import ClickInkRateRepository
from app.services.click_ink_rate_service import (
    ClickInkRateService,
    ClickInkRateValidationError,
    ClickInkRateNotFoundError,
)
from app.repositories.audit_repo import AuditLogRepository
from app.models.user import User

class MockActor:
    def __init__(self, user_id: int = 1) -> None:
        self.id = user_id

@pytest.fixture
def service_and_actor():
    db = SessionLocal()
    repo = ClickInkRateRepository(db)
    audit = AuditLogRepository(db)
    service = ClickInkRateService(repo, audit)
    actor = MockActor()
    yield service, actor
    db.close()

def test_create_click_ink_rate(client, service_and_actor):
    service, actor = service_and_actor
    
    # Create digital grayscale click rate
    rate = service.create_rate(
        technology="digital",
        color_type="grayscale",
        unit="click",
        unit_price=250,
        setup_fee=10000,
        min_charge=5000,
        effective_from=date(2026, 1, 1),
        actor=actor,
    )
    assert rate.id is not None
    assert rate.technology == "digital"
    assert rate.color_type == "grayscale"
    assert rate.unit == "click"
    assert rate.unit_price == 250
    assert rate.setup_fee == 10000
    assert rate.min_charge == 5000
    assert rate.effective_from == date(2026, 1, 1)
    assert rate.effective_to is None
    assert rate.is_active is True

def test_validation_invalid_technology(client, service_and_actor):
    service, actor = service_and_actor
    with pytest.raises(ClickInkRateValidationError, match="Công nghệ"):
        service.create_rate(
            technology="laser_print",
            color_type="grayscale",
            unit="click",
            unit_price=250,
            effective_from=date(2026, 1, 1),
            actor=actor,
        )

def test_validation_invalid_color_type(client, service_and_actor):
    service, actor = service_and_actor
    with pytest.raises(ClickInkRateValidationError, match="Loại màu"):
        service.create_rate(
            technology="digital",
            color_type="rgb",
            unit="click",
            unit_price=250,
            effective_from=date(2026, 1, 1),
            actor=actor,
        )

def test_validation_invalid_unit(client, service_and_actor):
    service, actor = service_and_actor
    with pytest.raises(ClickInkRateValidationError, match="Đơn vị tính"):
        service.create_rate(
            technology="digital",
            color_type="cmyk",
            unit="kilogram",
            unit_price=250,
            effective_from=date(2026, 1, 1),
            actor=actor,
        )

def test_validation_negative_values(client, service_and_actor):
    service, actor = service_and_actor
    with pytest.raises(ClickInkRateValidationError, match="không được âm"):
        service.create_rate(
            technology="digital",
            color_type="cmyk",
            unit="click",
            unit_price=-10,
            effective_from=date(2026, 1, 1),
            actor=actor,
        )

def test_add_row_close_old_consecutive(client, service_and_actor):
    service, actor = service_and_actor
    
    # 1. Create original rate
    rate1 = service.create_rate(
        technology="digital",
        color_type="cmyk",
        unit="click",
        unit_price=500,
        effective_from=date(2026, 1, 1),
        actor=actor,
    )
    
    # 2. Create updated rate starting 2026-03-01
    rate2 = service.create_rate(
        technology="digital",
        color_type="cmyk",
        unit="click",
        unit_price=600,
        effective_from=date(2026, 3, 1),
        actor=actor,
    )
    
    # Refresh rate1 from DB
    rate1_refreshed = service.get_rate(rate1.id)
    assert rate1_refreshed.effective_to == date(2026, 3, 1) # closed at exclusive effective_from
    assert rate2.effective_to is None # active
    
    # Check rate at different dates
    rate_jan = service.repo.get_rate_at_date("digital", "cmyk", None, "click", date(2026, 1, 15))
    assert rate_jan.unit_price == 500
    
    rate_mar = service.repo.get_rate_at_date("digital", "cmyk", None, "click", date(2026, 3, 15))
    assert rate_mar.unit_price == 600

def test_validation_date_overlap(client, service_and_actor):
    service, actor = service_and_actor
    
    service.create_rate(
        technology="digital",
        color_type="cmyk",
        unit="click",
        unit_price=500,
        effective_from=date(2026, 2, 1),
        actor=actor,
    )
    
    # Adding a rate backdated or equal effective_from raises validation error
    with pytest.raises(ClickInkRateValidationError, match="Ngày hiệu lực mới"):
        service.create_rate(
            technology="digital",
            color_type="cmyk",
            unit="click",
            unit_price=600,
            effective_from=date(2026, 2, 1),
            actor=actor,
        )

def test_delete_rates_retroactivity(client, service_and_actor):
    service, actor = service_and_actor
    today = date.today()
    
    # 1. Past/active rate cannot be hard deleted
    past_rate = service.create_rate(
        technology="digital",
        color_type="cmyk",
        unit="click",
        unit_price=500,
        effective_from=today - timedelta(days=5),
        actor=actor,
    )
    with pytest.raises(ClickInkRateValidationError, match="Không thể xóa cứng"):
        service.delete_rate(rate_id=past_rate.id, actor=actor)
        
    # 2. Future rate can be hard deleted
    future_rate = service.create_rate(
        technology="digital",
        color_type="cmyk",
        unit="click",
        unit_price=550,
        effective_from=today + timedelta(days=5),
        actor=actor,
    )
    service.delete_rate(rate_id=future_rate.id, actor=actor)
    with pytest.raises(ClickInkRateNotFoundError):
        service.get_rate(future_rate.id)
