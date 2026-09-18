"""Sửa GIÁ GỐC thành phẩm sau khi ghi sổ + danh sách "Thành phẩm chưa có giá gốc" (design nhập kho
thành phẩm §5).

  · gõ một lần trên lô gốc ⇒ lô gốc + lô sinh ra qua điều chuyển đổi cùng lúc: dòng phiếu nhập (báo cáo
    Nhập–Xuất–Tồn) và giá lô (phiếu xuất đã ghi sổ đọc lại ra số mới);
  · một lô trong họ ở kỳ khoá sổ của kho nó ⇒ chặn cả lần sửa;
  · lô không phải thành phẩm từ KCS ⇒ chặn; thiếu `kho:view_cost` ⇒ 403.
"""
from __future__ import annotations

from datetime import date, timedelta

import pytest

from app.models.audit import AuditLog
from app.models.role import SCOPE_ALL
from app.models.stock_lot import StockLot
from app.models.stock_request import StockRequest
from app.models.stock_voucher import StockVoucher, StockVoucherLine
from app.repositories.kho_khoa_so_repo import KhoKhoaSoRepository
from app.routers.kho_baocao import _nxt_compute
from app.routers.kho_voucher import get_service as voucher_service
from app.services import kho_gia_goc_service as gg
from tests.test_kho_de_nghi import _login, _mk_user
from tests.test_kho_lo_goc import _kho
from tests.test_san_xuat_kcs import (  # noqa: F401
    _batch,
    admin,
    customer,
    db,
    lsx_svc,
    orders,
)
from tests.test_san_xuat_nhap_kho_tp import _gui, _nhan


def _dung(db, orders, lsx_svc, admin, customer):
    """KCS gửi 90 → kho TP nhận 90 → điều chuyển 30 sang KHO-B. Trả (lô gốc, lô ở B, phiếu xuất nguồn)."""
    _to, cv, rb = _batch(db, orders, lsx_svc, admin, customer, dat=90, khong_dat=0, cuoi=True)
    r = _gui(db, cv, rb)
    a, b = _kho(db, "KHO-TP"), _kho(db, "KHO-B")
    _nhan(db, admin, r["request_id"], 90)
    tp_id = db.get(StockRequest, r["request_id"]).lines[0].hang_id
    [goc] = db.query(StockLot).filter_by(kho_id=a.id, hang_loai="vat_tu", hang_id=tp_id).all()

    svc = voucher_service(db)
    res = svc.dieu_chuyen(user=admin, kho_nguon_id=a.id, kho_den_id=b.id,
                          items=[{"hang_loai": "vat_tu", "hang_id": tp_id, "so_luong": 30}])
    svc.post(res["phieu_nhap"].id, admin)
    [o_b] = db.query(StockLot).filter_by(kho_id=b.id, hang_id=tp_id).all()
    return goc, o_b, db.get(StockVoucher, res["phieu_xuat"].id), a, b


def _dong_nhap(db, lot_id):
    return (db.query(StockVoucherLine).join(StockVoucher, StockVoucher.id == StockVoucherLine.voucher_id)
            .filter(StockVoucherLine.lot_id == lot_id, StockVoucher.loai == "NHAP").one())


def _mon(rows, ma_lo):
    return [x for x in rows["items"] if x["ma_lo"] == ma_lo]


def test_sua_gia_goc_lan_xuong_lo_dieu_chuyen_va_bao_cao(db, orders, lsx_svc, admin, customer):
    goc, o_b, px, a, b = _dung(db, orders, lsx_svc, admin, customer)
    assert goc.don_gia_nhap == 0 and o_b.lo_goc_id == goc.id
    svc = voucher_service(db)
    assert svc.cost_of(px) == 0

    [dong] = _mon(gg.ds_chua_gia_goc(db, q=goc.ma_lo, chi_chua_gia=True, page=1, size=20), goc.ma_lo)
    assert dong["don_gia"] == 0 and dong["don_gia_ban"] == 500 and dong["so_lo"] == 2
    assert dong["sl_con_lai"] == 90 and dong["kho_ten"] == "Kho KHO-TP"
    # Chỉ lô GỐC lên danh sách — lô ở KHO-B không thành dòng riêng.
    assert _mon(gg.ds_chua_gia_goc(db, q=o_b.ma_lo, chi_chua_gia=False, page=1, size=20), o_b.ma_lo) == []

    # Gõ trên lô CON cũng được — hệ quy về lô gốc.
    out = gg.sua_gia_goc(db, user=admin, lot_id=o_b.id, don_gia=12_000)
    assert out == {"lot_id": goc.id, "ma_lo": goc.ma_lo, "don_gia_cu": 0, "don_gia": 12_000,
                   "don_gia_nhap": 12_000, "so_lo": 2}

    db.expire_all()
    assert db.get(StockLot, goc.id).don_gia_nhap == 12_000
    assert db.get(StockLot, o_b.id).don_gia_nhap == 12_000
    assert _dong_nhap(db, goc.id).don_gia == 12_000 and _dong_nhap(db, o_b.id).don_gia == 12_000
    assert svc.cost_of(db.get(StockVoucher, px.id)) == 12_000 * 30          # phiếu xuất đã ghi sổ

    hom_nay = date.today()
    nxt = _nxt_compute(db, tu=hom_nay, den=hom_nay, kho_ids=[a.id, b.id])
    assert nxt[(a.id, "vat_tu", goc.hang_id)]["nhap_gt"] == 12_000 * 90
    assert nxt[(b.id, "vat_tu", goc.hang_id)]["nhap_gt"] == 12_000 * 30

    assert _mon(gg.ds_chua_gia_goc(db, q=goc.ma_lo, chi_chua_gia=True, page=1, size=20), goc.ma_lo) == []
    [sau] = _mon(gg.ds_chua_gia_goc(db, q=goc.ma_lo, chi_chua_gia=False, page=1, size=20), goc.ma_lo)
    assert sau["don_gia"] == 12_000
    [vet] = db.query(AuditLog).filter_by(action=gg.ACTION_SUA_GIA_GOC).all()
    assert vet.target == f"stock_lot:{goc.id}" and "0 → 12.000" in vet.detail and "2 lô" in vet.detail


def test_ky_khoa_o_kho_dich_chan_ca_lan_sua(db, orders, lsx_svc, admin, customer):
    goc, o_b, _px, _a, b = _dung(db, orders, lsx_svc, admin, customer)
    hom_nay = date.today()
    KhoKhoaSoRepository(db).add(kho_id=b.id, tu_ngay=hom_nay - timedelta(days=1),
                                den_ngay=hom_nay + timedelta(days=1), hanh_dong="khoa",
                                nguoi_khoa_id=admin.id)
    db.commit()

    with pytest.raises(gg.GiaGocError, match="Kho KHO-B.*khoá sổ"):
        gg.sua_gia_goc(db, user=admin, lot_id=goc.id, don_gia=9_000)
    db.expire_all()
    assert db.get(StockLot, goc.id).don_gia_nhap == 0 and _dong_nhap(db, goc.id).don_gia == 0


def test_lo_khong_phai_thanh_pham_tu_kcs_bi_chan(db, orders, lsx_svc, admin, customer):
    _batch(db, orders, lsx_svc, admin, customer, dat=10, khong_dat=0, cuoi=True)
    lot = db.query(StockLot).filter(StockLot.ma_lo.like("LOT-XL-%")).first()
    with pytest.raises(gg.GiaGocError, match="Chỉ sửa giá gốc cho thành phẩm nhập từ KCS"):
        gg.sua_gia_goc(db, user=admin, lot_id=lot.id, don_gia=1)
    with pytest.raises(gg.GiaGocKhongThay):
        gg.sua_gia_goc(db, user=admin, lot_id=99_999_999, don_gia=1)


def test_thieu_quyen_xem_gia_von_bi_403(client):
    _mk_user("t_thukho_gg", "Kho", dict(can_read=True, can_create=True, can_post=True, scope=SCOPE_ALL,
                                        can_view_stock=True))
    _mk_user("t_ketoan_gg", "Kế toán", dict(can_read=True, scope=SCOPE_ALL, can_view_stock=True,
                                            can_view_cost=True, can_close_book=True))
    tk, kt = _login(client, "t_thukho_gg"), _login(client, "t_ketoan_gg")

    assert client.patch("/api/kho/phieu/lo/999999/gia-goc", headers=tk, json={"don_gia": 1}).status_code == 403
    assert client.get("/api/kho/bao-cao/thanh-pham-chua-gia-goc", headers=tk).status_code == 403

    assert client.patch("/api/kho/phieu/lo/999999/gia-goc", headers=kt, json={"don_gia": 1}).status_code == 404
    assert client.patch("/api/kho/phieu/lo/999999/gia-goc", headers=kt, json={"don_gia": -5}).status_code == 422
    r = client.get("/api/kho/bao-cao/thanh-pham-chua-gia-goc", headers=kt, params={"page": 1, "size": 20})
    assert r.status_code == 200 and r.json() == {"items": [], "total": 0, "page": 1, "size": 20}
