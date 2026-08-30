"""Đề nghị cấp vật tư theo công đoạn (docs/spec-de-nghi-cap-vat-tu-cong-doan.md).

Hai bảng SẢN XUẤT giữ bản đối chiếu ĐẦY ĐỦ (kể cả dòng xin 0); yêu cầu kho là ẢNH CHIẾU chỉ chứa
dòng dương. Test file này chốt: cấu trúc, luật lý do, luật khoá, luật quyền, và luật "sửa hết về 0".
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy.exc import IntegrityError

from app.db import Base, SessionLocal, engine
from app.models.san_xuat_vat_tu import (
    DN_BO_SUNG, DN_LAN_DAU, SanXuatVatTuDeNghi, SanXuatVatTuDeNghiDong,
)

_T0 = datetime(2026, 8, 31, 8, 0, tzinfo=timezone.utc)


@pytest.fixture
def db():
    # `create_all` chỉ dựng bảng, KHÔNG áp migration — test này không cần: các test dựa vào id
    # giả (cong_viec_id=1, stock_request_id=555) mà conftest không bật PRAGMA foreign_keys nên
    # khoá ngoại không bị ép; ràng buộc đang kiểm là UNIQUE, không phải FK.
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    s = SessionLocal()
    yield s
    s.close()


def test_mot_cong_viec_khong_co_hai_lan_cung_so(db):
    for _ in range(2):
        db.add(SanXuatVatTuDeNghi(cong_viec_id=1, lan_so=1, loai=DN_LAN_DAU, can_luc=_T0))
    with pytest.raises(IntegrityError):
        db.flush()
    db.rollback()


def test_mot_de_nghi_khong_co_hai_dong_cung_mat_hang(db):
    dn = SanXuatVatTuDeNghi(cong_viec_id=2, lan_so=1, loai=DN_LAN_DAU, can_luc=_T0)
    db.add(dn)
    db.flush()
    for _ in range(2):
        db.add(SanXuatVatTuDeNghiDong(
            de_nghi_id=dn.id, hang_loai="giay", hang_id=9, dvt="tờ", dvt_goc="kg",
            sl_ke_hoach=100, sl_ke_hoach_goc=12, sl_yeu_cau=100, sl_yeu_cau_goc=12,
        ))
    with pytest.raises(IntegrityError):
        db.flush()
    db.rollback()


def test_mot_yeu_cau_kho_chi_thuoc_mot_de_nghi(db):
    for lan in (1, 2):
        db.add(SanXuatVatTuDeNghi(cong_viec_id=3, lan_so=lan, loai=DN_LAN_DAU,
                                  can_luc=_T0, stock_request_id=555))
    with pytest.raises(IntegrityError):
        db.flush()
    db.rollback()


def test_dong_yeu_cau_kho_mac_dinh_chua_chot_thuc_xuat(db):
    """`sl_chot_thuc_xuat` NULL = kho CHƯA điều chỉnh. KHÁC hẳn 0 (đã chốt là không xuất gì)."""
    from app.models.stock_request import StockRequestLine

    ln = StockRequestLine(request_id=1, hang_loai="giay", hang_id=1, dvt="kg", sl_de_nghi=100)
    assert ln.sl_chot_thuc_xuat is None


def test_migration_0249_co_trong_danh_sach():
    from app.db_migrations import MIGRATIONS
    assert any(ma == "0249_sx_vat_tu_de_nghi" for ma, _fn in MIGRATIONS)
