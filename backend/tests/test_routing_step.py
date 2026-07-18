"""Routing riêng mỗi lệnh (§13.2) — copy từ job spec + kế hoạch sửa.

Verify THẬT qua HTTP: bung COPY routing (theo `thu_tu`, tổ từ `cong_doan.department_id`) · thêm /
sửa / xóa bước · đổi thứ tự (chỉ khi nháp, chặn sau phát).
Dùng fixture `client` (conftest) + SessionLocal để dựng job spec (PTG) nền.

(Module theo dõi thực thi xưởng — bắt đầu/hoàn thành bước qua QR + màn tổ — đã GỠ.)
"""
from __future__ import annotations

from app.db import SessionLocal
from app.models.lenh_san_xuat import LenhSanXuat
from app.models.order import Order, OrderLine
from app.models.phieu_tinh_gia import PhieuThanhPham, PhieuThanhPhan, PhieuTinhGia


def _headers(client) -> dict[str, str]:
    login = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
    assert login.status_code == 200, login.text
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


def _seed_don_2steps() -> int:
    """PTG + 1 ấn phẩm + 2 bước routing (Cán @cd2, Bế @cd3) + đơn 'ordered'. Trả order_id."""
    db = SessionLocal()
    try:
        ptg = PhieuTinhGia(ma="PTG-RS-1", ten_san_pham="Sách", so_luong=500)
        db.add(ptg)
        db.flush()
        ptp = PhieuThanhPhan(phieu_id=ptg.id, thu_tu=1, ten="Ruột", so_luong=500)
        db.add(ptp)
        db.flush()
        db.add(PhieuThanhPham(thanh_phan_id=ptp.id, thu_tu=1, cong_doan_id=2, ten="Cán màng"))
        db.add(PhieuThanhPham(thanh_phan_id=ptp.id, thu_tu=2, cong_doan_id=3, ten="Bế"))
        order = Order(order_no="DH-RS-1", status="ordered")
        db.add(order)
        db.flush()
        db.add(OrderLine(order_id=order.id, description="Sách", qty=500, phieu_thanh_phan_id=ptp.id))
        db.commit()
        return order.id
    finally:
        db.close()


def _bung(client, h, order_id: int) -> int:
    r = client.post("/api/lenh-sx/lenh/bung", json={"order_id": order_id}, headers=h)
    assert r.status_code == 201, r.text
    return r.json()[0]["id"]


def test_bung_copies_routing_in_order(client):
    """Bung → copy đúng công đoạn job spec theo thu_tu, mọi bước 'cho'; routing có trong detail."""
    h = _headers(client)
    lenh_id = _bung(client, h, _seed_don_2steps())
    routing = client.get(f"/api/lenh-sx/lenh/{lenh_id}/routing", headers=h).json()
    assert [s["ten"] for s in routing] == ["Cán màng", "Bế"]
    assert [s["thu_tu"] for s in routing] == [1, 2]
    assert [s["cong_doan_id"] for s in routing] == [2, 3]
    detail = client.get(f"/api/lenh-sx/lenh/{lenh_id}", headers=h).json()
    assert len(detail["routing"]) == 2


def test_them_sua_xoa_buoc(client):
    """Kế hoạch thêm bước (cuối) → sửa tổ → xóa; đều khi bước còn 'cho'."""
    h = _headers(client)
    lenh_id = _bung(client, h, _seed_don_2steps())
    r = client.post(f"/api/lenh-sx/lenh/{lenh_id}/routing", json={"cong_doan_id": 9, "to_id": 5}, headers=h)
    assert r.status_code == 201, r.text
    routing = r.json()
    assert len(routing) == 3
    new_id = routing[-1]["id"]
    assert routing[-1]["thu_tu"] == 3 and routing[-1]["to_id"] == 5
    r2 = client.put(f"/api/lenh-sx/routing/{new_id}", json={"cong_doan_id": 9, "to_id": 7}, headers=h)
    assert r2.status_code == 200, r2.text
    assert next(s for s in r2.json() if s["id"] == new_id)["to_id"] == 7
    r3 = client.delete(f"/api/lenh-sx/routing/{new_id}", headers=h)
    assert r3.status_code == 200, r3.text
    assert len(r3.json()) == 2


def test_reorder_only_when_nhap(client):
    """Đổi thứ tự OK khi nháp; chặn 409 sau khi lệnh đã phát (đang chạy)."""
    h = _headers(client)
    lenh_id = _bung(client, h, _seed_don_2steps())
    ids = [s["id"] for s in client.get(f"/api/lenh-sx/lenh/{lenh_id}/routing", headers=h).json()]
    r = client.post(f"/api/lenh-sx/lenh/{lenh_id}/routing/reorder", json={"step_ids": list(reversed(ids))}, headers=h)
    assert r.status_code == 200, r.text
    assert [s["ten"] for s in r.json()] == ["Bế", "Cán màng"]
    # mô phỏng đã phát: lệnh sang đang chạy → reorder chặn
    db = SessionLocal()
    try:
        db.get(LenhSanXuat, lenh_id).trang_thai = "dang_chay"
        db.commit()
    finally:
        db.close()
    r2 = client.post(f"/api/lenh-sx/lenh/{lenh_id}/routing/reorder", json={"step_ids": ids}, headers=h)
    assert r2.status_code == 409


