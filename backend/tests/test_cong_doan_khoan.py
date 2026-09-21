"""Cấu hình Khoán 1–1 nằm trong aggregate Công đoạn."""
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base
import app.models  # noqa: F401
from app.models.cong_doan import CongDoanKhoan, CongDoanKhoanPhatSinh
from app.models.don_vi_do import DonViDo
from app.repositories.cong_doan_repo import CongDoanRepository
from app.services.cong_doan_service import CongDoanService, CongDoanValidationError


def _svc():
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(eng)
    db = sessionmaker(bind=eng)()
    db.add_all([
        DonViDo(ma="to", ten="Tờ", ho="khac"),
        DonViDo(ma="kem", ten="Bản kẽm", ho="khac"),
    ])
    db.commit()
    return db, CongDoanService(CongDoanRepository(db))


def _base(**them):
    return {
        "ma": "CD-KHOAN", "ten": "Cắt thành phẩm", "nhom": "finishing",
        "pricing_basis": "per_other", **them,
    }


def test_tao_doc_sua_va_go_cau_hinh_khoan_cung_cong_doan():
    db, svc = _svc()
    cd = svc.create(_base(khoan={
        "unit": "to", "unit_price": 25, "cong_thuc_khoan": " sl_ra ",
        "viec_phat_sinh": [
            {"ten": "Thay kẽm", "don_gia": 100000, "don_vi": "kem"},
        ],
    }))
    assert cd.khoan is not None
    assert (cd.khoan.unit, float(cd.khoan.unit_price), cd.khoan.cong_thuc_khoan) == \
        ("to", 25, "sl_ra")
    assert [(v.ten, float(v.don_gia), v.don_vi) for v in cd.khoan.viec_phat_sinh] == \
        [("Thay kẽm", 100000, "kem")]

    cd = svc.update(cd.id, _base(khoan={
        "unit": "to", "unit_price": 0, "cong_thuc_khoan": None,
        "viec_phat_sinh": [],
    }))
    assert cd.khoan is not None and float(cd.khoan.unit_price) == 0
    assert cd.khoan.viec_phat_sinh == []

    cd = svc.update(cd.id, _base(khoan=None))
    assert cd.khoan is None
    assert db.scalar(select(CongDoanKhoan).where(CongDoanKhoan.cong_doan_id == cd.id)) is None
    assert db.scalars(select(CongDoanKhoanPhatSinh)).all() == []


@pytest.mark.parametrize("khoan, loi", [
    ({"unit": "", "unit_price": 25}, "đủ đơn vị tính và đơn giá"),
    ({"unit": "to", "unit_price": None}, "đủ đơn vị tính và đơn giá"),
    ({"unit": "to", "unit_price": -1}, "không được âm"),
    ({"unit": "khong-co", "unit_price": 1}, "không có trong danh mục"),
    ({"unit": "to", "unit_price": 1, "viec_phat_sinh": [
        {"ten": " Thay kẽm ", "don_gia": 1, "don_vi": "kem"},
        {"ten": "thay   KẼM", "don_gia": 2, "don_vi": "kem"},
    ]}, "trùng tên"),
])
def test_chan_cau_hinh_khoan_khong_hop_le(khoan, loi):
    db, svc = _svc()
    with pytest.raises(CongDoanValidationError, match=loi):
        svc.create(_base(khoan=khoan))


def test_loi_khoan_khong_luu_do_cong_doan():
    db, svc = _svc()
    with pytest.raises(CongDoanValidationError):
        svc.create(_base(khoan={"unit": "to", "unit_price": -1}))
    assert svc.repo.find_by_ma("CD-KHOAN") is None


def test_anh_chup_nhat_ky_gom_ca_khoan_va_viec_phat_sinh():
    from app.services.nhat_ky_danh_muc import anh_chup

    _db, svc = _svc()
    cd = svc.create(_base(khoan={
        "unit": "to", "unit_price": 25, "cong_thuc_khoan": "sl_ra",
        "viec_phat_sinh": [
            {"ten": "Thay kẽm", "don_gia": 100000, "don_vi": "kem"},
        ],
    }))
    snap = anh_chup(cd)
    assert snap["khoan"]["Đơn giá khoán"] == "25 đ"
    assert snap["khoan"]["Công thức khoán"] == "sl_ra"
    assert snap["khoan"]["Việc phát sinh › Thay kẽm"] == "100.000 đ/Bản kẽm"
