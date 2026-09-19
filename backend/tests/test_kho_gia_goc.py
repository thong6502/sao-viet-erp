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
from app.models.customer import Customer
from app.models.lsx import Lsx
from app.models.order import Order
from app.models.role import SCOPE_ALL
from app.models.stock_lot import StockLot
from app.models.stock_request import StockRequest
from app.models.stock_voucher import StockVoucher, StockVoucherLine
from app.repositories.kho_khoa_so_repo import KhoKhoaSoRepository
from app.routers.kho_baocao import _nxt_compute
from app.routers.kho_request import _serialize
from app.routers.kho_voucher import _serialize as _serialize_phieu
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

    def _dong_phieu(v, xem_gia=True):
        return _serialize_phieu(v, svc=svc, db=db, can_view_cost=xem_gia).lines[0]

    # Phiếu XUẤT lô KCS 0 đ: "0 đ" là chưa có giá gốc, không phải miễn phí. Thiếu quyền giá ⇒ không lộ.
    assert _dong_phieu(px).chua_gia_goc and not _dong_phieu(px, xem_gia=False).chua_gia_goc
    # Dòng phiếu nói hàng của lệnh/đơn/khách nào + giá bán — đọc ở lô GỐC, kể cả phiếu nhập điều chuyển
    # ở KHO-B (dòng yêu cầu điều chuyển không có lệnh). Giá bán là tiền ⇒ thiếu quyền thì None.
    xuat = _dong_phieu(px)
    assert xuat.lsx_ma and xuat.order_ma and xuat.khach_hang and xuat.don_gia_ban == 500
    an = _dong_phieu(px, xem_gia=False)
    assert an.order_ma == xuat.order_ma and an.don_gia_ban is None
    nhap_b = _dong_phieu(db.get(StockVoucher, _dong_nhap(db, o_b.id).voucher_id))
    assert (nhap_b.lsx_ma, nhap_b.order_ma, nhap_b.khach_hang, nhap_b.don_gia_ban) == (
        xuat.lsx_ma, xuat.order_ma, xuat.khach_hang, 500)

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
    assert not _dong_phieu(db.get(StockVoucher, px.id)).chua_gia_goc

    hom_nay = date.today()
    nxt = _nxt_compute(db, tu=hom_nay, den=hom_nay, kho_ids=[a.id, b.id])
    assert nxt[(a.id, "vat_tu", goc.hang_id)]["nhap_gt"] == 12_000 * 90
    assert nxt[(b.id, "vat_tu", goc.hang_id)]["nhap_gt"] == 12_000 * 30

    assert _mon(gg.ds_chua_gia_goc(db, q=goc.ma_lo, chi_chua_gia=True, page=1, size=20), goc.ma_lo) == []
    [sau] = _mon(gg.ds_chua_gia_goc(db, q=goc.ma_lo, chi_chua_gia=False, page=1, size=20), goc.ma_lo)
    assert sau["don_gia"] == 12_000
    [vet] = db.query(AuditLog).filter_by(action=gg.ACTION_SUA_GIA_GOC).all()
    assert vet.target == f"stock_lot:{goc.id}" and "0 → 12.000" in vet.detail and "2 lô" in vet.detail


def test_dong_yeu_cau_kcs_doc_gia_goc_tu_lo_va_an_khi_thieu_quyen(db, orders, lsx_svc, admin, customer):
    """Màn yêu cầu nhập: dòng KCS giữ `don_gia` 0 mãi, giá gốc thật đọc ở lô sau khi kế toán gõ. Thiếu
    `view_cost` thì không một con số tiền nào ra khỏi máy chủ."""
    _to, cv, rb = _batch(db, orders, lsx_svc, admin, customer, dat=90, khong_dat=0, cuoi=True)
    r = _gui(db, cv, rb)

    def _dong(xem_gia):
        req = db.get(StockRequest, r["request_id"])
        return _serialize(req, db=db, can_view_stock=False, can_view_cost=xem_gia,
                          levels=None, on_hand=None).lines[0]

    chua_nhap = _dong(True)
    assert chua_nhap.tu_kcs and chua_nhap.gia_goc is None
    assert chua_nhap.don_gia_ban == 500 and chua_nhap.don_ban_ma

    a = _kho(db, "KHO-TP")
    _nhan(db, admin, r["request_id"], 90)
    db.expire_all()
    assert _dong(True).gia_goc is None                               # lô vào kho 0 đ
    [pn] = db.query(StockVoucher).filter_by(request_id=r["request_id"]).all()
    assert _serialize_phieu(pn, svc=voucher_service(db), db=db, can_view_cost=True).lines[0].chua_gia_goc
    [goc] = db.query(StockLot).filter_by(kho_id=a.id, hang_id=chua_nhap.hang_id).all()
    gg.sua_gia_goc(db, user=admin, lot_id=goc.id, don_gia=12_000)
    db.expire_all()
    assert _dong(True).gia_goc == 12_000
    assert not _serialize_phieu(db.get(StockVoucher, pn.id), svc=voucher_service(db), db=db,
                                can_view_cost=True).lines[0].chua_gia_goc

    assert _dong(True).tien_goc == 12_000 * 90

    an = _dong(False)
    assert an.tu_kcs
    assert (an.don_gia, an.gia_goc, an.tien_goc, an.don_gia_ban, an.don_ban_ma) == (None,) * 5


def test_tien_goc_dong_kcs_cong_tung_dot_khong_nhan_nguoc_gia_binh_quan(
        db, orders, lsx_svc, admin, customer):
    """Nhập hai đợt, kế toán gõ hai giá: giá dòng là bình quân làm tròn đồng, nhưng TIỀN là tổng hai
    phiếu — 1.873 × 90 = 168.570 lệch 30 đ so với 50 × 1.850 + 40 × 1.901 = 168.540."""
    _to, cv, rb = _batch(db, orders, lsx_svc, admin, customer, dat=90, khong_dat=0, cuoi=True)
    r = _gui(db, cv, rb)
    _nhan(db, admin, r["request_id"], 50)
    _nhan(db, admin, r["request_id"], 40)
    req = db.get(StockRequest, r["request_id"])
    lo1, lo2 = (db.query(StockLot).filter_by(kho_id=_kho(db, "KHO-TP").id, hang_id=req.lines[0].hang_id)
                .order_by(StockLot.id).all())
    gg.sua_gia_goc(db, user=admin, lot_id=lo1.id, don_gia=1_850)
    assert _serialize(db.get(StockRequest, r["request_id"]), db=db, can_view_stock=False,
                      can_view_cost=True, levels=None, on_hand=None).lines[0].tien_goc is None  # còn lô 0 đ
    gg.sua_gia_goc(db, user=admin, lot_id=lo2.id, don_gia=1_901)
    db.expire_all()
    dong = _serialize(db.get(StockRequest, r["request_id"]), db=db, can_view_stock=False,
                      can_view_cost=True, levels=None, on_hand=None).lines[0]
    assert (dong.gia_goc, dong.tien_goc) == (1_873, 168_540)


def test_dong_phieu_nhap_kcs_mang_don_va_gia_ban_ca_luc_nhap(db, orders, lsx_svc, admin, customer):
    """Phiếu nhập từ KCS nói hàng của lệnh/đơn/khách nào: còn nháp (chưa có lô) đọc dòng yêu cầu, ghi sổ
    rồi đọc lô gốc — hai đường phải ra cùng một nguồn. Giá bán chỉ khi có `view_cost`; nguồn thì không ẩn."""
    _to, cv, rb = _batch(db, orders, lsx_svc, admin, customer, dat=90, khong_dat=0, cuoi=True)
    r = _gui(db, cv, rb)
    [rl] = db.get(StockRequest, r["request_id"]).lines
    lenh = db.get(Lsx, rl.lsx_id)
    don = db.get(Order, lenh.order_id)
    nguon = (lenh.ma, don.order_no, db.get(Customer, don.customer_id).name)
    svc = voucher_service(db)

    def _dong(v_id, xem_gia=True):
        return _serialize_phieu(db.get(StockVoucher, v_id), svc=svc, db=db, can_view_cost=xem_gia).lines[0]

    pn = svc.create(user=admin, request_id=r["request_id"], kho_id=_kho(db, "KHO-TP").id,
                    lines=[{"request_line_id": rl.id, "so_luong": 90}])
    nhap = _dong(pn.id)
    assert nhap.lot_id is None and (nhap.lsx_ma, nhap.order_ma, nhap.khach_hang) == nguon
    assert nhap.chua_gia_goc and nhap.don_gia_ban == 500
    an = _dong(pn.id, xem_gia=False)
    assert (an.lsx_ma, an.order_ma, an.khach_hang) == nguon and an.don_gia_ban is None

    svc.post(pn.id, admin)
    db.expire_all()
    nhap = _dong(pn.id)
    assert nhap.lot_id and (nhap.lsx_ma, nhap.order_ma, nhap.khach_hang) == nguon
    assert nhap.chua_gia_goc and nhap.don_gia_ban == 500


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
