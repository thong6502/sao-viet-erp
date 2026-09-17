"""Lô theo ĐƠN khi kho xuất cho Giao hàng (design nhập kho thành phẩm §6).

Danh mục Thành phẩm gộp mã theo tên nên một mã có thể mang hàng của nhiều đơn. Hàng đơn nào giao đúng
đơn đó, tách bằng LÔ (lô → lô gốc → dòng yêu cầu → lệnh → đơn → khách):
  · gợi ý lô của chính đơn đang giao trước → lô không nguồn → lô đơn khác cùng khách (kèm cảnh báo);
    lô của khách khác không được gợi ý;
  · lập phiếu xuất chọn lô của khách khác ⇒ chặn; lô đơn khác cùng khách vẫn cho.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy import inspect as sa_inspect

from app.models.customer import Customer
from app.models.delivery import LG_DA_LEN_KE_HOACH, DeliveryRequest, DeliveryTrip
from app.models.employee import Employee
from app.models.lsx import Lsx
from app.models.order import Order
from app.models.stock_lot import StockLot
from app.models.stock_request import StockRequest
from app.routers.kho_voucher import get_service as voucher_service
from app.services.san_xuat.vat_tu_de_nghi import _hang_service, _req_service
from app.services.stock_voucher_service import StockVoucherError
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


def _nhan_ban(db, obj, **doi):
    """Chép một hàng ORM (bỏ khoá chính) rồi đè vài cột — dựng nhanh đơn / lệnh thứ hai."""
    m = sa_inspect(type(obj))
    data = {c.key: getattr(obj, c.key) for c in m.column_attrs if c.key != "id"}
    data.update(doi)
    moi = type(obj)(**data)
    db.add(moi)
    db.flush()
    return moi


def _lo_cua_lenh(db, admin, kho, tp, dvt, lsx_id, so_luong, *, ma_yc) -> StockLot:
    """Nhập thường một lô thành phẩm có dòng yêu cầu trỏ lệnh `lsx_id` (None = lô không nguồn)."""
    svc = voucher_service(db)
    req = _req_service(db, _hang_service(db)).create(
        user=admin, loai="NHAP", ma=ma_yc, kho_id=kho.id,
        lines=[{"hang_loai": "vat_tu", "hang_id": tp, "dvt": dvt, "sl_de_nghi": so_luong,
                "lsx_id": lsx_id}],
    )
    [ln] = req.lines
    v = svc.create(user=admin, request_id=req.id, kho_id=kho.id,
                   lines=[{"request_line_id": ln.id, "so_luong": so_luong}])
    svc.post(v.id, admin)
    [lot] = db.query(StockLot).filter_by(voucher_id=v.id).all()
    return lot


def _dung(db, orders, lsx_svc, admin, customer):
    """Bốn lô cùng mã TP ở KHO-TP: đơn A (từ KCS), không nguồn, đơn B cùng khách, đơn C khách khác.
    Nhập theo thứ tự để FIFO thuần sẽ xếp: khác khách → cùng khách → không nguồn → đơn A."""
    _to, cv, rb = _batch(db, orders, lsx_svc, admin, customer, dat=40, khong_dat=0, cuoi=True)
    lenh_a = db.get(Lsx, cv.lsx_id)
    don_a = db.get(Order, lenh_a.order_id)
    r = _gui(db, cv, rb)
    rl = db.get(StockRequest, r["request_id"]).lines[0]
    tp, dvt = rl.hang_id, rl.dvt
    kho = _kho(db, "KHO-TP")

    khach_khac = Customer(code="KH-KHAC", name="Khách Khác")
    db.add(khach_khac)
    db.flush()
    don_b = _nhan_ban(db, don_a, order_no="DH-B")
    don_c = _nhan_ban(db, don_a, order_no="DH-C", customer_id=khach_khac.id)
    lenh_b = _nhan_ban(db, lenh_a, ma="LSX-B", order_id=don_b.id)
    lenh_c = _nhan_ban(db, lenh_a, ma="LSX-C", order_id=don_c.id)
    db.commit()

    lo_c = _lo_cua_lenh(db, admin, kho, tp, dvt, lenh_c.id, 20, ma_yc="DNN-C")
    lo_b = _lo_cua_lenh(db, admin, kho, tp, dvt, lenh_b.id, 20, ma_yc="DNN-B")
    lo_trong = _lo_cua_lenh(db, admin, kho, tp, dvt, None, 20, ma_yc="DNN-T")
    _nhan(db, admin, r["request_id"], 40)
    [lo_a] = (db.query(StockLot)
              .filter(StockLot.kho_id == kho.id, StockLot.hang_id == tp,
                      StockLot.id.notin_([lo_c.id, lo_b.id, lo_trong.id])).all())
    # Ép ngày nhập để FIFO thuần ra đúng thứ tự dựng (các lô cùng ngày thì thứ tự id cũng vậy).
    hom_nay = date.today()
    for i, lot in enumerate([lo_c, lo_b, lo_trong, lo_a]):
        lot.ngay_nhap = hom_nay - timedelta(days=4 - i)
    db.commit()

    emp = Employee(code="NV-GIAO-LTD", full_name="Tài xế lô theo đơn")
    db.add(emp)
    db.flush()
    ycgh = DeliveryRequest(code="YCGH-LTD", order_id=don_a.id, customer_id=don_a.customer_id,
                           ngay_can_giao=hom_nay)
    db.add(ycgh)
    db.flush()
    bay_gio = datetime.now(timezone.utc)
    trip = DeliveryTrip(request_id=ycgh.id, lan_thu=1, employee_id=emp.id, gio_lay_hang=bay_gio,
                        gio_du_kien_giao=bay_gio + timedelta(hours=2), trang_thai=LG_DA_LEN_KE_HOACH)
    db.add(trip)
    db.commit()
    xuat = _req_service(db, _hang_service(db)).create(
        user=admin, loai="XUAT", ma="DNX-LTD", kho_id=kho.id, delivery_trip_id=trip.id,
        lines=[{"hang_loai": "vat_tu", "hang_id": tp, "dvt": dvt, "sl_de_nghi": 70}],
    )
    return {"kho": kho, "tp": tp, "xuat": xuat, "don_a": don_a,
            "lo": {"a": lo_a, "b": lo_b, "c": lo_c, "trong": lo_trong}}


def test_goi_y_lo_dung_don_truoc_bo_lo_khach_khac(db, orders, lsx_svc, admin, customer):
    d = _dung(db, orders, lsx_svc, admin, customer)
    svc = voucher_service(db)
    lo = d["lo"]
    hang = ("vat_tu", d["tp"])

    # Không gắn đơn: FEFO/FIFO thuần như cũ, vẫn trả nguồn để kho nhìn.
    rows, thieu = svc.suggest_allocation(hang, d["kho"].id, 80)
    assert [r["lot_id"] for r in rows] == [lo["c"].id, lo["b"].id, lo["trong"].id, lo["a"].id]
    assert thieu == 0 and all(r["canh_bao"] is None for r in rows)
    assert rows[0]["khach_hang"] == "Khách Khác" and rows[0]["order_ma"] == "DH-C"

    # Xuất cho Giao hàng đơn A: đơn A → không nguồn → đơn B cùng khách (cảnh báo); lô khách khác bị bỏ.
    rows, thieu = svc.suggest_allocation(hang, d["kho"].id, 70, request_id=d["xuat"].id)
    assert [(r["lot_id"], r["so_luong"]) for r in rows] == [
        (lo["a"].id, 40), (lo["trong"].id, 20), (lo["b"].id, 10)]
    assert thieu == 0
    assert rows[0]["order_ma"] == d["don_a"].order_no and rows[0]["canh_bao"] is None
    assert rows[1]["order_ma"] is None and rows[1]["canh_bao"] is None
    assert rows[2]["canh_bao"] == "Lô này sản xuất cho đơn DH-B"

    # Cần nhiều hơn tồn không tính lô khách khác ⇒ báo thiếu, không lén lấy lô đó.
    rows, thieu = svc.suggest_allocation(hang, d["kho"].id, 100, request_id=d["xuat"].id)
    assert lo["c"].id not in {r["lot_id"] for r in rows} and thieu == 20


def test_lap_phieu_xuat_chan_lo_khach_khac_cho_lo_cung_khach(db, orders, lsx_svc, admin, customer):
    d = _dung(db, orders, lsx_svc, admin, customer)
    svc = voucher_service(db)
    [ln] = d["xuat"].lines
    kho_id = d["kho"].id

    with pytest.raises(StockVoucherError, match="Lô .* sản xuất cho khách Khách Khác"):
        svc.create(user=admin, request_id=d["xuat"].id, kho_id=kho_id, lines=[
            {"request_line_id": ln.id, "so_luong": 40, "lot_id": d["lo"]["a"].id},
            {"request_line_id": ln.id, "so_luong": 20, "lot_id": d["lo"]["c"].id},
            {"request_line_id": ln.id, "so_luong": 10, "lot_id": d["lo"]["b"].id},
        ])

    v = svc.create(user=admin, request_id=d["xuat"].id, kho_id=kho_id, lines=[
        {"request_line_id": ln.id, "so_luong": 40, "lot_id": d["lo"]["a"].id},
        {"request_line_id": ln.id, "so_luong": 20, "lot_id": d["lo"]["b"].id},
        {"request_line_id": ln.id, "so_luong": 10, "lot_id": d["lo"]["trong"].id},
    ])
    assert {x.lot_id for x in v.lines} == {d["lo"]["a"].id, d["lo"]["b"].id, d["lo"]["trong"].id}


def test_yeu_cau_xuat_thuong_khong_rang_buoc_khach(db, orders, lsx_svc, admin, customer):
    """Xuất không sinh từ chuyến giao (vd điều chuyển, xuất nội bộ) — không có đơn đích để so."""
    d = _dung(db, orders, lsx_svc, admin, customer)
    svc = voucher_service(db)
    req = _req_service(db, _hang_service(db)).create(
        user=admin, loai="XUAT", ma="DNX-THUONG", kho_id=d["kho"].id,
        lines=[{"hang_loai": "vat_tu", "hang_id": d["tp"], "dvt": d["xuat"].lines[0].dvt,
                "sl_de_nghi": 20}],
    )
    assert svc.requests.don_giao_cua_yeu_cau(req.id) is None
    v = svc.create(user=admin, request_id=req.id, kho_id=d["kho"].id, lines=[
        {"request_line_id": req.lines[0].id, "so_luong": 20, "lot_id": d["lo"]["c"].id}])
    assert v.lines[0].lot_id == d["lo"]["c"].id


def test_danh_sach_lo_tra_nguon_va_an_gia_ban_khi_thieu_quyen(client):
    """`/lo/danh-sach` có thêm nguồn lô; giá bán là số tiền nên chỉ trả khi có `view_cost`. DB seed
    không có lô thành phẩm nào nên chỉ soát khoá có mặt và không nổ."""
    from app.models.role import SCOPE_ALL
    from tests.test_kho_de_nghi import _login, _mk_user

    _mk_user("t_thukho_ltd", "Kho", dict(can_read=True, can_create=True, can_post=True, scope=SCOPE_ALL,
                                         can_view_stock=True))
    tk = _login(client, "t_thukho_ltd")
    r = client.get("/api/kho/phieu/lo/danh-sach", headers=tk, params={"con_hang": "false"})
    assert r.status_code == 200
    for row in r.json():
        assert {"lo_goc_id", "lsx_ma", "order_ma", "khach_hang", "tu_kcs"} <= row.keys()
        assert row["don_gia_ban"] is None and row["don_gia_nhap"] is None
