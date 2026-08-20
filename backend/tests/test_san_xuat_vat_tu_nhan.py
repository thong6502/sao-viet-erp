"""Thực hiện sản xuất — Giai đoạn 3 mặt GHI: XÁC NHẬN VẬT TƯ ĐÃ NHẬN (§10.1).

Soi tầng service `services/san_xuat/vat_tu_nhan.py` (nơi chứa LUẬT), không qua HTTP:
  · chỉ xác nhận phiếu XUẤT đã GHI SỔ (posted) — nháp/nhập bị chặn;
  · một phiếu chỉ xác nhận MỘT lần (`voucher_id` UNIQUE);
  · GATE §6: chỉ tổ trưởng đúng tổ nhận.

SQLite test không siết khoá ngoại (conftest không bật PRAGMA) nên phiếu mang `request_id`/`kho_id`
tượng trưng vẫn dựng được — service chỉ đọc `loai` + `trang_thai`.
"""
from __future__ import annotations

from datetime import date
from types import SimpleNamespace

import pytest

from app.models.san_xuat_san_luong import SanXuatVatTuNhan
from app.models.stock_voucher import (
    StockVoucher,
    VOUCHER_DRAFT,
    VOUCHER_NHAP,
    VOUCHER_POSTED,
    VOUCHER_XUAT,
)
from app.services.san_xuat import vat_tu_nhan

from tests.test_san_xuat_thuc_thi import (  # noqa: F401
    _to_khoan,
    admin,
    customer,
    db,
    lsx_svc,
    orders,
)


def _voucher(db, admin, *, loai=VOUCHER_XUAT, trang_thai=VOUCHER_POSTED, ma="PXK-TT"):
    v = StockVoucher(
        ma=ma, loai=loai, request_id=1, kho_id=1,
        ngay=date(2026, 8, 19), nguoi_lap_id=admin.id, trang_thai=trang_thai,
    )
    db.add(v)
    db.flush()
    return v


def test_xac_nhan_phieu_xuat_posted(db, orders, lsx_svc, admin, customer):
    to = _to_khoan(db, admin, ma="TO-VT")
    v = _voucher(db, admin)

    res = vat_tu_nhan.xac_nhan_vat_tu(db, user=admin, voucher_id=v.id, department_id=to.id)
    assert res["voucher_id"] == v.id and res["department_id"] == to.id and res["nhan_id"]
    nhan = db.get(SanXuatVatTuNhan, res["nhan_id"])
    assert nhan.xac_nhan_by_id == admin.id and nhan.xac_nhan_luc is not None


def test_tu_choi_phieu_nhap_hoac_chua_ghi_so(db, orders, lsx_svc, admin, customer):
    to = _to_khoan(db, admin, ma="TO-VT2")
    nhap = _voucher(db, admin, loai=VOUCHER_NHAP, ma="PNK-1")
    with pytest.raises(ValueError):                       # phiếu NHẬP
        vat_tu_nhan.xac_nhan_vat_tu(db, user=admin, voucher_id=nhap.id, department_id=to.id)
    nhap_du = _voucher(db, admin, trang_thai=VOUCHER_DRAFT, ma="PXK-DRAFT")
    with pytest.raises(ValueError):                       # XUẤT nhưng còn nháp
        vat_tu_nhan.xac_nhan_vat_tu(db, user=admin, voucher_id=nhap_du.id, department_id=to.id)


def test_khong_xac_nhan_hai_lan(db, orders, lsx_svc, admin, customer):
    to = _to_khoan(db, admin, ma="TO-VT3")
    v = _voucher(db, admin, ma="PXK-2LAN")
    vat_tu_nhan.xac_nhan_vat_tu(db, user=admin, voucher_id=v.id, department_id=to.id)
    with pytest.raises(ValueError):
        vat_tu_nhan.xac_nhan_vat_tu(db, user=admin, voucher_id=v.id, department_id=to.id)


def test_gate_chi_to_truong(db, orders, lsx_svc, admin, customer):
    to = _to_khoan(db, admin, ma="TO-VT4")
    v = _voucher(db, admin, ma="PXK-GATE")
    nguoi_la = SimpleNamespace(id=admin.id + 99_999)
    with pytest.raises(PermissionError):
        vat_tu_nhan.xac_nhan_vat_tu(db, user=nguoi_la, voucher_id=v.id, department_id=to.id)
