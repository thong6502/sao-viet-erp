"""Backend tests for Plate/Die Rates (Phase 1B).
"""
from __future__ import annotations

import pytest
from datetime import date, timedelta
from app.db import SessionLocal
from app.repositories.plate_die_rate_repo import PlateDieRateRepository
from app.services.plate_die_rate_service import (
    PlateDieRateService,
    PlateDieRateValidationError,
    PlateDieRateNotFoundError,
)
from app.repositories.audit_repo import AuditLogRepository

class MockActor:
    def __init__(self, user_id: int = 1) -> None:
        self.id = user_id

@pytest.fixture
def service_and_actor():
    db = SessionLocal()
    repo = PlateDieRateRepository(db)
    audit = AuditLogRepository(db)
    service = PlateDieRateService(repo, audit)
    actor = MockActor()
    yield service, actor
    db.close()

def test_create_plate_die_rate(client, service_and_actor):
    service, actor = service_and_actor
    
    rate = service.create_rate(
        plate_type="ban_kem_offset",
        technology="offset",
        unit="ban",
        unit_price=120000,
        setup_fee=0,
        min_charge=0,
        reusable=False,
        effective_from=date(2026, 1, 1),
        actor=actor,
    )
    assert rate.id is not None
    assert rate.plate_type == "ban_kem_offset"
    assert rate.technology == "offset"
    assert rate.unit == "ban"
    assert rate.unit_price == 120000
    assert rate.effective_from == date(2026, 1, 1)
    assert rate.effective_to is None
    assert rate.is_active is True

def test_validation_invalid_plate_type(client, service_and_actor):
    service, actor = service_and_actor
    with pytest.raises(PlateDieRateValidationError, match="Loại khuôn/bản"):
        service.create_rate(
            plate_type="laser_plate",
            technology="offset",
            unit="ban",
            unit_price=120000,
            effective_from=date(2026, 1, 1),
            actor=actor,
        )

def test_validation_invalid_technology(client, service_and_actor):
    service, actor = service_and_actor
    with pytest.raises(PlateDieRateValidationError, match="Công nghệ gia công"):
        service.create_rate(
            plate_type="ban_kem_offset",
            technology="laser",
            unit="ban",
            unit_price=120000,
            effective_from=date(2026, 1, 1),
            actor=actor,
        )

def test_validation_invalid_unit(client, service_and_actor):
    service, actor = service_and_actor
    with pytest.raises(PlateDieRateValidationError, match="Đơn vị tính"):
        service.create_rate(
            plate_type="ban_kem_offset",
            technology="offset",
            unit="kilogram",
            unit_price=120000,
            effective_from=date(2026, 1, 1),
            actor=actor,
        )

def test_add_row_close_old_consecutive(client, service_and_actor):
    service, actor = service_and_actor
    
    # 1. Create original rate
    rate1 = service.create_rate(
        plate_type="ban_kem_offset",
        technology="offset",
        unit="ban",
        unit_price=120000,
        effective_from=date(2026, 1, 1),
        actor=actor,
    )
    
    # 2. Create updated rate starting 2026-04-01
    rate2 = service.create_rate(
        plate_type="ban_kem_offset",
        technology="offset",
        unit="ban",
        unit_price=135000,
        effective_from=date(2026, 4, 1),
        actor=actor,
    )
    
    # Refresh rate1 from DB
    rate1_refreshed = service.get_rate(rate1.id)
    assert rate1_refreshed.effective_to == date(2026, 4, 1) # closed at exclusive effective_from
    assert rate2.effective_to is None # active
    
    # Check rate at different dates
    rate_feb = service.repo.get_rate_at_date("ban_kem_offset", "offset", "ban", date(2026, 2, 1))
    assert rate_feb.unit_price == 120000
    
    rate_may = service.repo.get_rate_at_date("ban_kem_offset", "offset", "ban", date(2026, 5, 1))
    assert rate_may.unit_price == 135000

def test_validation_date_overlap(client, service_and_actor):
    service, actor = service_and_actor
    
    service.create_rate(
        plate_type="ban_kem_offset",
        technology="offset",
        unit="ban",
        unit_price=120000,
        effective_from=date(2026, 2, 1),
        actor=actor,
    )
    
    with pytest.raises(PlateDieRateValidationError, match="Ngày hiệu lực mới"):
        service.create_rate(
            plate_type="ban_kem_offset",
            technology="offset",
            unit="ban",
            unit_price=130000,
            effective_from=date(2026, 2, 1),
            actor=actor,
        )

def test_delete_rates_retroactivity(client, service_and_actor):
    service, actor = service_and_actor
    today = date.today()
    
    # 1. Past/active rate cannot be hard deleted
    past_rate = service.create_rate(
        plate_type="ban_kem_offset",
        technology="offset",
        unit="ban",
        unit_price=120000,
        effective_from=today - timedelta(days=5),
        actor=actor,
    )
    with pytest.raises(PlateDieRateValidationError, match="Không thể xóa cứng"):
        service.delete_rate(rate_id=past_rate.id, actor=actor)
        
    # 2. Future rate can be hard deleted
    future_rate = service.create_rate(
        plate_type="ban_kem_offset",
        technology="offset",
        unit="ban",
        unit_price=130000,
        effective_from=today + timedelta(days=5),
        actor=actor,
    )
    service.delete_rate(rate_id=future_rate.id, actor=actor)
    with pytest.raises(PlateDieRateNotFoundError):
        service.get_rate(future_rate.id)
