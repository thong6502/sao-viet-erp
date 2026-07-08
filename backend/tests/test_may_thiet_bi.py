"""Máy thiết bị — model + compute_bhr (§4.2/4.3) + validate (§8). Self-contained in-memory DB."""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base
import app.models  # noqa: F401 — đăng ký metadata
from app.models.may_thiet_bi import MayThietBi
from app.repositories.may_thiet_bi_repo import MayThietBiRepository
from app.services.may_thiet_bi_service import (
    MayThietBiDuplicate,
    MayThietBiService,
    MayThietBiValidationError,
    compute_bhr,
)


def _svc():
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(eng)
    db = sessionmaker(bind=eng)()
    return db, MayThietBiService(MayThietBiRepository(db))


def _off74(**over):
    """Máy offset 74 theo ví dụ §4.3."""
    base = dict(
        ma="OFF-74-4C", ten="Offset 74 4 màu", loai_may="press_offset_sheet",
        kho_max_dai=740, kho_max_rong=530, kho_min_dai=210, kho_min_rong=280,
        gripper_mm=12, so_units=4, khoa_class="74",
        von_dau_tu=4_000_000_000, gia_tri_thu_hoi=400_000_000, nam_khau_hao=8,
        gio_lam_nam=2000, availability_pct=90, productivity_pct=83, lai_von_pct=10,
        bao_hiem_nam=40_000_000, dien_tich_san_m2=40, don_gia_thue_m2_nam=1_200_000,
        luong_gio=60_000, luong_burden_pct=30, so_nhan_cong=2, so_may_song_song=1,
        bao_tri_gio=30_000, overhead_gio=50_000,
        cong_suat_kW=80, he_so_tai_dien=0.65, don_gia_dien=3000, markup_pct=15,
    )
    base.update(over)
    return base


def test_create_and_active_from_trang_thai():
    db, svc = _svc()
    m = svc.create(_off74())
    assert m.id and m.ma == "OFF-74-4C" and m.loai_may == "press_offset_sheet"
    assert m.active is True                       # trang_thai=active → active
    m2 = svc.update(m.id, _off74(trang_thai="retired"))
    assert m2.active is False


def test_duplicate_ma_rejected():
    db, svc = _svc()
    svc.create(_off74())
    with pytest.raises(MayThietBiDuplicate):
        svc.create(_off74(ten="Khác tên"))


def test_bhr_matches_spec_example():
    db, svc = _svc()
    m = svc.create(_off74())
    r = compute_bhr(m)
    # §4.3: gio_tinh_phi ≈ 1494 (spec làm tròn 1500), BHR ≈ 897–899k.
    assert 1490 <= r["gio_tinh_phi"] <= 1500
    assert 880_000 <= r["BHR"] <= 915_000, r
    # điện là chi phí CHẠY = 80×0.65×3000 = 156.000
    assert r["breakdown"]["dien_gio"] == 156_000
    # lao động = 60k×1.3×2 = 156.000
    assert r["breakdown"]["lao_dong_gio"] == 156_000
    # don_gia_ban = BHR×1.15
    assert abs(r["don_gia_ban_gio"] - r["BHR"] * 1.15) < 1


def test_bhr_direct_source():
    db, svc = _svc()
    m = svc.create(_off74(nguon_bhr="nhap_truc_tiep", don_gia_gio_BHR=1_000_000, markup_pct=20))
    r = compute_bhr(m)
    assert r["BHR"] == 1_000_000 and r["don_gia_ban_gio"] == 1_200_000


def test_validate_kho_and_nhip():
    db, svc = _svc()
    with pytest.raises(MayThietBiValidationError):      # E-MAY-KHO
        svc.create(_off74(ma="X1", kho_min_dai=800, kho_max_dai=740))
    with pytest.raises(MayThietBiValidationError):      # E-MAY-NHIP: gripper ≥ kho_min_rong
        svc.create(_off74(ma="X2", gripper_mm=300, kho_min_rong=280))
    with pytest.raises(MayThietBiValidationError):      # loai_may sai
        svc.create(_off74(ma="X3", loai_may="khong_co"))


def test_fields_theo_loai_json_roundtrip():
    db, svc = _svc()
    m = svc.create(_off74(ma="DIG-1", loai_may="press_digital",
                          fields_theo_loai={"cong_nghe": "toner", "click_mau": 1200}))
    got = svc.get(m.id)
    assert got.fields_theo_loai["click_mau"] == 1200


def test_list_filter_by_loai_may():
    db, svc = _svc()
    svc.create(_off74())
    svc.create(_off74(ma="CTP-B1", ten="CTP", loai_may="prepress_ctp"))
    rows, total = svc.list(loai_may="prepress_ctp")
    assert total == 1 and rows[0].ma == "CTP-B1"
