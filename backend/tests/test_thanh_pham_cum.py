"""Thành phẩm theo CỤM BÁN (design nhập kho thành phẩm §3).

Kho giữ đúng thứ khách mua: Ruột 500 + Bìa 500 cùng nhãn nhóm là MỘT quyển sách, một mã kho. Luật
khoá là bản Python của `frontend/src/utils/gop-nhom.ts` (nhãn + SL) — lệch là kho và tờ xác nhận
đơn gọi cùng một món bằng hai cái tên.
"""
from __future__ import annotations

from datetime import date, timedelta

from app.db import SessionLocal
from app.models.customer import Customer
from app.models.delivery import DeliveryRequest
from app.models.order import STATUS_ORDERED, Order, OrderLine
from app.models.vat_lieu_kho import VatTuInAn
from app.services.thanh_pham_khai_bao import cum_ban, gia_ban_cum, khai_cho_don
from tests.test_giao_hang_api import _admin, _di_toi_dang_giao, _len_kh, _tai_xe


def _don(suffix: str, dong: list[dict]) -> tuple[int, list[int]]:
    db = SessionLocal()
    try:
        kh = Customer(code=f"KH-CUM-{suffix}", name=f"Khach cum {suffix}")
        db.add(kh)
        db.flush()
        o = Order(order_no=f"DH-CUM-{suffix}", customer_id=kh.id, status=STATUS_ORDERED,
                  delivery_address="1 Le Loi")
        for d in dong:
            o.lines.append(OrderLine(vat_pct_estimate=0, **d))
        db.add(o)
        db.commit()
        return o.id, [ln.id for ln in sorted(o.lines, key=lambda x: x.id)]
    finally:
        db.close()


SACH = [
    {"description": "Ruột sách", "qty": 500, "don_vi_tinh": "cái", "nhom": "Kỷ yếu 25 năm",
     "dvt_nhom": "cuốn", "line_total": 9_000_000},
    {"description": "Bìa sách", "qty": 500, "don_vi_tinh": "cái", "nhom": "kỷ yếu 25 năm ",
     "dvt_nhom": "cuốn", "line_total": 2_500_000},
]


def test_dong_khong_nhan_moi_dong_mot_cum(client):
    oid, _ = _don("le", [
        {"description": "Hộp A", "qty": 100, "don_vi_tinh": "hộp", "line_total": 1_000_000},
        {"description": "Hộp B", "qty": 100, "don_vi_tinh": "hộp", "line_total": 2_000_000},
    ])
    db = SessionLocal()
    try:
        cums = cum_ban(db.get(Order, oid))
        assert [c.ten for c in cums] == ["Hộp A", "Hộp B"]
        assert [gia_ban_cum(c) for c in cums] == [10_000, 20_000]
    finally:
        db.close()


def test_ruot_bia_cung_nhan_cung_sl_la_MOT_ma_ten_nhan_dvt_cum(client):
    oid, _ = _don("sach", SACH)
    db = SessionLocal()
    try:
        order = db.get(Order, oid)
        cums = cum_ban(order)
        assert len(cums) == 1
        c = cums[0]
        assert (c.ten, c.dvt, c.so_luong, len(c.dong)) == ("Kỷ yếu 25 năm", "cuốn", 500, 2)
        assert gia_ban_cum(c) == 23_000               # (9.000.000 + 2.500.000) ÷ 500
        ma = khai_cho_don(db, order)
        db.commit()
        assert len(ma) == 1
        h = db.get(VatTuInAn, ma[0].id)
        assert h.ten == "Kỷ yếu 25 năm" and h.don_vi_gia == "cuon" and h.la_thanh_pham
    finally:
        db.close()


def test_cung_nhan_khac_sl_tach_hai_cum(client):
    oid, _ = _don("lech", [
        {**SACH[0], "qty": 10_000},
        {**SACH[1], "qty": 10_000},
        {**SACH[0], "qty": 100},
    ])
    db = SessionLocal()
    try:
        cums = cum_ban(db.get(Order, oid))
        assert [(c.so_luong, len(c.dong)) for c in cums] == [(10_000, 2), (100, 1)]
    finally:
        db.close()


def test_chua_co_thanh_tien_thi_gia_ban_trong(client):
    oid, _ = _don("0d", [{"description": "Mẫu", "qty": 10, "don_vi_tinh": "cái", "line_total": None}])
    db = SessionLocal()
    try:
        assert gia_ban_cum(cum_ban(db.get(Order, oid))[0]) is None
    finally:
        db.close()


def _yc_giao(client, h, oid, lines):
    return client.post("/api/giao-hang/requests", json={
        "order_id": oid, "ngay_can_giao": (date.today() + timedelta(days=3)).isoformat(),
        "lines": lines,
    }, headers=h)


def test_yeu_cau_giao_bung_ca_cum_va_xuat_kho_MOT_dong(client):
    h = _admin(client)
    oid, (ruot, bia) = _don("giao", SACH)
    r = _yc_giao(client, h, oid, [{"order_line_id": bia, "qty": 200}])
    assert r.status_code == 201, r.text
    db = SessionLocal()
    try:
        req = db.get(DeliveryRequest, r.json()["id"])
        dong = sorted(req.lines, key=lambda x: x.order_line_id)
        assert [(d.order_line_id, d.qty) for d in dong] == [(ruot, 200), (bia, 200)]
        assert dong[0].hang_id is not None and dong[1].hang_id is None
    finally:
        db.close()
    con = client.get(f"/api/giao-hang/orders/{oid}/con-phai-giao", headers=h).json()
    assert {x["order_line_id"]: x["con_phai_giao"] for x in con["lines"]} == {ruot: 300, bia: 300}
    # Form gom hai dòng thành MỘT ô theo khoá cụm máy chủ trả.
    khoa = {x["order_line_id"]: (x["cum_khoa"], x["cum_ten"], x["cum_dvt"]) for x in con["lines"]}
    assert khoa[ruot] == khoa[bia] and khoa[ruot][0] and khoa[ruot][1:] == ("Kỷ yếu 25 năm", "cuốn")
    ct = client.get(f"/api/giao-hang/requests/{r.json()['id']}", headers=h).json()
    assert {x["cum_khoa"] for x in ct["request"]["lines"]} == {khoa[ruot][0]}

    nv = _tai_xe("Tai xe cum")
    trip = _len_kh(client, h, r.json()["id"], nv).json()["trip"]["id"]
    xuat = client.get(f"/api/giao-hang/plans/{trip}/hang-can-xuat", headers=h)
    assert xuat.status_code == 200, xuat.text
    assert [(d["sl_de_nghi"]) for d in xuat.json()] == [200]


def test_hai_dong_cung_cum_khac_sl_bi_chan(client):
    h = _admin(client)
    oid, (ruot, bia) = _don("chan", SACH)
    r = _yc_giao(client, h, oid, [{"order_line_id": ruot, "qty": 200},
                                  {"order_line_id": bia, "qty": 100}])
    assert r.status_code == 400
    assert "Kỷ yếu" in r.text


def test_giao_thieu_ghi_so_thuc_nhan_cho_ca_cum(client):
    h = _admin(client)
    oid, (ruot, bia) = _don("thieu", SACH)
    yc = _yc_giao(client, h, oid, [{"order_line_id": ruot, "qty": 200}]).json()
    nv = _tai_xe("Tai xe cum thieu")
    trip = _len_kh(client, h, yc["id"], nv).json()["trip"]["id"]
    _di_toi_dang_giao(client, h, trip)
    r = client.post(f"/api/giao-hang/trips/{trip}/ket-qua", json={
        "ket_qua": "giao_thieu", "km": 5, "nguoi_nhan_thuc_te": "Anh Ba",
        "so_thuc_nhan": [{"order_line_id": ruot, "qty": 150}],
    }, headers=h)
    assert r.status_code == 200, r.text
    con = client.get(f"/api/giao-hang/orders/{oid}/con-phai-giao", headers=h).json()
    assert {x["order_line_id"]: x["da_giao"] for x in con["lines"]} == {ruot: 150, bia: 150}
