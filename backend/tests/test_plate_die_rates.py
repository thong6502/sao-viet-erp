"""Đơn giá kẽm & khuôn (#5) — kẽm chọn theo máy.

Router `/api/plate-die-rates` + `PlateDieRateService` đã GỠ (2026-07-16: không màn nào gọi,
module quyền `dm_gia_khuon_ban` bỏ theo migration 0069) → mọi test CRUD/validation qua service
đi cùng. Phần CÒN SỐNG là dữ liệu + `PlateDieRateRepository.resolve_plate_for_machine`, thứ
engine tính giá gọi thẳng (pricing_engine `_plate_die_cost`) — nên nó ở lại, test qua repo.
"""
from __future__ import annotations

from datetime import date

import pytest

from app.db import SessionLocal
from app.models.machine import Machine
from app.repositories.plate_die_rate_repo import PlateDieRateRepository


@pytest.fixture
def repo(client):
    db = SessionLocal()
    yield PlateDieRateRepository(db), db
    db.close()


def _kem(**over):
    d = dict(name="Kẽm CTP 72", plate_type="ban_kem_offset", technology="offset", unit="ban",
             unit_price=100000, pricing_method="fixed", effective_from=date(2026, 1, 1))
    d.update(over)
    return d


def test_resolve_plate_prefers_machine_specific(repo):
    """Kẽm gắn ĐÚNG máy thắng kẽm mọi-máy; máy không khớp thì rơi về mọi-máy."""
    r, db = repo
    m = Machine(code="M_OFF", name="Máy offset", machine_type="offset", process_type="in",
                speed=8000, speed_unit="to/gio")
    db.add(m)
    db.commit()

    r.add_rate(code="PLATE_GEN", machine_ids=None, **_kem(unit_price=90000))
    r.add_rate(code="PLATE_SPEC", machine_ids=[m.id], **_kem(unit_price=111000))

    got = r.resolve_plate_for_machine(m.id, date(2026, 6, 1))
    assert got is not None and got.unit_price == 111000  # specific thắng generic

    got2 = r.resolve_plate_for_machine(999, date(2026, 6, 1))
    assert got2 is not None and got2.unit_price == 90000  # máy khác → chỉ có generic
