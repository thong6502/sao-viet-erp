"""Thực hiện sản xuất — Giai đoạn 3 mặt GHI: XÁC NHẬN VẬT TƯ ĐÃ NHẬN (§10.1).

Soi tầng service `services/san_xuat/vat_tu_nhan.py` (nơi chứa LUẬT), không qua HTTP:
  · chỉ xác nhận phiếu XUẤT đã GHI SỔ (posted) — nháp/nhập bị chặn;
  · một phiếu chỉ xác nhận MỘT lần (`voucher_id` UNIQUE);
  · cổng: quyền Kho TRỌN tổ nhận (dòng quyền theo tổ, mg 0302) — xác nhận theo tổ không gắn việc
    riêng của ai nên phạm vi "Của tôi" không đủ, có quyền khác mà thiếu Kho cũng bị chặn.

SQLite test không siết khoá ngoại (conftest không bật PRAGMA) nên phiếu mang `request_id`/`kho_id`
tượng trưng vẫn dựng được — service chỉ đọc `loai` + `trang_thai`.
"""
from __future__ import annotations

from datetime import date
from types import SimpleNamespace

import pytest

from app.models.role import SCOPE_OWN
from app.models.san_xuat_san_luong import SanXuatVatTuNhan
from app.models.stock_voucher import (
    StockVoucher,
    VOUCHER_DRAFT,
    VOUCHER_NHAP,
    VOUCHER_POSTED,
    VOUCHER_XUAT,
)
from app.models.user import User
from app.services.san_xuat import vat_tu_nhan
from tests.quyen_to_fixtures import cap_quyen_to

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


def test_gate_nguoi_khong_co_quyen_to_bi_chan(db, orders, lsx_svc, admin, customer):
    to = _to_khoan(db, admin, ma="TO-VT4")
    v = _voucher(db, admin, ma="PXK-GATE")
    nguoi_la = SimpleNamespace(id=admin.id + 99_999)
    with pytest.raises(PermissionError):
        vat_tu_nhan.xac_nhan_vat_tu(db, user=nguoi_la, voucher_id=v.id, department_id=to.id)


def _nguoi(db, ten, to) -> User:
    u = User(username=ten, name=ten, password_hash="x", department_id=to.id)
    db.add(u)
    db.flush()
    return u


def test_gate_kho_phai_tron_to(db, orders, lsx_svc, admin, customer):
    """Kho ở phạm vi "Của tôi" không xác nhận nhận vật tư được (không có việc riêng để đối chiếu);
    đủ bốn quyền trừ Kho cũng không; Kho trọn tổ thì được."""
    to = _to_khoan(db, admin, ma="TO-VT5")
    v = _voucher(db, admin, ma="PXK-KHO")
    kho_own = _nguoi(db, "kho_own_vt", to)
    cap_quyen_to(db, kho_own, to, scope=SCOPE_OWN, viec=("warehouse",))
    thieu_kho = _nguoi(db, "thieu_kho_vt", to)
    cap_quyen_to(db, thieu_kho, to, viec=("run_order", "confirm_output"))
    kho_tron = _nguoi(db, "kho_tron_vt", to)
    cap_quyen_to(db, kho_tron, to, viec=("warehouse",))
    db.commit()

    for u in (kho_own, thieu_kho):
        with pytest.raises(PermissionError, match="quyền Kho"):
            vat_tu_nhan.xac_nhan_vat_tu(db, user=u, voucher_id=v.id, department_id=to.id)
    res = vat_tu_nhan.xac_nhan_vat_tu(db, user=kho_tron, voucher_id=v.id, department_id=to.id)
    assert db.get(SanXuatVatTuNhan, res["nhan_id"]).xac_nhan_by_id == kho_tron.id
