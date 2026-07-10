"""Tests — Đợt kiểm kê & điều chỉnh tồn (spec-13 C)."""
from __future__ import annotations

import pytest

from app.db import SessionLocal
from app.models.material import Material


@pytest.fixture
def token(client, seed_credentials) -> str:
    return client.post("/api/auth/login", json=seed_credentials).json()["access_token"]


@pytest.fixture
def h(token) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def env(client, h) -> dict:
    db = SessionLocal()
    try:
        m = Material(code="GY_KK", name="Giấy kiểm kê", material_type="paper", unit="to", is_active=True)
        db.add(m); db.commit(); db.refresh(m)
        mid = m.id
    finally:
        db.close()
    wh = client.post("/api/warehouses", json={"name": "Kho KK"}, headers=h).json()["id"]
    return {"mat": mid, "wh": wh}


def _nhap(client, h, mat, wh, qty):
    return client.post("/api/kho/moves", json={
        "material_id": mat, "warehouse_id": wh, "quantity": qty, "move_type": "ton_dau_ky",
    }, headers=h)


def _stock(client, h, mat, wh):
    bal = client.get(f"/api/kho/stock?material_id={mat}&warehouse_id={wh}", headers=h).json()["items"]
    return sum(b["on_hand"] for b in bal)


def test_kiem_ke_shortage(client, h, env):
    _nhap(client, h, env["mat"], env["wh"], 100)  # tồn hệ thống 100
    c = client.post("/api/kho/counts", json={"warehouse_id": env["wh"]}, headers=h)
    assert c.status_code == 201, c.text
    count = c.json()
    line = next(l for l in count["lines"] if l["material_id"] == env["mat"])
    assert line["system_qty"] == 100
    # Đếm thực 90 (thiếu 10)
    upd = client.put(f"/api/kho/counts/{count['id']}/lines",
                     json={"lines": [{"line_id": line["id"], "counted_qty": 90}]}, headers=h)
    assert upd.status_code == 200
    ul = next(l for l in upd.json()["lines"] if l["id"] == line["id"])
    assert ul["diff"] == -10
    # Duyệt → điều chỉnh −10 → tồn 90
    posted = client.post(f"/api/kho/counts/{count['id']}/post", headers=h)
    assert posted.status_code == 200 and posted.json()["status"] == "posted"
    assert _stock(client, h, env["mat"], env["wh"]) == 90


def test_kiem_ke_surplus(client, h, env):
    _nhap(client, h, env["mat"], env["wh"], 50)
    count = client.post("/api/kho/counts", json={"warehouse_id": env["wh"]}, headers=h).json()
    line = next(l for l in count["lines"] if l["material_id"] == env["mat"])
    client.put(f"/api/kho/counts/{count['id']}/lines",
               json={"lines": [{"line_id": line["id"], "counted_qty": 55}]}, headers=h)  # thừa 5
    client.post(f"/api/kho/counts/{count['id']}/post", headers=h)
    assert _stock(client, h, env["mat"], env["wh"]) == 55


def test_kiem_ke_no_change_no_move(client, h, env):
    _nhap(client, h, env["mat"], env["wh"], 30)
    count = client.post("/api/kho/counts", json={"warehouse_id": env["wh"]}, headers=h).json()
    line = next(l for l in count["lines"] if l["material_id"] == env["mat"])
    client.put(f"/api/kho/counts/{count['id']}/lines",
               json={"lines": [{"line_id": line["id"], "counted_qty": 30}]}, headers=h)  # khớp
    client.post(f"/api/kho/counts/{count['id']}/post", headers=h)
    assert _stock(client, h, env["mat"], env["wh"]) == 30  # không đổi


def test_cannot_post_twice(client, h, env):
    _nhap(client, h, env["mat"], env["wh"], 10)
    count = client.post("/api/kho/counts", json={"warehouse_id": env["wh"]}, headers=h).json()
    client.post(f"/api/kho/counts/{count['id']}/post", headers=h)
    r = client.post(f"/api/kho/counts/{count['id']}/post", headers=h)
    assert r.status_code == 409
