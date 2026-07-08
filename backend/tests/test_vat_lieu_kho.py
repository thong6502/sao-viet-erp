"""Vật liệu Kho — CRUD giấy/mực/bản + lookup giá kẽm (thiếu → LỖI). Self-contained DB."""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base
import app.models  # noqa: F401
from app.models.vat_lieu_kho import BanKem, GiayNguyen, Muc  # noqa: F401 — đăng ký metadata
from app.repositories.vat_lieu_kho_repo import VatLieuKhoRepository
from app.services.vat_lieu_kho_service import (
    VatLieuKhoDuplicate,
    VatLieuKhoNotFound,
    VatLieuKhoService,
    VatLieuKhoValidationError,
)


def _svc():
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(eng)
    db = sessionmaker(bind=eng)()
    return db, VatLieuKhoService(VatLieuKhoRepository(db))


def test_giay_crud_and_validate():
    db, svc = _svc()
    g = svc.create("giay", dict(ma="C300", ten="Couché 300", kho_dai=860, kho_rong=650,
                                gsm=300, caliper_micron=310, tho="canh_dai", don_vi_gia="kg", don_gia=30000))
    assert g.id and g.ma == "C300" and g.gsm == 300
    with pytest.raises(VatLieuKhoValidationError):            # gsm <= 0
        svc.create("giay", dict(ma="X", ten="x", kho_dai=860, kho_rong=650, gsm=0))
    with pytest.raises(VatLieuKhoDuplicate):
        svc.create("giay", dict(ma="C300", ten="khác", kho_dai=650, kho_rong=860, gsm=150))


def test_muc_and_ban_crud():
    db, svc = _svc()
    m = svc.create("muc", dict(ma="M-CMYK", ten="Mực process", loai_muc="process", don_gia=8000))
    assert m.loai_muc == "process"
    b = svc.create("ban", dict(ma="K74", ten="Kẽm khổ 74", khoa_class="74", don_gia_kem=100000))
    assert b.khoa_class == "74"
    with pytest.raises(VatLieuKhoValidationError):            # khoa_class sai
        svc.create("ban", dict(ma="KX", ten="x", khoa_class="99", don_gia_kem=1))


def test_lookup_don_gia_kem():
    db, svc = _svc()
    svc.create("ban", dict(ma="K74", ten="Kẽm 74", khoa_class="74", don_gia_kem=100000))
    assert svc.lookup_don_gia_kem("74") == 100000
    # Thiếu mặt hàng → LỖI (E-TG-KHO-MISS), KHÔNG trả 0.
    with pytest.raises(VatLieuKhoNotFound):
        svc.lookup_don_gia_kem("102")


def test_list_filter_active():
    db, svc = _svc()
    svc.create("giay", dict(ma="G1", ten="g1", kho_dai=860, kho_rong=650, gsm=150))
    svc.create("giay", dict(ma="G2", ten="g2", kho_dai=860, kho_rong=650, gsm=200, active=False))
    rows, total = svc.list("giay", active=True)
    assert total == 1 and rows[0].ma == "G1"
