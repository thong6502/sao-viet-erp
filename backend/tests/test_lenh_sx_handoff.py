"""Handoff Đơn → bàn Kế hoạch SX — VERIFY THẬT (spec §5.1).

Kiểm cầu nối đơn-chốt → hàng chờ kế hoạch → bấm 'Lên kế hoạch' (bung) + đường sửa hint SX post-chốt:
  - `GET /api/lenh-sx/hang-cho` chỉ liệt kê đơn ĐÃ CHỐT có ≥1 ấn phẩm (ptp) mà CHƯA có lệnh;
    kèm ngữ cảnh (gấp/lưu ý/ấn phẩm+SL). Bung xong → rời hàng chờ.
  - Cổng: bung CHẶN khi đơn chưa chốt (409).
  - `POST /api/orders/{id}/production-hint` sửa gấp/lưu ý CHỈ khi đã chốt (nháp → 409).
"""
from __future__ import annotations

from datetime import datetime, timezone

from app.db import SessionLocal
from app.models.order import Order, OrderLine
from app.models.phieu_tinh_gia import PhieuThanhPhan, PhieuTinhGia


def _headers(client) -> dict[str, str]:
    login = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
    assert login.status_code == 200, login.text
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


def _seed_order(
    *, status: str = "ordered", with_ptp: bool = True, order_no: str,
    is_rush: bool = True, production_note: str | None = "In thử màu trước",
    released: bool = True,
) -> tuple[int, int | None]:
    """1 Đơn + (tùy chọn) 1 ấn phẩm PTP + 1 dòng đơn. Trả (order_id, ptp_id|None).

    `released=True` = Sale đã "Chuyển xuống SX" (san_xuat_released_at set) → đủ điều kiện vào hàng chờ.
    """
    db = SessionLocal()
    try:
        ptp_id = None
        if with_ptp:
            ptg = PhieuTinhGia(ma=f"PTG-{order_no}", ten_san_pham="Catalogue", so_luong=500)
            db.add(ptg)
            db.flush()
            ptp = PhieuThanhPhan(phieu_id=ptg.id, thu_tu=1, ten="Ruột", so_luong=500)
            db.add(ptp)
            db.flush()
            ptp_id = ptp.id
        order = Order(
            order_no=order_no, status=status, is_rush=is_rush, production_note=production_note,
            san_xuat_released_at=(datetime.now(timezone.utc) if released and status == "ordered" else None),
        )
        db.add(order)
        db.flush()
        db.add(OrderLine(
            order_id=order.id, description="Catalogue A5", qty=500,
            don_vi_tinh="cuốn", phieu_thanh_phan_id=ptp_id,
        ))
        db.commit()
        return order.id, ptp_id
    finally:
        db.close()


def test_hang_cho_lists_ordered_with_ptp_then_leaves_after_bung(client):
    h = _headers(client)
    oid, ptp = _seed_order(order_no="DH-HC-1")

    r = client.get("/api/lenh-sx/hang-cho", headers=h)
    assert r.status_code == 200, r.text
    rows = [x for x in r.json() if x["order_id"] == oid]
    assert len(rows) == 1
    row = rows[0]
    assert row["order_no"] == "DH-HC-1"
    assert row["is_rush"] is True
    assert row["production_note"] == "In thử màu trước"
    assert len(row["an_pham"]) == 1
    assert row["an_pham"][0]["phieu_thanh_phan_id"] == ptp
    assert row["an_pham"][0]["qty"] == 500
    assert row["an_pham"][0]["don_vi_tinh"] == "cuốn"

    # kế hoạch bấm 'Lên kế hoạch' (bung) → rời hàng chờ (đã có lệnh)
    assert client.post("/api/lenh-sx/lenh/bung", json={"order_id": oid}, headers=h).status_code == 201
    r2 = client.get("/api/lenh-sx/hang-cho", headers=h)
    assert all(x["order_id"] != oid for x in r2.json())


def test_hang_cho_excludes_draft_and_manual_only(client):
    h = _headers(client)
    _seed_order(status="draft", order_no="DH-HC-DRAFT")            # chưa chốt
    _seed_order(status="ordered", with_ptp=False, order_no="DH-HC-MANUAL")  # chốt nhưng dòng nhập tay

    nos = [x["order_no"] for x in client.get("/api/lenh-sx/hang-cho", headers=h).json()]
    assert "DH-HC-DRAFT" not in nos
    assert "DH-HC-MANUAL" not in nos


def test_bung_blocked_when_not_ordered(client):
    h = _headers(client)
    oid, _ = _seed_order(status="draft", order_no="DH-BUNG-DRAFT")
    r = client.post("/api/lenh-sx/lenh/bung", json={"order_id": oid}, headers=h)
    assert r.status_code == 409, r.text


def test_hang_cho_excludes_not_released(client):
    h = _headers(client)
    # đơn đã chốt nhưng Sale CHƯA "Chuyển xuống SX" → không vào hàng chờ
    _seed_order(order_no="DH-HC-NOTREL", released=False)
    nos = [x["order_no"] for x in client.get("/api/lenh-sx/hang-cho", headers=h).json()]
    assert "DH-HC-NOTREL" not in nos


def test_release_production_then_appears_in_hang_cho(client):
    h = _headers(client)
    oid, _ = _seed_order(order_no="DH-REL-1", released=False)
    # chưa release → chưa có trong hàng chờ
    assert all(x["order_id"] != oid for x in client.get("/api/lenh-sx/hang-cho", headers=h).json())
    # Sale bấm "Chuyển xuống SX"
    r = client.post(f"/api/orders/{oid}/release-production", headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["san_xuat_released_at"] is not None
    # giờ mới vào hàng chờ
    assert any(x["order_id"] == oid for x in client.get("/api/lenh-sx/hang-cho", headers=h).json())


def test_release_production_blocked_when_draft(client):
    h = _headers(client)
    oid, _ = _seed_order(status="draft", order_no="DH-REL-DRAFT")
    r = client.post(f"/api/orders/{oid}/release-production", headers=h)
    assert r.status_code == 409, r.text


def test_production_hint_editable_only_after_ordered(client):
    h = _headers(client)
    oid, _ = _seed_order(order_no="DH-HINT-1")

    # đã chốt → sửa gấp/lưu ý OK
    r = client.post(
        f"/api/orders/{oid}/production-hint",
        json={"is_rush": False, "production_note": "Giao trước 5h chiều"}, headers=h,
    )
    assert r.status_code == 200, r.text
    assert r.json()["is_rush"] is False
    assert r.json()["production_note"] == "Giao trước 5h chiều"

    # đơn nháp → chặn 409 (không nới cổng update() nháp)
    did, _ = _seed_order(status="draft", order_no="DH-HINT-DRAFT")
    r2 = client.post(f"/api/orders/{did}/production-hint", json={"is_rush": True}, headers=h)
    assert r2.status_code == 409, r2.text
