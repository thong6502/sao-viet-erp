"""Giao hàng làm lại 19/09/2026 — "không được giao phần chưa nhập kho" + các lỗ treo cũ.

Thiết kế: `docs/superpowers/plans/2026-09-19-giao-hang-tien-do-don.md`.
"""
from __future__ import annotations

from datetime import date, timedelta

from app.db import SessionLocal
from app.models.lsx import Lsx
from app.models.order import Order
from app.models.stock_request import StockRequest, StockRequestLine
from app.models.user import User
from app.services.thanh_pham_khai_bao import cum_ban, khai_mot_dong
from tests.test_giao_hang_api import (
    _admin,
    _don_da_chot,
    _gui_yeu_cau_xuat_kho,
    _len_kh,
    _nap_ton,
    _tai_xe,
    _tao_yc,
)


def _yc(client, h, oid, lid, qty):
    return client.post("/api/giao-hang/requests", json={
        "order_id": oid, "ngay_can_giao": (date.today() + timedelta(days=2)).isoformat(),
        "lines": [{"order_line_id": lid, "qty": qty}],
    }, headers=h)


def test_KHONG_TON_thi_khong_lap_duoc_yeu_cau(client):
    h = _admin(client)
    oid, lid = _don_da_chot(suffix="gd1", nap_ton=False)
    r = _yc(client, h, oid, lid, 10)
    assert r.status_code == 400, r.text
    assert "chưa nhập kho" in r.json()["detail"]


def test_TON_MOT_PHAN_chi_lap_duoc_toi_so_ton(client):
    h = _admin(client)
    oid, lid = _don_da_chot(suffix="gd2", nap_ton=False)
    _nap_ton(oid, so=30)
    assert _yc(client, h, oid, lid, 31).status_code == 400
    assert _yc(client, h, oid, lid, 30).status_code == 201
    # 30 đã bị yêu cầu đầu giữ ⇒ hết.
    assert _yc(client, h, oid, lid, 1).status_code == 400


def _lenh_va_kho_nhan(oid: int, *, de_nghi: float, da_nhan: float) -> None:
    """Đơn có LỆNH, KCS đã gửi yêu cầu nhập cho lệnh đó, kho nhận `da_nhan`."""
    db = SessionLocal()
    try:
        order = db.get(Order, oid)
        ln = order.lines[0]
        l = Lsx(ma=f"LSX-GD-{oid}", ten=ln.description, order_id=oid, order_line_id=ln.id,
                so_luong_dat=int(ln.qty))
        db.add(l)
        db.flush()
        tp = khai_mot_dong(db, order, cum_ban(order)[0].dong_dau)
        admin = db.query(User).filter(User.username == "admin").one()
        req = StockRequest(ma=f"YCNK-GD-{oid}", loai="NHAP", nguoi_tao_id=admin.id,
                           trang_thai="partial", san_xuat_cong_viec_id=987654)
        req.lines.append(StockRequestLine(hang_loai="vat_tu", hang_id=tp.id, dvt=tp.don_vi_gia or "hop",
                                          sl_de_nghi=de_nghi, sl_duyet=de_nghi, sl_da_ung=da_nhan,
                                          lsx_id=l.id))
        db.add(req)
        db.commit()
    finally:
        db.close()


def test_DON_CO_LENH_chi_giao_phan_kho_DA_NHAN_cua_chinh_don(client):
    """Tồn chung của mã (100, nạp sẵn — ví dụ hàng của đơn khác trùng tên) KHÔNG được tính: đơn có
    lệnh thì chỉ giao phần kho đã nhận từ lệnh của nó (40)."""
    h = _admin(client)
    oid, lid = _don_da_chot(suffix="gd3")               # tồn thật 100
    _lenh_va_kho_nhan(oid, de_nghi=60, da_nhan=40)
    assert _yc(client, h, oid, lid, 41).status_code == 400
    assert _yc(client, h, oid, lid, 40).status_code == 201

    td = client.get(f"/api/orders/{oid}/tien-do", headers=h)
    assert td.status_code == 200, td.text
    cum = td.json()["cum"][0]
    assert cum["kho_de_nghi"] == 60 and cum["kho_da_nhan"] == 40 and cum["cho_kho"] == 20
    assert cum["dang_giu"] == 40 and cum["giao_duoc"] == 0
    assert td.json()["yeu_cau"][0]["trang_thai"] == "cho_len_ke_hoach"


def test_HUY_CHUYEN_thi_yeu_cau_huy_duoc_va_nha_hang(client):
    """Bẫy cũ: unique index mg 0229 cấm chuyến thứ hai, còn huỷ yêu cầu bị chặn vì 'còn chuyến' ⇒
    yêu cầu kẹt mãi, hàng bị giữ mãi."""
    h = _admin(client)
    oid, lid = _don_da_chot(suffix="gd4")
    yc = _tao_yc(client, h, oid, lid, qty=100)
    trip = _len_kh(client, h, yc["id"], _tai_xe("TX gd4")).json()["trip"]["id"]
    r = client.post(f"/api/giao-hang/plans/{trip}/huy", json={"ly_do": "Xe hong"}, headers=h)
    assert r.status_code == 200, r.text

    ds = client.get(f"/api/giao-hang/requests?order_id={oid}", headers=h).json()["items"]
    assert ds[0]["trang_thai"] == "chuyen_da_huy"
    con = client.get(f"/api/giao-hang/orders/{oid}/con-phai-giao", headers=h).json()
    assert con["lines"][0]["con_phai_giao"] == 100
    r = client.post(f"/api/giao-hang/requests/{yc['id']}/huy", json={"ly_do": "Lap lai"}, headers=h)
    assert r.status_code == 200, r.text


def test_HUY_DON_bi_chan_khi_con_yeu_cau_dang_chay(client):
    h = _admin(client)
    oid, lid = _don_da_chot(suffix="gd5")
    yc = _tao_yc(client, h, oid, lid, qty=10)
    r = client.post(f"/api/orders/{oid}/cancel",
                    json={"reason": "Khach huy", "fault": "khach"}, headers=h)
    assert r.status_code == 409, r.text
    assert yc["code"] in r.json()["detail"]


def test_GUI_XUAT_KHO_kiem_lai_ton_that(client):
    h = _admin(client)
    oid, lid = _don_da_chot(suffix="gd6")
    yc = _tao_yc(client, h, oid, lid, qty=100)
    trip = _len_kh(client, h, yc["id"], _tai_xe("TX gd6")).json()["trip"]["id"]
    # Kho đã xuất hàng cho việc khác trong lúc chờ xếp chuyến.
    from app.models.stock_lot import StockLot
    db = SessionLocal()
    try:
        for lot in db.query(StockLot).filter(StockLot.ma_lo.like(f"LO-GH-{oid}-%")).all():
            lot.sl_con_lai = 50
        db.commit()
    finally:
        db.close()
    from app.models.kho_hang import KhoHang
    db = SessionLocal()
    try:
        kho_id = db.query(KhoHang).filter(KhoHang.ma == "KTP").one().id
    finally:
        db.close()
    r = client.post(f"/api/giao-hang/plans/{trip}/yeu-cau-xuat-kho", json={"kho_id": kho_id},
                    headers=h)
    assert r.status_code == 400, r.text
    assert "chỉ còn 50" in r.json()["detail"]
