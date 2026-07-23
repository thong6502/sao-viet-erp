"""Đơn giá khoán (module `luong` nhịp 2): CRUD bảng giá tra khi ghi Phiếu sản lượng.

Tiền khoán vào bảng lương = Phiếu sản lượng theo người (xem test_san_luong_api). Không còn "sổ khoán".
"""
from __future__ import annotations

ADMIN = {"username": "admin", "password": "admin123"}


def _admin_token(client) -> str:
    return client.post("/api/auth/login", json=ADMIN).json()["access_token"]


def _h(t: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {t}"}


def test_rate_crud(client):
    token = _admin_token(client)
    r = client.post("/api/luong/khoan/rates", json={
        "group_name": "to_boi", "name": "Bồi 3 lớp", "unit": "m2", "unit_price": 170,
    }, headers=_h(token))
    assert r.status_code == 201
    rid = r.json()["id"]
    assert any(x["id"] == rid for x in client.get("/api/luong/khoan/rates", headers=_h(token)).json()["items"])
    upd = client.put(f"/api/luong/khoan/rates/{rid}", json={
        "group_name": "to_boi", "name": "Bồi 3 lớp", "unit": "m2", "unit_price": 180,
    }, headers=_h(token))
    assert upd.json()["unit_price"] == 180
    assert client.delete(f"/api/luong/khoan/rates/{rid}", headers=_h(token)).status_code == 204


def test_rate_scoped_by_department(client):
    """Đơn giá gắn `department_id` (khai trong Cấu hình lương của tổ) → GET lọc đúng theo tổ."""
    token = _admin_token(client)
    a = client.post("/api/luong/khoan/rates", json={
        "group_name": "Tổ Bế", "department_id": 101, "name": "Dán bìa các tông",
        "unit": "to", "unit_price": 170,
    }, headers=_h(token)).json()
    b = client.post("/api/luong/khoan/rates", json={
        "group_name": "Tổ Bồi", "department_id": 202, "name": "Bồi carton 3 lớp",
        "unit": "m2", "unit_price": 200,
    }, headers=_h(token)).json()
    assert a["department_id"] == 101 and b["department_id"] == 202
    # Lọc theo tổ 101 → chỉ đơn giá của tổ đó.
    only = client.get("/api/luong/khoan/rates?department_id=101", headers=_h(token)).json()["items"]
    ids = {x["id"] for x in only}
    assert a["id"] in ids and b["id"] not in ids
    assert all(x["department_id"] == 101 for x in only)
    # Không lọc → thấy cả hai.
    all_ids = {x["id"] for x in client.get("/api/luong/khoan/rates", headers=_h(token)).json()["items"]}
    assert a["id"] in all_ids and b["id"] in all_ids
