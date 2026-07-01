"""spec-06 / PBI-4007 — org tree: re-parent, cycle guard, and level ordering.

A unit can be re-parented; the parent may not be the unit itself or a descendant (cycle),
and a child unit's level must rank strictly below its parent's (Khối > Phòng > Tổ). A plain
rename (no parent_id sent) keeps the current parent.
"""
from __future__ import annotations

ADMIN = {"username": "admin", "password": "admin123"}


def _token(client) -> str:
    return client.post("/api/auth/login", json=ADMIN).json()["access_token"]


def _h(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _levels(client, token) -> dict[str, dict]:
    """Seeded levels keyed by name (Khối rank1, Phòng rank2, Tổ rank3)."""
    rows = client.get("/api/unit-levels", headers=_h(token)).json()
    return {r["name"]: r for r in rows}


def _dept(client, token, name, **body):
    return client.post(
        "/api/departments", json={"name": name, **body}, headers=_h(token)
    ).json()


def test_reparent_moves_unit(client):
    token = _token(client)
    a = _dept(client, token, "Đơn vị A")
    b = _dept(client, token, "Đơn vị B")  # a root

    moved = client.put(
        f"/api/departments/{b['id']}",
        json={"name": b["name"], "parent_id": a["id"]},
        headers=_h(token),
    )
    assert moved.status_code == 200
    listing = client.get("/api/departments", headers=_h(token)).json()
    assert next(d for d in listing if d["id"] == b["id"])["parent_id"] == a["id"]


def test_rename_without_parent_id_keeps_parent(client):
    token = _token(client)
    parent = _dept(client, token, "Cha giữ")
    child = _dept(client, token, "Con giữ", parent_id=parent["id"])

    # Plain rename — no parent_id in the payload — must NOT orphan the child.
    client.put(
        f"/api/departments/{child['id']}",
        json={"name": "Con đổi tên"},
        headers=_h(token),
    )
    listing = client.get("/api/departments", headers=_h(token)).json()
    assert next(d for d in listing if d["id"] == child["id"])["parent_id"] == parent["id"]


def test_cycle_is_blocked(client):
    token = _token(client)
    parent = _dept(client, token, "P gốc")
    child = _dept(client, token, "C con", parent_id=parent["id"])

    # Making the parent a child of its own descendant → 400.
    resp = client.put(
        f"/api/departments/{parent['id']}",
        json={"name": parent["name"], "parent_id": child["id"]},
        headers=_h(token),
    )
    assert resp.status_code == 400

    # A unit cannot be its own parent → 400.
    self_ref = client.put(
        f"/api/departments/{parent['id']}",
        json={"name": parent["name"], "parent_id": parent["id"]},
        headers=_h(token),
    )
    assert self_ref.status_code == 400


def test_child_level_must_rank_below_parent(client):
    token = _token(client)
    lv = _levels(client, token)
    khoi, phong, to = lv["Khối"], lv["Phòng"], lv["Tổ"]

    parent = _dept(client, token, "Khối KD", level_id=phong["id"])  # rank 2

    # Child at a LOWER tier (Tổ, rank 3) under a rank-2 parent → ok.
    ok = client.post(
        "/api/departments",
        json={"name": "Tổ 1", "parent_id": parent["id"], "level_id": to["id"]},
        headers=_h(token),
    )
    assert ok.status_code == 201

    # Child at a HIGHER tier (Khối, rank 1) under a rank-2 parent → 400.
    bad = client.post(
        "/api/departments",
        json={"name": "Khối con", "parent_id": parent["id"], "level_id": khoi["id"]},
        headers=_h(token),
    )
    assert bad.status_code == 400

    # Same rule on update: move the ok child's level up to Khối → 400.
    child_id = ok.json()["id"]
    bump = client.put(
        f"/api/departments/{child_id}",
        json={"name": "Tổ 1", "level_id": khoi["id"]},
        headers=_h(token),
    )
    assert bump.status_code == 400
