"""Kiểu bình bài — version-chain (spec E) + engine resolve theo code/effective-date.

Editing a type that has been used in a báo giá snapshot (used_count>0) must NOT mutate its
coefficients in place — it supersedes the current row and spins a new version. Non-material
edits (note/is_active) update in place even when used. Deleting a used type is blocked.
Self-contained (own in-memory DB); does not depend on the seed.
"""
from datetime import date

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base
import app.models  # noqa: F401 — register every table on Base.metadata
from app.models.user import User
from app.repositories.audit_repo import AuditLogRepository
from app.repositories.imposition_type_repo import ImpositionTypeRepository
from app.services.imposition_type_service import (
    ImpositionTypeService,
    ImpositionTypeValidationError,
    ImpositionTypeDuplicate,
)


def _setup():
    eng = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(eng)
    db = sessionmaker(bind=eng)()
    actor = User(username="tester", name="Tester", password_hash="x")
    db.add(actor)
    db.commit()
    repo = ImpositionTypeRepository(db)
    svc = ImpositionTypeService(repo, AuditLogRepository(db))
    return db, repo, svc, actor


def _data(**over):
    base = dict(
        code="TU_TRO",
        name="Tự trở",
        group_kind="two_side",
        note="ban đầu",
        is_active=True,
        sides=2,
        finished_factor=0.5,
        pass_count=2,
        plate_set_factor=1.0,
        ink_pass_factor=2.0,
        allow_rotate=True,
        shared_plate_set=True,
        technology="offset",
        applies_to_sides="2",
        applicable_product_types=None,
        applicable_machine_ids=None,
        applicable_paper_size_ids=None,
        allow_multi_signature=True,
        priority=20,
        effective_from=None,
        effective_to=None,
    )
    base.update(over)
    return base


def test_create_sets_code_and_audit_fields():
    db, repo, svc, actor = _setup()
    item = svc.create_item(_data(), actor=actor)
    assert item.code == "TU_TRO" and item.version == 1
    assert item.created_by == actor.id and item.updated_by == actor.id
    assert item.used_count == 0


def test_duplicate_code_rejected():
    db, repo, svc, actor = _setup()
    svc.create_item(_data(), actor=actor)
    with pytest.raises(ImpositionTypeDuplicate):
        svc.create_item(_data(name="Khác tên"), actor=actor)


def test_edit_when_unused_is_in_place():
    db, repo, svc, actor = _setup()
    item = svc.create_item(_data(), actor=actor)
    upd = svc.update_item(item.id, _data(plate_set_factor=2.0), actor=actor)
    assert upd.id == item.id and upd.version == 1
    assert float(upd.plate_set_factor) == 2.0
    # still only one row for this code
    assert repo.max_version_for_code("TU_TRO") == 1


def test_material_edit_when_used_creates_version():
    db, repo, svc, actor = _setup()
    item = svc.create_item(_data(), actor=actor)
    repo.increment_used_count(item)  # simulate báo giá snapshot
    assert item.used_count == 1

    new = svc.update_item(item.id, _data(plate_set_factor=2.0, name="Tự trở"), actor=actor)
    # A fresh version, not an in-place mutation.
    assert new.id != item.id
    assert new.version == 2
    assert new.effective_from == date.today()
    assert new.used_count == 0
    assert float(new.plate_set_factor) == 2.0

    db.refresh(item)
    assert item.effective_to == date.today()
    assert item.is_active is False
    # The old row keeps its frozen coefficient.
    assert float(item.plate_set_factor) == 1.0


def test_non_material_edit_when_used_is_in_place():
    db, repo, svc, actor = _setup()
    item = svc.create_item(_data(), actor=actor)
    repo.increment_used_count(item)
    # Only note/is_active change → no new version.
    upd = svc.update_item(item.id, _data(note="đổi mô tả", is_active=False), actor=actor)
    assert upd.id == item.id and upd.version == 1
    assert repo.max_version_for_code("TU_TRO") == 1


def test_resolve_active_picks_highest_effective_version():
    db, repo, svc, actor = _setup()
    item = svc.create_item(_data(), actor=actor)
    repo.increment_used_count(item)
    new = svc.update_item(item.id, _data(plate_set_factor=2.0), actor=actor)

    resolved = repo.resolve_active(code="TU_TRO", at_date=date.today())
    assert resolved is not None and resolved.id == new.id and resolved.version == 2
    # name fallback resolves too
    by_name = repo.resolve_active(name="Tự trở", at_date=date.today())
    assert by_name is not None and by_name.version == 2


def test_delete_used_type_blocked():
    db, repo, svc, actor = _setup()
    item = svc.create_item(_data(), actor=actor)
    repo.increment_used_count(item)
    with pytest.raises(ImpositionTypeValidationError):
        svc.delete_item(item_id=item.id, actor=actor)
