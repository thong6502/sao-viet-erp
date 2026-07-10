"""Tests — Kho Document Engine (spec-13): phiếu nhập/xuất/điều chuyển + tồn khả dụng."""
from __future__ import annotations

import pytest

from app.db import SessionLocal
from app.models.material import Material


@pytest.fixture
def token(client, seed_credentials) -> str:
    resp = client.post("/api/auth/login", json=seed_credentials)
    assert resp.status_code == 200
    return resp.json()["access_token"]


@pytest.fixture
def h(token) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def env(client, h) -> dict:
    db = SessionLocal()
    try:
        m = Material(code="GY_ENG150", name="Couche 150 eng", material_type="paper",
                     unit="to", gsm=150, width_cm=65.0, height_cm=86.0, is_active=True)
        db.add(m); db.commit(); db.refresh(m)
        mid = m.id
    finally:
        db.close()
    wh_a = client.post("/api/warehouses", json={"name": "Kho A eng"}, headers=h).json()["id"]
    wh_b = client.post("/api/warehouses", json={"name": "Kho B eng"}, headers=h).json()["id"]
    vtypes = {v["code"]: v["id"] for v in client.get("/api/kho/voucher-types", headers=h).json()["items"]}
    statuses = {s["code"]: s["id"] for s in client.get("/api/kho/item-statuses", headers=h).json()["items"]}
    return {"mat": mid, "wh_a": wh_a, "wh_b": wh_b, "vt": vtypes, "st": statuses}


def _stock(client, h, mat, wh):
    bal = client.get(f"/api/kho/stock?material_id={mat}&warehouse_id={wh}", headers=h).json()["items"]
    on = sum(b["on_hand"] for b in bal)
    av = sum(b["available"] for b in bal)
    return on, av


def _voucher(client, h, vt_id, lines, src=None, dst=None):
    body = {"voucher_type_id": vt_id, "lines": lines}
    if src:
        body["src_warehouse_id"] = src
    if dst:
        body["dst_warehouse_id"] = dst
    return client.post("/api/kho/vouchers", json=body, headers=h)


def _voucher_full(client, h, vt_id, lines, src=None, dst=None, partner_kind=None, partner_ref=None):
    body = {"voucher_type_id": vt_id, "lines": lines}
    if src:
        body["src_warehouse_id"] = src
    if dst:
        body["dst_warehouse_id"] = dst
    if partner_kind:
        body["partner_kind"] = partner_kind
    if partner_ref:
        body["partner_ref"] = partner_ref
    return client.post("/api/kho/vouchers", json=body, headers=h)


def _post(client, h, vid):
    """Nộp phiếu; loại phiếu seed đều require_approval → duyệt luôn (admin có kho:approve).
    Trả response cuối (submit nếu chặn ngay, hoặc approve)."""
    r = client.post(f"/api/kho/vouchers/{vid}/submit", headers=h)
    if r.status_code == 200 and r.json().get("status") == "pending":
        r = client.post(f"/api/kho/vouchers/{vid}/approve", headers=h)
    return r


def test_submit_goes_pending_then_approve_posts(client, h, env):
    # require_approval=True: Nộp → Chờ duyệt; Duyệt → Đã ghi sổ.
    v = _voucher(client, h, env["vt"]["NK-NVL"], [{"material_id": env["mat"], "quantity": 10}], dst=env["wh_a"])
    vid = v.json()["id"]
    sub = client.post(f"/api/kho/vouchers/{vid}/submit", headers=h)
    assert sub.status_code == 200 and sub.json()["status"] == "pending"
    # chưa duyệt → tồn CHƯA đổi
    assert _stock(client, h, env["mat"], env["wh_a"])[0] == 0
    appr = client.post(f"/api/kho/vouchers/{vid}/approve", headers=h)
    assert appr.status_code == 200 and appr.json()["status"] == "posted"
    assert _stock(client, h, env["mat"], env["wh_a"])[0] == 10


def test_receipt_with_conversion(client, h, env):
    # NK-NVL (tang, cần kho đích). Nhập 2 ream → 1000 tờ ở kho A.
    v = _voucher(client, h, env["vt"]["NK-NVL"],
                 [{"material_id": env["mat"], "quantity": 2, "uom": "ream"}], dst=env["wh_a"])
    assert v.status_code == 201, v.text
    vid = v.json()["id"]
    posted = _post(client, h, vid)
    assert posted.status_code == 200 and posted.json()["status"] == "posted"
    on, av = _stock(client, h, env["mat"], env["wh_a"])
    assert on == 1000 and av == 1000


def test_receipt_missing_dst_blocked(client, h, env):
    v = _voucher(client, h, env["vt"]["NK-NVL"], [{"material_id": env["mat"], "quantity": 1}])
    vid = v.json()["id"]
    assert _post(client, h, vid).status_code == 422  # thiếu kho đích → chặn khi ghi sổ


def test_issue_and_guard(client, h, env):
    # nạp 1000 tờ
    v = _voucher(client, h, env["vt"]["NK-NVL"], [{"material_id": env["mat"], "quantity": 1000}], dst=env["wh_a"])
    _post(client, h, v.json()["id"])
    # xuất 300 (XK-SX, giam, cần kho nguồn)
    out = _voucher(client, h, env["vt"]["XK-SX"], [{"material_id": env["mat"], "quantity": 300}], src=env["wh_a"])
    assert _post(client, h, out.json()["id"]).status_code == 200
    on, _ = _stock(client, h, env["mat"], env["wh_a"])
    assert on == 700
    # xuất 5000 quá tồn → 422
    over = _voucher(client, h, env["vt"]["XK-SX"], [{"material_id": env["mat"], "quantity": 5000}], src=env["wh_a"])
    assert _post(client, h, over.json()["id"]).status_code == 422


def test_transfer(client, h, env):
    v = _voucher(client, h, env["vt"]["NK-NVL"], [{"material_id": env["mat"], "quantity": 500}], dst=env["wh_a"])
    _post(client, h, v.json()["id"])
    mv = _voucher(client, h, env["vt"]["DC-KHO"], [{"material_id": env["mat"], "quantity": 100}],
                  src=env["wh_a"], dst=env["wh_b"])
    assert _post(client, h, mv.json()["id"]).status_code == 200
    assert _stock(client, h, env["mat"], env["wh_a"])[0] == 400
    assert _stock(client, h, env["mat"], env["wh_b"])[0] == 100


def test_available_vs_on_hand_by_status(client, h, env):
    # nhập 700 Khả dụng + 200 Chờ KCS
    v1 = _voucher(client, h, env["vt"]["NK-NVL"],
                  [{"material_id": env["mat"], "quantity": 700, "status_id": env["st"]["AVAILABLE"]}], dst=env["wh_a"])
    _post(client, h, v1.json()["id"])
    v2 = _voucher(client, h, env["vt"]["NK-NVL"],
                  [{"material_id": env["mat"], "quantity": 200, "status_id": env["st"]["QC_WAIT"]}], dst=env["wh_a"])
    _post(client, h, v2.json()["id"])
    on, av = _stock(client, h, env["mat"], env["wh_a"])
    assert on == 900   # thực tế
    assert av == 700   # khả dụng (Chờ KCS không tính)


def test_cannot_edit_or_cancel_posted(client, h, env):
    v = _voucher(client, h, env["vt"]["NK-NVL"], [{"material_id": env["mat"], "quantity": 10}], dst=env["wh_a"])
    vid = v.json()["id"]
    _post(client, h, vid)
    upd = client.put(f"/api/kho/vouchers/{vid}", json={"voucher_type_id": env["vt"]["NK-NVL"], "lines": []}, headers=h)
    assert upd.status_code == 409
    assert client.post(f"/api/kho/vouchers/{vid}/cancel", headers=h).status_code == 409


def test_cost_value_receipt_and_issue(client, h, env):
    # Nhập 100 @ đơn giá 500 → giá trị tồn = 50.000.
    v = _voucher(client, h, env["vt"]["NK-NVL"],
                 [{"material_id": env["mat"], "quantity": 100, "unit_cost": 500}], dst=env["wh_a"])
    _post(client, h, v.json()["id"])
    bal = client.get(f"/api/kho/stock?material_id={env['mat']}&warehouse_id={env['wh_a']}", headers=h).json()["items"]
    b = next(x for x in bal if x["warehouse_id"] == env["wh_a"])
    assert b["on_hand"] == 100 and b["value"] == 100 * 500

    # Xuất 30 (không lô → bình quân 500) → tồn 70, giá trị 35.000.
    out = _voucher(client, h, env["vt"]["XK-SX"], [{"material_id": env["mat"], "quantity": 30}], src=env["wh_a"])
    _post(client, h, out.json()["id"])
    bal = client.get(f"/api/kho/stock?material_id={env['mat']}&warehouse_id={env['wh_a']}", headers=h).json()["items"]
    b = next(x for x in bal if x["warehouse_id"] == env["wh_a"])
    assert b["on_hand"] == 70 and b["value"] == 70 * 500


def test_voucher_records_creator_and_partner(client, h, env):
    # Phiếu nhập ghi "nhập từ ai" (partner_ref) + trả kèm tên người nhập.
    v = _voucher_full(client, h, env["vt"]["NK-NVL"],
                      [{"material_id": env["mat"], "quantity": 50}], dst=env["wh_a"],
                      partner_kind="ncc", partner_ref="Cty Giấy An Bình")
    assert v.status_code == 201, v.text
    body = v.json()
    assert body["partner_ref"] == "Cty Giấy An Bình"
    assert body["created_by_name"]  # có tên người nhập (seed admin)

    # Lọc theo NCC (chứa, không phân biệt hoa thường).
    r = client.get("/api/kho/vouchers?partner_ref=an bình", headers=h).json()
    assert any(x["id"] == body["id"] for x in r["items"])
    # Lọc NCC không khớp → không có.
    r2 = client.get("/api/kho/vouchers?partner_ref=khong-ton-tai-xyz", headers=h).json()
    assert all(x["id"] != body["id"] for x in r2["items"])
    # Lọc theo người nhập (created_by_user_id) → có phiếu.
    uid = body["created_by_user_id"]
    r3 = client.get(f"/api/kho/vouchers?created_by_user_id={uid}", headers=h).json()
    assert any(x["id"] == body["id"] for x in r3["items"])


def test_filter_by_voucher_type(client, h, env):
    _voucher(client, h, env["vt"]["NK-NVL"], [{"material_id": env["mat"], "quantity": 10}], dst=env["wh_a"])
    r = client.get(f"/api/kho/vouchers?voucher_type_id={env['vt']['NK-NVL']}", headers=h).json()
    assert r["items"] and all(x["voucher_type_id"] == env["vt"]["NK-NVL"] for x in r["items"])


def test_status_catalog_seeded(client, h, env):
    codes = {s["code"] for s in client.get("/api/kho/item-statuses", headers=h).json()["items"]}
    assert {"AVAILABLE", "RESERVED", "QC_WAIT", "DEFECT", "CANCELLED"} <= codes
