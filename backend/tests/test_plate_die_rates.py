"""Đơn giá kẽm & khuôn (#5) — create/version/close/delete + kẽm chọn theo máy + pricing_method khuôn."""
from __future__ import annotations

import pytest
from datetime import date, timedelta
from app.db import SessionLocal
from app.models.machine import Machine
from app.repositories.plate_die_rate_repo import PlateDieRateRepository
from app.services.plate_die_rate_service import (
    PlateDieRateService,
    PlateDieRateValidationError,
    PlateDieRateDuplicate,
    PlateDieRateNotFoundError,
)
from app.repositories.audit_repo import AuditLogRepository


class MockActor:
    def __init__(self, user_id: int = 1) -> None:
        self.id = user_id


@pytest.fixture
def svc(client):
    db = SessionLocal()
    service = PlateDieRateService(PlateDieRateRepository(db), AuditLogRepository(db))
    yield service, MockActor(), db
    db.close()


def _kem(**over):
    d = dict(code="PLATE_72", name="Kẽm CTP 72", plate_type="ban_kem_offset",
             technology="offset", unit="ban", unit_price=100000, pricing_method="fixed",
             effective_from=date(2026, 1, 1))
    d.update(over)
    return d


def _die(**over):
    d = dict(code="DIE_BOX", name="Khuôn bế hộp", plate_type="khuon_be", technology="be",
             unit="bo", unit_price=800000, pricing_method="fixed", min_charge=500000,
             effective_from=date(2026, 1, 1))
    d.update(over)
    return d


# -- create / validation ------------------------------------------------------

def test_create_sets_fields(svc):
    service, actor, _ = svc
    r = service.create_rate(_kem(), actor=actor)
    assert r.id and r.code == "PLATE_72" and r.plate_type == "ban_kem_offset"
    assert r.unit_price == 100000 and r.effective_to is None and r.used_count == 0


def test_duplicate_code_rejected(svc):
    service, actor, _ = svc
    service.create_rate(_kem(), actor=actor)
    with pytest.raises(PlateDieRateDuplicate):
        service.create_rate(_kem(name="khác"), actor=actor)


def test_invalid_plate_type(svc):
    service, actor, _ = svc
    with pytest.raises(PlateDieRateValidationError, match="Loại kẽm/khuôn"):
        service.create_rate(_kem(plate_type="laser_plate"), actor=actor)


def test_invalid_technology(svc):
    service, actor, _ = svc
    with pytest.raises(PlateDieRateValidationError, match="Công nghệ"):
        service.create_rate(_kem(technology="laser"), actor=actor)


def test_kem_requires_price(svc):
    service, actor, _ = svc
    with pytest.raises(PlateDieRateValidationError, match="Đơn giá 1 bản kẽm"):
        service.create_rate(_kem(unit_price=0), actor=actor)


def test_die_area_requires_area_price(svc):
    service, actor, _ = svc
    with pytest.raises(PlateDieRateValidationError, match="đơn giá/cm"):
        service.create_rate(_die(code="FOIL", pricing_method="area", unit_price=0,
                                 unit_price_area=0, plate_type="khuon_ep_kim",
                                 technology="ep_kim", unit="cm2"), actor=actor)


def test_die_perimeter_requires_perimeter_price(svc):
    service, actor, _ = svc
    with pytest.raises(PlateDieRateValidationError, match="đơn giá/mét dao"):
        service.create_rate(_die(pricing_method="perimeter", unit_price=0,
                                 unit_price_perimeter=0, unit="met"), actor=actor)


# -- version-chain (hiệu lực-theo-ngày, key=code) -----------------------------

def test_version_closes_old_and_resolves_by_date(svc):
    service, actor, _ = svc
    r1 = service.create_rate(_kem(), actor=actor)
    r2 = service.create_version(r1.id, _kem(unit_price=135000, effective_from=date(2026, 4, 1)),
                                actor=actor)
    assert service.get_rate(r1.id).effective_to == date(2026, 4, 1)
    assert r2.effective_to is None
    assert service.repo.get_rate_at_date("PLATE_72", date(2026, 2, 1)).unit_price == 100000
    assert service.repo.get_rate_at_date("PLATE_72", date(2026, 5, 1)).unit_price == 135000


def test_version_date_must_advance(svc):
    service, actor, _ = svc
    r1 = service.create_rate(_kem(effective_from=date(2026, 2, 1)), actor=actor)
    with pytest.raises(PlateDieRateValidationError, match="phải sau"):
        service.create_version(r1.id, _kem(effective_from=date(2026, 2, 1)), actor=actor)


def test_clone_creates_new_code(svc):
    service, actor, _ = svc
    r = service.create_rate(_kem(), actor=actor)
    c = service.clone_rate(r.id, actor=actor)
    assert c.code != r.code and c.unit_price == r.unit_price and "bản sao" in c.name


def test_delete_retroactivity(svc):
    service, actor, _ = svc
    today = date.today()
    past = service.create_rate(_kem(code="P_PAST", effective_from=today - timedelta(days=5)), actor=actor)
    with pytest.raises(PlateDieRateValidationError, match="Không thể xóa cứng"):
        service.delete_rate(rate_id=past.id, actor=actor)
    future = service.create_rate(_kem(code="P_FUT", effective_from=today + timedelta(days=5)), actor=actor)
    service.delete_rate(rate_id=future.id, actor=actor)
    with pytest.raises(PlateDieRateNotFoundError):
        service.get_rate(future.id)


# -- kẽm chọn theo máy --------------------------------------------------------

def test_resolve_plate_prefers_machine_specific(svc):
    service, actor, db = svc
    m = Machine(code="M_OFF", name="Máy offset", machine_type="offset", process_type="in",
                speed=8000, speed_unit="to/gio")
    db.add(m)
    db.commit()
    # generic (mọi máy) + specific (máy m)
    service.create_rate(_kem(code="PLATE_GEN", unit_price=90000, machine_ids=None), actor=actor)
    service.create_rate(_kem(code="PLATE_SPEC", unit_price=111000, machine_ids=[m.id]), actor=actor)
    got = service.repo.resolve_plate_for_machine(m.id, date(2026, 6, 1))
    assert got is not None and got.unit_price == 111000  # specific thắng generic
    # máy khác → chỉ có generic
    got2 = service.repo.resolve_plate_for_machine(999, date(2026, 6, 1))
    assert got2 is not None and got2.unit_price == 90000
