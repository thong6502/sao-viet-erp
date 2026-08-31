"""Bàn Thực hiện sản xuất — API `/api/san-xuat/*` (gác quyền + hình dạng ra).

Soi tầng router + schema + `require_permission`: chưa đăng nhập → 401; admin → 200 và tổ vừa
tạo hiện trong danh sách (badge 0 khi chưa phát hành); timeline tổ hợp lệ → 200 rỗng; tổ ngoài
tập node-lá Khối SX → 403. Không dựng cả luồng phát hành ở đây (đã có ở test service backbone) —
chỉ cần một tổ-lá để chứng minh đường dây HTTP.
"""
from __future__ import annotations

from app.db import SessionLocal
from app.models.department import Department

ADMIN = {"username": "admin", "password": "admin123"}


def _admin_h(client) -> dict[str, str]:
    tok = client.post("/api/auth/login", json=ADMIN).json()["access_token"]
    return {"Authorization": f"Bearer {tok}"}


def _to_la_sx(ten="Tổ In API", ma="TO-API") -> int:
    db = SessionLocal()
    try:
        d = Department(name=ten, code=ma, la_san_xuat=True)
        db.add(d)
        db.commit()
        return d.id
    finally:
        db.close()


def test_teams_can_dang_nhap(client):
    assert client.get("/api/san-xuat/teams").status_code == 401


def test_teams_admin_thay_to_moi(client):
    to_id = _to_la_sx()
    resp = client.get("/api/san-xuat/teams", headers=_admin_h(client))
    assert resp.status_code == 200
    teams = resp.json()["teams"]
    row = next((t for t in teams if t["id"] == to_id), None)
    assert row is not None
    assert set(row) == {
        "id", "ten", "ma", "la_kcs", "so_viec_cho", "so_viec_kcs_cho", "co_viec_kcs",
    }
    assert row["ten"] == "Tổ In API" and row["so_viec_cho"] == 0
    assert row["so_viec_kcs_cho"] == 0 and row["co_viec_kcs"] is False


def test_work_items_to_hop_le_rong(client):
    to_id = _to_la_sx()
    resp = client.get(
        "/api/san-xuat/work-items", params={"team_id": to_id}, headers=_admin_h(client)
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["team_id"] == to_id and body["cong_viec"] == []


def test_work_items_ngoai_pham_vi_403(client):
    resp = client.get(
        "/api/san-xuat/work-items", params={"team_id": 999_999}, headers=_admin_h(client)
    )
    assert resp.status_code == 403


def test_work_items_mode_query_param(client):
    """Task 4: `mode` là query param FastAPI `Literal["production", "kcs"]` — hợp lệ thì 200 (đúng
    hình dạng ra, kể cả tổ trống), giá trị lạ thì 422 (Pydantic tự validate, không cần code tay)."""
    to_id = _to_la_sx()
    resp = client.get(
        "/api/san-xuat/work-items",
        params={"team_id": to_id, "mode": "kcs"},
        headers=_admin_h(client),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["team_id"] == to_id and body["cong_viec"] == []

    resp_bad = client.get(
        "/api/san-xuat/work-items",
        params={"team_id": to_id, "mode": "abc"},
        headers=_admin_h(client),
    )
    assert resp_bad.status_code == 422
