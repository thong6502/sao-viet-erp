"""Tính giá service — resolve danh mục đã seed → costing_engine → giá thật (flat name card)."""
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base
import app.models  # noqa: F401 — đăng ký toàn bộ bảng
from app.models.loai_san_pham import LoaiSanPham
from app.models.may_thiet_bi import MayThietBi
from app.models.vat_lieu_kho import GiayNguyen
from app.seed_rebuild import seed_rebuild_catalog
from app.services.tinh_gia_service import TinhGiaService


def _db():
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(eng)
    db = sessionmaker(bind=eng)()
    seed_rebuild_catalog(db)
    return db


def test_preview_name_card_end_to_end():
    db = _db()
    sp = db.execute(select(LoaiSanPham).where(LoaiSanPham.ma == "LSP-0001")).scalars().first()
    may = db.execute(select(MayThietBi).where(MayThietBi.ma == "TB-0001")).scalars().first()
    giay = db.execute(select(GiayNguyen).where(GiayNguyen.ma == "COUCHE-300-65x86")).scalars().first()
    assert sp and may and giay

    out = TinhGiaService(db).preview({
        "loai_san_pham_id": sp.id, "may_id": may.id, "giay_id": giay.id,
        "so_luong": 10000, "so_mau_truoc": 4, "so_mau_sau": 4,
        "rong_tp": 53, "dai_tp": 90, "bleed_mm": 2, "chi_phi_khac": 150000,
        "quote": {"overhead_cty_pct": 15, "he_so_lai_pct": 20, "vat_rate": 8},
    })

    comp = out["components"][0]
    assert not comp.get("error")
    assert comp["imposition"]["so_kem"] == 8          # 4/4 flat
    assert comp["tien_kem"] == 800000.0               # 8 × giá kẽm khổ 74 (100k)
    assert comp["tien_giay"] > 0
    assert comp["tien_in"] >= 350000                  # sàn công in
    assert comp["tien_gia_cong"] > 0                  # có bế (per_pass)
    assert out["gia_von"] > 0
    assert out["gia_ban"] > out["gia_von"]            # +overhead+lãi+VAT
    assert out["don_gia_ban"] > 0
    assert out["may"] == "Offset 4 màu khổ 74"


def test_preview_vat_defaults_to_product():
    # Bỏ trống vat_rate (None) → lấy theo Loại SP (NAMECARD = 8%), KHÔNG rơi về 0.
    db = _db()
    sp = db.execute(select(LoaiSanPham).where(LoaiSanPham.ma == "LSP-0001")).scalars().first()
    may = db.execute(select(MayThietBi).where(MayThietBi.ma == "TB-0001")).scalars().first()
    giay = db.execute(select(GiayNguyen).where(GiayNguyen.ma == "COUCHE-300-65x86")).scalars().first()
    out = TinhGiaService(db).preview({
        "loai_san_pham_id": sp.id, "may_id": may.id, "giay_id": giay.id,
        "so_luong": 10000, "so_mau_truoc": 4, "so_mau_sau": 4, "rong_tp": 53, "dai_tp": 90,
        "quote": {"vat_rate": None},
    })
    assert out["vat_rate"] == 8 and out["vat"] > 0


def test_preview_missing_machine_errors():
    db = _db()
    giay = db.execute(select(GiayNguyen)).scalars().first()
    import pytest
    from app.services.tinh_gia_service import TinhGiaError
    with pytest.raises(TinhGiaError):
        TinhGiaService(db).preview({"may_id": 99999, "giay_id": giay.id, "so_luong": 100,
                                    "rong_tp": 50, "dai_tp": 90})
