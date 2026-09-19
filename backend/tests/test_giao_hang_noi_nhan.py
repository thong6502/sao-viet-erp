"""Nơi nhận của yêu cầu giao — CHỌN từ khách, không gõ tay (chủ chốt 19/09/2026).

Không chọn ⇒ nơi nhận của đơn; chọn ⇒ id trong sổ địa chỉ / người liên hệ của ĐÚNG khách của đơn,
chụp lại chữ lúc lập. Lưu ý giao hàng luôn lấy của đơn.
"""
from __future__ import annotations

from datetime import date, timedelta

from app.db import SessionLocal
from app.models.customer import Customer, CustomerAddress, CustomerContact
from app.models.order import Order
from tests.test_giao_hang_api import _admin, _don_da_chot


def _so_khach(oid: int) -> tuple[int, int]:
    db = SessionLocal()
    try:
        o = db.get(Order, oid)
        o.delivery_note = "Gọi trước 30 phút"
        a = CustomerAddress(customer_id=o.customer_id, label="Kho Bắc Ninh",
                            address="KCN Quế Võ, lô B2", phone="0222")
        c = CustomerContact(customer_id=o.customer_id, name="Chị Hạnh", phone="0938")
        db.add_all([a, c])
        db.commit()
        return a.id, c.id
    finally:
        db.close()


def _yc(client, h, oid, lid, **them):
    return client.post("/api/giao-hang/requests", json={
        "order_id": oid, "ngay_can_giao": (date.today() + timedelta(days=2)).isoformat(),
        "lines": [{"order_line_id": lid, "qty": 10}], **them,
    }, headers=h)


def test_khong_chon_thi_lay_noi_nhan_va_luu_y_cua_don(client):
    h = _admin(client)
    oid, lid = _don_da_chot(suffix="nn1")
    _so_khach(oid)
    r = _yc(client, h, oid, lid)
    assert r.status_code == 201, r.text
    y = r.json()
    assert (y["dia_chi"], y["nguoi_nhan"], y["sdt_nguoi_nhan"]) == ("12 Le Loi, Q1", "Chi Lan", "0901234567")
    assert y["ghi_chu"] == "Gọi trước 30 phút"


def test_chon_tu_so_khach_thi_chup_lai_chu(client):
    h = _admin(client)
    oid, lid = _don_da_chot(suffix="nn2")
    aid, cid = _so_khach(oid)
    r = _yc(client, h, oid, lid, dia_chi_id=aid, lien_he_id=cid)
    assert r.status_code == 201, r.text
    y = r.json()
    assert (y["dia_chi"], y["nguoi_nhan"], y["sdt_nguoi_nhan"]) == ("KCN Quế Võ, lô B2", "Chị Hạnh", "0938")
    # Sửa: đổi về nơi nhận của đơn.
    r = client.put(f"/api/giao-hang/requests/{y['id']}",
                   json={"dia_chi_id": None, "lien_he_id": None}, headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["dia_chi"] == "12 Le Loi, Q1"


def test_dia_chi_cua_khach_khac_bi_chan(client):
    h = _admin(client)
    oid, lid = _don_da_chot(suffix="nn3")
    db = SessionLocal()
    try:
        k = Customer(code="KH-NN-LA", name="Khách lạ")
        db.add(k)
        db.flush()
        a = CustomerAddress(customer_id=k.id, label="Lạ", address="Nơi khác")
        db.add(a)
        db.commit()
        aid = a.id
    finally:
        db.close()
    r = _yc(client, h, oid, lid, dia_chi_id=aid)
    assert r.status_code == 400 and "không thuộc khách" in r.json()["detail"], r.text


def test_gui_chu_go_tay_bi_bo_qua(client):
    h = _admin(client)
    oid, lid = _don_da_chot(suffix="nn4")
    r = _yc(client, h, oid, lid, dia_chi="Gõ tay bừa", nguoi_nhan="Ai đó")
    assert r.status_code == 201, r.text
    assert r.json()["dia_chi"] == "12 Le Loi, Q1"


def test_don_va_khach_deu_khong_co_dia_chi_thi_bao_ro(client):
    h = _admin(client)
    oid, lid = _don_da_chot(suffix="nn5")
    db = SessionLocal()
    try:
        db.get(Order, oid).delivery_address = None
        db.commit()
    finally:
        db.close()
    r = _yc(client, h, oid, lid)
    assert r.status_code == 400 and "hồ sơ khách hàng" in r.json()["detail"], r.text


def test_tien_do_tra_so_noi_nhan_cua_khach(client):
    h = _admin(client)
    oid, _ = _don_da_chot(suffix="nn6")
    aid, cid = _so_khach(oid)
    n = client.get(f"/api/orders/{oid}/tien-do", headers=h).json()["noi_nhan"]
    assert n["dia_chi"] == "12 Le Loi, Q1" and n["luu_y"] == "Gọi trước 30 phút"
    assert [x["id"] for x in n["so_dia_chi"]] == [aid]
    assert [x["id"] for x in n["lien_he"]] == [cid]
