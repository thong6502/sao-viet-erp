"""Loại sản phẩm — CRUD + validate (§5) + tương thích layout (§5.1). Self-contained DB."""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base
import app.models  # noqa: F401
from app.models.loai_san_pham import LoaiSanPham  # noqa: F401 — đăng ký metadata
from app.repositories.loai_san_pham_repo import LoaiSanPhamRepository
from app.services.loai_san_pham_service import (
    LoaiSanPhamDuplicate,
    LoaiSanPhamService,
    LoaiSanPhamValidationError,
    is_layout_compatible,
)


def _svc():
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(eng)
    db = sessionmaker(bind=eng)()
    return db, LoaiSanPhamService(LoaiSanPhamRepository(db))


def test_create_flat_and_multipage():
    db, svc = _svc()
    nc = svc.create(dict(ma="NAMECARD", ten="Name card", structural_type="flat",
                         imposition_rule_id=1, default_so_mat=2, vat_rate=8,
                         routing_template=[10, 20, 30]))
    assert nc.id and nc.structural_type == "flat" and nc.routing_template == [10, 20, 30]
    cat = svc.create(dict(ma="CATALOGUE", ten="Catalogue", structural_type="multipage",
                          has_cover=True, cover_type="bia_roi", default_binding="keo", vat_rate=5))
    assert cat.has_cover and cat.vat_rate == 5


def test_duplicate_ma():
    db, svc = _svc()
    svc.create(dict(ma="NAMECARD", ten="x", structural_type="flat"))
    with pytest.raises(LoaiSanPhamDuplicate):
        svc.create(dict(ma="NAMECARD", ten="y", structural_type="flat"))


def test_validate_box_cover_vat():
    db, svc = _svc()
    with pytest.raises(LoaiSanPhamValidationError):        # box thiếu box_sub_type
        svc.create(dict(ma="H1", ten="Hộp", structural_type="box"))
    with pytest.raises(LoaiSanPhamValidationError):        # has_cover thiếu cover_type [E-SP-COVER]
        svc.create(dict(ma="S1", ten="Sách", structural_type="multipage", has_cover=True))
    with pytest.raises(LoaiSanPhamValidationError):        # vat_rate sai
        svc.create(dict(ma="X1", ten="x", structural_type="flat", vat_rate=7))
    with pytest.raises(LoaiSanPhamValidationError):        # structural_type sai
        svc.create(dict(ma="X2", ten="x", structural_type="khong_co"))


def test_layout_compat_matrix():
    # §5.1: flat ~ step_repeat/nesting ; multipage ~ signature ; box ~ nesting/step_repeat ; label ~ step_repeat
    assert is_layout_compatible("flat", "step_repeat")
    assert is_layout_compatible("multipage", "signature")
    assert not is_layout_compatible("multipage", "step_repeat")
    assert is_layout_compatible("label", "step_repeat")
    assert not is_layout_compatible("flat", "signature")


def test_list_filter_by_structural_type():
    db, svc = _svc()
    svc.create(dict(ma="NAMECARD", ten="nc", structural_type="flat"))
    svc.create(dict(ma="HOP", ten="hop", structural_type="box", box_sub_type="folding_carton"))
    rows, total = svc.list(structural_type="box")
    assert total == 1 and rows[0].ma == "HOP"
