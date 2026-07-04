"""Khổ giấy tiêu chuẩn — version-chain (spec E) + validation (spec §8) + loại-khổ booleans.

Sửa KÍCH THƯỚC một khổ đã dùng (used_count>0) tạo version mới, đóng băng bản cũ; sửa
field vòng đời (note/máy/active) thì tại chỗ. Khổ cắt phải có cha & không lớn hơn cha; khổ
vượt khổ máy bị chặn; xóa khổ đã dùng bị chặn. Self-contained (own in-memory DB).
"""
from datetime import date

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base
import app.models  # noqa: F401 — register every table on Base.metadata
from app.models.machine import Machine
from app.models.user import User
from app.repositories.audit_repo import AuditLogRepository
from app.repositories.paper_size_repo import PaperSizeRepository
from app.services.paper_size_service import (
    PaperSizeService,
    PaperSizeValidationError,
    PaperSizeDuplicate,
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
    repo = PaperSizeRepository(db)
    svc = PaperSizeService(repo, AuditLogRepository(db))
    return db, repo, svc, actor


def _data(**over):
    base = dict(
        code="K79x109",
        name="Khổ 79×109",
        size_group="cong_nghiep",
        is_purchase_size=True,
        is_print_sheet_size=True,
        is_cut_size=False,
        note=None,
        is_active=True,
        width_cm=79,
        height_cm=109,
        allow_rotation=True,
        compatible_machine_ids=None,
        default_machine_id=None,
        parent_size_id=None,
        cut_count=None,
        cut_waste_rate=None,
        effective_from=None,
        effective_to=None,
    )
    base.update(over)
    return base


# -- create / normalize -------------------------------------------------------

def test_create_sets_code_area_and_type():
    db, repo, svc, actor = _setup()
    item = svc.create_item(_data(), actor=actor)
    assert item.code == "K79x109" and item.version == 1
    assert item.created_by == actor.id and item.used_count == 0
    assert item.size_type == "ca_hai"  # purchase + print
    assert item.area_m2 == round(79 * 109 / 10000, 4)  # 0.8611


def test_blank_code_autogenerates_kg():
    db, repo, svc, actor = _setup()
    item = svc.create_item(_data(code=None), actor=actor)
    assert item.code == "KG001"


def test_size_type_back_compat_derives_booleans():
    # Old FE sends size_type only, no booleans.
    db, repo, svc, actor = _setup()
    d = _data()
    for k in ("is_purchase_size", "is_print_sheet_size", "is_cut_size"):
        d[k] = None
    d["size_type"] = "mua"
    item = svc.create_item(d, actor=actor)
    assert item.is_purchase_size is True and item.is_print_sheet_size is False
    assert item.size_type == "mua"


def test_duplicate_name_rejected():
    db, repo, svc, actor = _setup()
    svc.create_item(_data(), actor=actor)
    with pytest.raises(PaperSizeDuplicate):
        svc.create_item(_data(code="OTHER"), actor=actor)


# -- version-chain ------------------------------------------------------------

def test_dimension_edit_when_unused_is_in_place():
    db, repo, svc, actor = _setup()
    item = svc.create_item(_data(), actor=actor)
    upd = svc.update_item(item.id, _data(width_cm=80), actor=actor)
    assert upd.id == item.id and upd.version == 1
    assert float(upd.width_cm) == 80
    assert repo.max_version_for_code("K79x109") == 1


def test_dimension_edit_when_used_creates_version():
    db, repo, svc, actor = _setup()
    item = svc.create_item(_data(), actor=actor)
    repo.increment_used_count(item)  # simulate phiếu tính giá
    new = svc.update_item(item.id, _data(width_cm=80), actor=actor)
    assert new.id != item.id and new.version == 2
    assert new.effective_from == date.today() and new.used_count == 0
    assert float(new.width_cm) == 80
    db.refresh(item)
    assert item.effective_to == date.today() and item.is_active is False
    assert float(item.width_cm) == 79  # bản cũ đóng băng


def test_non_dimension_edit_when_used_is_in_place():
    db, repo, svc, actor = _setup()
    item = svc.create_item(_data(), actor=actor)
    repo.increment_used_count(item)
    upd = svc.update_item(item.id, _data(note="đổi ghi chú", is_active=False), actor=actor)
    assert upd.id == item.id and upd.version == 1
    assert repo.max_version_for_code("K79x109") == 1


def test_resolve_active_picks_highest_effective_version():
    db, repo, svc, actor = _setup()
    item = svc.create_item(_data(), actor=actor)
    repo.increment_used_count(item)
    new = svc.update_item(item.id, _data(width_cm=80), actor=actor)
    resolved = repo.resolve_active(code="K79x109", at_date=date.today())
    assert resolved is not None and resolved.id == new.id and resolved.version == 2


def test_manual_create_version():
    db, repo, svc, actor = _setup()
    item = svc.create_item(_data(), actor=actor)
    new = svc.create_version_item(item.id, _data(width_cm=81), actor=actor)
    assert new.version == 2 and float(new.width_cm) == 81
    db.refresh(item)
    assert item.is_active is False


# -- cut-size -----------------------------------------------------------------

def test_cut_size_requires_parent():
    db, repo, svc, actor = _setup()
    with pytest.raises(PaperSizeValidationError):
        svc.create_item(_data(code="CUT", name="Khổ cắt", is_cut_size=True, parent_size_id=None),
                        actor=actor)


def test_cut_size_larger_than_parent_rejected():
    db, repo, svc, actor = _setup()
    parent = svc.create_item(_data(code="P39", name="Khổ 39×54", width_cm=39, height_cm=54),
                             actor=actor)
    with pytest.raises(PaperSizeValidationError):
        svc.create_item(
            _data(code="CUT", name="Khổ cắt to", width_cm=79, height_cm=109,
                  is_cut_size=True, parent_size_id=parent.id),
            actor=actor,
        )


def test_cut_size_within_parent_ok():
    db, repo, svc, actor = _setup()
    parent = svc.create_item(_data(code="P79", name="Khổ 79×109"), actor=actor)
    child = svc.create_item(
        _data(code="C54", name="Khổ 54×79", width_cm=54, height_cm=79,
              is_cut_size=True, parent_size_id=parent.id),
        actor=actor,
    )
    assert child.parent_size_id == parent.id and child.size_type == "cat"


# -- machine over-size --------------------------------------------------------

def test_paper_exceeds_machine_rejected():
    db, repo, svc, actor = _setup()
    m = Machine(code="M52", name="Máy 52", machine_type="offset", process_type="in",
                max_width_cm=52, max_height_cm=72, speed=5000, speed_unit="to/gio")
    db.add(m)
    db.commit()
    with pytest.raises(PaperSizeValidationError):
        svc.create_item(_data(compatible_machine_ids=[m.id]), actor=actor)  # 79×109 > 52×72


def test_paper_fits_machine_ok():
    db, repo, svc, actor = _setup()
    m = Machine(code="M102", name="Máy 102", machine_type="offset", process_type="in",
                max_width_cm=75, max_height_cm=105, speed=5000, speed_unit="to/gio")
    db.add(m)
    db.commit()
    # 65×86 fits within 75×105
    item = svc.create_item(_data(code="K65", name="Khổ 65×86", width_cm=65, height_cm=86,
                                 compatible_machine_ids=[m.id]), actor=actor)
    assert item.compatible_machine_ids == [m.id]


# -- delete guard + clone -----------------------------------------------------

def test_delete_used_size_blocked():
    db, repo, svc, actor = _setup()
    item = svc.create_item(_data(), actor=actor)
    repo.increment_used_count(item)
    with pytest.raises(PaperSizeValidationError):
        svc.delete_item(item_id=item.id, actor=actor)


def test_delete_parent_with_children_blocked():
    db, repo, svc, actor = _setup()
    parent = svc.create_item(_data(code="P79", name="Khổ 79×109"), actor=actor)
    svc.create_item(_data(code="C54", name="Khổ 54×79", width_cm=54, height_cm=79,
                          is_cut_size=True, parent_size_id=parent.id), actor=actor)
    with pytest.raises(PaperSizeValidationError):
        svc.delete_item(item_id=parent.id, actor=actor)


def test_clone_creates_new_code():
    db, repo, svc, actor = _setup()
    item = svc.create_item(_data(), actor=actor)
    clone = svc.clone_item(item.id, actor=actor)
    assert clone.id != item.id and clone.code != item.code
    assert float(clone.width_cm) == float(item.width_cm)
    assert "bản sao" in clone.name
