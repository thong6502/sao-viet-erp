"""Danh mục Giấy & Vật tư — CRUD chủng loại / giấy / vật tư (phẳng).

Model mới: `VatTuInAn` gộp phẳng (bỏ `Muc`/`BanKem` cũ); `GiayNguyen` ăn theo 1 Chủng loại
(`chung_loai_giay_id`, soft int). Self-contained in-memory DB.
"""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base
import app.models  # noqa: F401 — đăng ký metadata mọi bảng
from app.models.vat_lieu_kho import ChungLoaiGiay, GiayNguyen, VatTuInAn  # noqa: F401
from app.repositories.vat_lieu_kho_repo import VatLieuKhoRepository
from app.services.vat_lieu_kho_service import (
    VatLieuKhoDuplicate,
    VatLieuKhoService,
    VatLieuKhoValidationError,
)


def _svc():
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(eng)
    db = sessionmaker(bind=eng)()
    return db, VatLieuKhoService(VatLieuKhoRepository(db))


def test_chung_loai_giay_crud():
    db, svc = _svc()
    c = svc.create("chung_loai_giay", dict(ma="COUCHE", ten="Couché", be_mat="bong"))
    assert c.id and c.ma == "COUCHE"
    with pytest.raises(VatLieuKhoValidationError):            # bề mặt sai
        svc.create("chung_loai_giay", dict(ma="X", ten="x", be_mat="xyz"))


def test_giay_crud_and_validate():
    db, svc = _svc()
    cl = svc.create("chung_loai_giay", dict(ma="COUCHE", ten="Couché"))
    g = svc.create("giay", dict(ma="C300", ten="Couché 300", chung_loai_giay_id=cl.id,
                                kho_dai=860, kho_rong=650, gsm=300, don_vi_gia="kg", don_gia=30000))
    assert g.id and g.ma == "C300" and g.gsm == 300 and g.chung_loai_giay_id == cl.id
    with pytest.raises(VatLieuKhoValidationError):            # thiếu chủng loại
        svc.create("giay", dict(ma="Y", ten="y", kho_dai=860, kho_rong=650, gsm=150))
    with pytest.raises(VatLieuKhoValidationError):            # gsm <= 0
        svc.create("giay", dict(ma="X", ten="x", chung_loai_giay_id=cl.id, kho_dai=860, kho_rong=650, gsm=0))
    with pytest.raises(VatLieuKhoDuplicate):
        svc.create("giay", dict(ma="C300", ten="khác", chung_loai_giay_id=cl.id, kho_dai=650, kho_rong=860, gsm=150))


def test_vat_tu_flat_crud():
    db, svc = _svc()
    v = svc.create("vat_tu", dict(ma="MUC-CMYK", ten="Mực process CMYK", don_vi_gia="nghin_luot",
                                  don_gia=8000, ghi_chu="4 màu"))
    assert v.id and v.ma == "MUC-CMYK" and v.don_gia == 8000
    with pytest.raises(VatLieuKhoValidationError):            # ĐVT sai
        svc.create("vat_tu", dict(ma="X", ten="x", don_vi_gia="xyz"))
    with pytest.raises(VatLieuKhoDuplicate):
        svc.create("vat_tu", dict(ma="MUC-CMYK", ten="khác"))


def test_list_filter_active():
    db, svc = _svc()
    cl = svc.create("chung_loai_giay", dict(ma="FORD", ten="Ford"))
    svc.create("giay", dict(ma="G1", ten="g1", chung_loai_giay_id=cl.id, kho_dai=860, kho_rong=650, gsm=150))
    svc.create("giay", dict(ma="G2", ten="g2", chung_loai_giay_id=cl.id, kho_dai=860, kho_rong=650,
                            gsm=200, active=False))
    rows, total = svc.list("giay", active=True)
    assert total == 1 and rows[0].ma == "G1"
