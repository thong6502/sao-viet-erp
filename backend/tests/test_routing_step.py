"""Routing riêng mỗi lệnh (§13.2) — copy từ job spec + kế hoạch sửa (khóa bước đã chạy).

Verify THẬT qua HTTP: bung COPY routing (theo `thu_tu`, tổ từ `cong_doan.department_id`) · thêm /
sửa / xóa bước (chỉ khi còn `cho`) · đổi thứ tự (chỉ khi nháp, chặn sau phát) · khóa bước đã/đang chạy.
Dùng fixture `client` (conftest) + SessionLocal để dựng job spec (PTG) nền.
"""
from __future__ import annotations

from app.db import SessionLocal
from app.models.department import Department
from app.models.lenh_san_xuat import LENH_DANG_CHAY, RS_DANG, LenhSanXuat, RoutingStep
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
    assert all(s["trang_thai"] == "cho" for s in routing)
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


def test_edit_blocked_when_step_running(client):
    """Bước đã/đang chạy (trạng thái ≠ 'cho') → sửa/xóa bị khóa 409."""
    h = _headers(client)
    lenh_id = _bung(client, h, _seed_don_2steps())
    step_id = client.get(f"/api/lenh-sx/lenh/{lenh_id}/routing", headers=h).json()[0]["id"]
    db = SessionLocal()
    try:
        db.get(RoutingStep, step_id).trang_thai = RS_DANG
        db.commit()
    finally:
        db.close()
    assert client.put(f"/api/lenh-sx/routing/{step_id}", json={"cong_doan_id": 2, "to_id": 1}, headers=h).status_code == 409
    assert client.delete(f"/api/lenh-sx/routing/{step_id}", headers=h).status_code == 409


# ============================================================ TỔ VIEW (§13.3–13.4)
def _two_dept_ids() -> tuple[int, int]:
    """2 phòng ban khác nhau trong seed (base seed có ≥7) để gán làm tổ cho 2 bước."""
    db = SessionLocal()
    try:
        ds = db.query(Department).order_by(Department.id).limit(2).all()
        assert len(ds) >= 2
        return ds[0].id, ds[1].id
    finally:
        db.close()


def _phat_with_tos(lenh_id: int, to0: int, to1: int) -> list[int]:
    """Mô phỏng đã phát (lệnh dang_chay) + gán tổ 2 bước. Trả step_ids theo thứ tự routing."""
    db = SessionLocal()
    try:
        db.get(LenhSanXuat, lenh_id).trang_thai = LENH_DANG_CHAY
        steps = (
            db.query(RoutingStep)
            .filter(RoutingStep.lenh_sx_id == lenh_id)
            .order_by(RoutingStep.thu_tu)
            .all()
        )
        steps[0].to_id, steps[1].to_id = to0, to1
        db.commit()
        return [s.id for s in steps]
    finally:
        db.close()


def test_bat_dau_hoan_thanh_theo_thu_tu(client):
    """Đến lượt tuyến tính: bắt đầu/hoàn thành THEO THỨ TỰ; bước sau khóa tới khi bước trước xong."""
    h = _headers(client)
    lenh_id = _bung(client, h, _seed_don_2steps())
    to0, to1 = _two_dept_ids()
    s0, s1 = _phat_with_tos(lenh_id, to0, to1)
    # chưa tới lượt → bắt đầu bước 2 bị chặn; hoàn thành bước 1 khi chưa bắt đầu cũng chặn
    assert client.post(f"/api/lenh-sx/routing/{s1}/bat-dau", headers=h).status_code == 409
    assert client.post(f"/api/lenh-sx/routing/{s0}/hoan-thanh", headers=h).status_code == 409
    # bắt đầu bước 1 → dang
    r = client.post(f"/api/lenh-sx/routing/{s0}/bat-dau", headers=h)
    assert r.status_code == 200, r.text
    assert next(s for s in r.json() if s["id"] == s0)["trang_thai"] == "dang"
    # bước 2 vẫn chưa tới lượt
    assert client.post(f"/api/lenh-sx/routing/{s1}/bat-dau", headers=h).status_code == 409
    # hoàn thành bước 1 → xong → bước 2 đến lượt
    r2 = client.post(f"/api/lenh-sx/routing/{s0}/hoan-thanh", headers=h)
    assert r2.status_code == 200, r2.text
    assert next(s for s in r2.json() if s["id"] == s0)["trang_thai"] == "xong"
    assert client.post(f"/api/lenh-sx/routing/{s1}/bat-dau", headers=h).status_code == 200


def test_bat_dau_chan_khi_chua_phat(client):
    """Lệnh còn nháp (chưa phát) → bắt đầu bước bị chặn 409 (cổng cứng)."""
    h = _headers(client)
    lenh_id = _bung(client, h, _seed_don_2steps())
    s0 = client.get(f"/api/lenh-sx/lenh/{lenh_id}/routing", headers=h).json()[0]["id"]
    assert client.post(f"/api/lenh-sx/routing/{s0}/bat-dau", headers=h).status_code == 409


def test_to_board_va_lenh_cua_to(client):
    """Bảng tổ đếm đúng đến-lượt/việc; lệnh-của-tổ trả cờ `den_luot` theo bước hiện hành."""
    h = _headers(client)
    lenh_id = _bung(client, h, _seed_don_2steps())
    to0, to1 = _two_dept_ids()
    _phat_with_tos(lenh_id, to0, to1)  # bước 1 @to0 (đến lượt), bước 2 @to1
    board = {n["id"]: n for n in client.get("/api/lenh-sx/to-board", headers=h).json()}
    assert board[to0]["so_den_luot"] >= 1              # bước hiện hành thuộc to0
    assert board[to1]["so_den_luot"] == 0              # to1 chưa tới lượt
    assert board[to0]["so_lenh"] >= 1 and board[to1]["so_lenh"] >= 1  # cả 2 tổ có việc trên lệnh
    # lệnh của tổ: to0 thấy den_luot=True; to1 thấy den_luot=False
    l0 = [r for r in client.get(f"/api/lenh-sx/to/{to0}/lenh", headers=h).json() if r["id"] == lenh_id]
    assert l0 and l0[0]["den_luot"] is True and l0[0]["so_buoc"] == 2
    l1 = [r for r in client.get(f"/api/lenh-sx/to/{to1}/lenh", headers=h).json() if r["id"] == lenh_id]
    assert l1 and l1[0]["den_luot"] is False
