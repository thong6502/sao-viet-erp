"""Kế hoạch & Lệnh sản xuất — API integration tests (VERIFY THẬT của Chunk 2 + 3).

Đi trọn luồng qua HTTP (router → service → repo → DB in-memory):
  tạo Đơn + ấn phẩm (PTP) → bung → ghép → gán máy → duyệt mẫu → phát → ghi sản lượng → nhập kho
  → lệnh XONG + đơn "xong sản xuất".
Cổng (record-only vẫn giữ toàn vẹn trạng thái):
  - phát bị CHẶN khi thiếu máy / chưa duyệt mẫu (422),
  - ghi sản lượng bị CHẶN trước khi phát (409),
  - bung IDEMPOTENT (gọi 2 lần không nhân đôi).
Dùng fixture `client` (conftest) + SessionLocal (chung StaticPool) để dựng dữ liệu nền.
"""
from __future__ import annotations

from app.db import SessionLocal
from app.models.order import Order, OrderLine
from app.models.phieu_tinh_gia import PhieuThanhPham, PhieuThanhPhan, PhieuTinhGia


def _headers(client) -> dict[str, str]:
    login = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
    assert login.status_code == 200, login.text
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


def _seed_don_ptp(*, qty: int = 1000, so_luong: int = 1000) -> tuple[int, int]:
    """PTG + 1 ấn phẩm (PhieuThanhPhan) + 1 bước routing + Đơn 'ordered' + dòng đơn trỏ ấn phẩm.

    Trả (order_id, ptp_id). DB làm lại sạch mỗi test (fixture client) nên mã cố định không đụng nhau.
    """
    db = SessionLocal()
    try:
        ptg = PhieuTinhGia(ma="PTG-LSX-1", ten_san_pham="Catalogue", so_luong=so_luong)
        db.add(ptg)
        db.flush()
        ptp = PhieuThanhPhan(phieu_id=ptg.id, thu_tu=1, ten="Ruột", so_luong=so_luong, may_id=7)
        db.add(ptp)
        db.flush()
        # 1 bước finishing (routing) cho thực tế — bế @ công đoạn 3 (soft-ref).
        db.add(PhieuThanhPham(thanh_phan_id=ptp.id, thu_tu=1, cong_doan_id=3, ten="Bế"))
        order = Order(order_no="DH-LSX-1", status="ordered")
        db.add(order)
        db.flush()
        db.add(OrderLine(
            order_id=order.id, description="Catalogue", qty=qty, phieu_thanh_phan_id=ptp.id,
        ))
        db.commit()
        return order.id, ptp.id
    finally:
        db.close()


def _bung_one(client, h) -> tuple[int, int]:
    order_id, _ = _seed_don_ptp()
    r = client.post("/api/lenh-sx/lenh/bung", json={"order_id": order_id}, headers=h)
    assert r.status_code == 201, r.text
    lenhs = r.json()
    assert len(lenhs) == 1
    return order_id, lenhs[0]["id"]


def _ghep(client, h, lenh_id: int, *, so_con: int = 2) -> int:
    r = client.post("/api/lenh-sx/forms/ghep", json={
        "giay_label": "Couche 150", "kho_in_dai": 650, "kho_in_rong": 490, "so_mau": 4,
        "so_to_chay": 1000, "so_kem": 4,
        "placements": [{"lenh_sx_id": lenh_id, "so_con": so_con}],
    }, headers=h)
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _drive_to_dang_chay(client, h) -> tuple[int, int, int]:
    """bung → ghép → gán máy → duyệt mẫu → phát. Trả (order_id, lenh_id, form_id)."""
    order_id, lenh_id = _bung_one(client, h)
    form_id = _ghep(client, h, lenh_id)
    assert client.post(f"/api/lenh-sx/forms/{form_id}/gan-may", json={"may_id": 7}, headers=h).status_code == 200
    assert client.post(f"/api/lenh-sx/lenh/{lenh_id}/duyet-mau", headers=h).status_code == 200
    assert client.post(f"/api/lenh-sx/forms/{form_id}/phat", headers=h).status_code == 200
    return order_id, lenh_id, form_id


# ============================================================ Luồng đầy-đủ (happy path)
def test_full_flow_bung_to_xong(client):
    h = _headers(client)
    order_id, ptp_id = _seed_don_ptp(qty=1000, so_luong=1000)

    # 1) bung → 1 lệnh nháp
    r = client.post("/api/lenh-sx/lenh/bung", json={"order_id": order_id}, headers=h)
    assert r.status_code == 201, r.text
    lenhs = r.json()
    assert len(lenhs) == 1
    lenh_id = lenhs[0]["id"]
    assert lenhs[0]["trang_thai"] == "nhap"
    assert lenhs[0]["phieu_thanh_phan_id"] == ptp_id

    # 2) ghép → tờ in + xếp bài; chưa máy + chưa duyệt ⇒ cho_ghep
    form_id = _ghep(client, h, lenh_id, so_con=2)
    rf = client.get(f"/api/lenh-sx/forms/{form_id}", headers=h)
    assert rf.status_code == 200
    assert rf.json()["trang_thai"] == "cho_ghep"
    assert len(rf.json()["placements"]) == 1

    # cổng: phát khi thiếu máy + chưa duyệt ⇒ 422
    assert client.post(f"/api/lenh-sx/forms/{form_id}/phat", headers=h).status_code == 422
    # cổng: ghi sản lượng trước khi phát ⇒ 409
    assert client.post(
        f"/api/lenh-sx/lenh/{lenh_id}/san-luong", json={"so_dat": 100, "so_hong": 0}, headers=h
    ).status_code == 409

    # 3) gán máy — nhưng chưa duyệt mẫu ⇒ phát vẫn 422
    assert client.post(f"/api/lenh-sx/forms/{form_id}/gan-may", json={"may_id": 7}, headers=h).status_code == 200
    assert client.post(f"/api/lenh-sx/forms/{form_id}/phat", headers=h).status_code == 422

    # 4) duyệt mẫu ⇒ con dấu đóng băng + tờ đủ điều kiện
    rd = client.post(f"/api/lenh-sx/lenh/{lenh_id}/duyet-mau", headers=h)
    assert rd.status_code == 200, rd.text
    assert rd.json()["mau_approved_at"] is not None
    assert client.get(f"/api/lenh-sx/forms/{form_id}", headers=h).json()["trang_thai"] == "du_dieu_kien"

    # 5) phát ⇒ tờ da_phat, lệnh dang_chay
    rp = client.post(f"/api/lenh-sx/forms/{form_id}/phat", headers=h)
    assert rp.status_code == 200, rp.text
    assert rp.json()["trang_thai"] == "da_phat"
    assert client.get(f"/api/lenh-sx/lenh/{lenh_id}", headers=h).json()["trang_thai"] == "dang_chay"

    # 6) ghi sản lượng (giờ mới cho) + đọc lại theo lệnh
    rs = client.post(
        f"/api/lenh-sx/lenh/{lenh_id}/san-luong",
        json={"cong_doan_id": 3, "to_id": 5, "so_dat": 1000, "so_hong": 5}, headers=h,
    )
    assert rs.status_code == 201, rs.text
    assert len(client.get(f"/api/lenh-sx/lenh/{lenh_id}/san-luong", headers=h).json()) == 1

    # 7) nhập kho đủ SL ⇒ lệnh XONG + đơn xong sản xuất
    rn = client.post(f"/api/lenh-sx/lenh/{lenh_id}/nhap-kho", json={"so_luong_nhap": 1000}, headers=h)
    assert rn.status_code == 200, rn.text
    body = rn.json()
    assert body["muc_tieu_sl"] == 1000
    assert body["lenh_xong"] is True
    assert body["lenh"]["trang_thai"] == "xong"
    assert body["order_production_done"] is True

    # detail lệnh phản ánh log (nuôi tracking)
    detail = client.get(f"/api/lenh-sx/lenh/{lenh_id}", headers=h).json()
    assert detail["tong_dat"] == 1000
    assert len(detail["san_luong"]) == 1
    assert len(detail["forms"]) == 1


# ============================================================ Cổng
def test_bung_idempotent(client):
    h = _headers(client)
    order_id, _ = _seed_don_ptp()
    r1 = client.post("/api/lenh-sx/lenh/bung", json={"order_id": order_id}, headers=h)
    assert r1.status_code == 201
    assert len(r1.json()) == 1
    r2 = client.post("/api/lenh-sx/lenh/bung", json={"order_id": order_id}, headers=h)
    assert r2.status_code == 201
    assert r2.json() == []          # gọi lại KHÔNG nhân đôi
    total = client.get("/api/lenh-sx/lenh", params={"order_id": order_id}, headers=h).json()["total"]
    assert total == 1


def test_phat_blocked_without_may_or_duyet(client):
    h = _headers(client)
    _, lenh_id = _bung_one(client, h)
    form_id = _ghep(client, h, lenh_id)
    # thiếu cả máy lẫn duyệt mẫu
    assert client.post(f"/api/lenh-sx/forms/{form_id}/phat", headers=h).status_code == 422
    # gán máy nhưng CHƯA duyệt mẫu ⇒ vẫn chặn (cổng AND)
    client.post(f"/api/lenh-sx/forms/{form_id}/gan-may", json={"may_id": 7}, headers=h)
    assert client.post(f"/api/lenh-sx/forms/{form_id}/phat", headers=h).status_code == 422


def test_san_luong_blocked_before_phat(client):
    h = _headers(client)
    _, lenh_id = _bung_one(client, h)
    r = client.post(f"/api/lenh-sx/lenh/{lenh_id}/san-luong", json={"so_dat": 10, "so_hong": 0}, headers=h)
    assert r.status_code == 409


def test_nhap_kho_thieu_chua_xong(client):
    h = _headers(client)
    _, lenh_id, _ = _drive_to_dang_chay(client, h)
    r = client.post(f"/api/lenh-sx/lenh/{lenh_id}/nhap-kho", json={"so_luong_nhap": 500}, headers=h)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["lenh_xong"] is False
    assert body["order_production_done"] is False
    assert client.get(f"/api/lenh-sx/lenh/{lenh_id}", headers=h).json()["trang_thai"] == "dang_chay"


def test_huy_lenh(client):
    h = _headers(client)
    _, lenh_id = _bung_one(client, h)
    r = client.post(f"/api/lenh-sx/lenh/{lenh_id}/huy", headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["trang_thai"] == "huy"


def test_bung_order_da_huy_conflict(client):
    h = _headers(client)
    order_id, _ = _seed_don_ptp()
    # đổi đơn sang cancelled rồi bung ⇒ 409
    db = SessionLocal()
    try:
        o = db.get(Order, order_id)
        o.status = "cancelled"
        db.commit()
    finally:
        db.close()
    r = client.post("/api/lenh-sx/lenh/bung", json={"order_id": order_id}, headers=h)
    assert r.status_code == 409, r.text
