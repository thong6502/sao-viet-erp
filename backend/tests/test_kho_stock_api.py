"""Tests — Kho P0: tồn dựa trên Material (StockLot + StockMove) + SEAM-22."""
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
def mat_paper() -> int:
    """Giấy Couche 150, đơn vị tồn = tờ, khổ 65×86 (cho test quy đổi ream/kg)."""
    db = SessionLocal()
    try:
        m = Material(
            code="GY_TEST150", name="Couche 150 test", material_type="paper",
            unit="to", gsm=150, width_cm=65.0, height_cm=86.0, is_active=True,
        )
        db.add(m)
        db.commit()
        db.refresh(m)
        return m.id
    finally:
        db.close()


@pytest.fixture
def wh(client, h) -> int:
    return client.post("/api/warehouses", json={"name": "Kho P0"}, headers=h).json()["id"]


def _move(client, h, mat, wh, qty, move_type="nhap", input_uom=None, lot_id=None):
    body = {"material_id": mat, "warehouse_id": wh, "quantity": qty, "move_type": move_type}
    if input_uom:
        body["input_uom"] = input_uom
    if lot_id:
        body["lot_id"] = lot_id
    return client.post("/api/kho/moves", json=body, headers=h)


def _stock(client, h, mat, wh) -> float:
    bal = client.get(f"/api/kho/stock?material_id={mat}&warehouse_id={wh}", headers=h).json()["items"]
    return sum(b["on_hand"] for b in bal)


def test_receipt_and_issue(client, h, mat_paper, wh):
    assert _move(client, h, mat_paper, wh, 1000, "nhap").status_code == 201
    assert _stock(client, h, mat_paper, wh) == 1000
    assert _move(client, h, mat_paper, wh, 300, "xuat").status_code == 201
    assert _stock(client, h, mat_paper, wh) == 700


def test_over_issue_blocked(client, h, mat_paper, wh):
    _move(client, h, mat_paper, wh, 100, "nhap")
    assert _move(client, h, mat_paper, wh, 500, "xuat").status_code == 422


def test_unit_conversion_ream(client, h, mat_paper, wh):
    # nhập 2 ream → 1000 tờ (đơn vị tồn = to)
    assert _move(client, h, mat_paper, wh, 2, "nhap", input_uom="ream").status_code == 201
    assert _stock(client, h, mat_paper, wh) == 1000


def test_lot_qty_on_hand(client, h, mat_paper, wh):
    lot = client.post(
        "/api/kho/lots", json={"material_id": mat_paper, "warehouse_id": wh, "supplier": "An Bình"},
        headers=h,
    )
    assert lot.status_code == 201, lot.text
    lot_id = lot.json()["id"]
    _move(client, h, mat_paper, wh, 400, "nhap", lot_id=lot_id)
    lots = client.get(f"/api/kho/lots?material_id={mat_paper}", headers=h).json()["items"]
    assert next(x for x in lots if x["id"] == lot_id)["qty_on_hand"] == 400


def test_lot_must_match_material(client, h, mat_paper, wh):
    db = SessionLocal()
    try:
        other = Material(code="GY_OTHER", name="x", material_type="paper", unit="to", is_active=True)
        db.add(other)
        db.commit()
        other_id = other.id
    finally:
        db.close()
    lot = client.post(
        "/api/kho/lots", json={"material_id": mat_paper, "warehouse_id": wh}, headers=h
    ).json()
    r = _move(client, h, other_id, wh, 5, "nhap", lot_id=lot["id"])
    assert r.status_code == 422


def test_material_options_gated_by_kho(client, h, mat_paper):
    # Trang Tồn kho lấy vật tư qua endpoint này (gate `kho`), không cần quyền dm_giay_vat_tu.
    r = client.get("/api/kho/material-options", headers=h)
    assert r.status_code == 200
    opts = r.json()
    assert any(o["id"] == mat_paper for o in opts)
    picked = next(o for o in opts if o["id"] == mat_paper)
    assert picked["code"] == "GY_TEST150" and picked["unit"] == "to"


def test_nxt_report(client, h, mat_paper, wh):
    from datetime import datetime, timezone

    from app.models.warehouse_stock import StockMove

    db = SessionLocal()
    try:
        # Tồn đầu kỳ (trước 6/2026) +100; trong kỳ nhập +50, xuất −30.
        for when, delta in [
            (datetime(2026, 5, 15, tzinfo=timezone.utc), 100),
            (datetime(2026, 6, 10, tzinfo=timezone.utc), 50),
            (datetime(2026, 6, 20, tzinfo=timezone.utc), -30),
        ]:
            db.add(StockMove(material_id=mat_paper, warehouse_id=wh, qty_delta=delta,
                             unit="to", move_type="nhap", created_at=when))
        db.commit()
    finally:
        db.close()

    r = client.get(f"/api/kho/reports/nxt?from=2026-06-01&to=2026-06-30&material_id={mat_paper}", headers=h)
    assert r.status_code == 200, r.text
    row = next(x for x in r.json()["items"] if x["material_id"] == mat_paper and x["warehouse_id"] == wh)
    assert row["opening"] == 100
    assert row["in_qty"] == 50
    assert row["out_qty"] == 30
    assert row["closing"] == 120


def test_nxt_report_bad_range(client, h, mat_paper):
    r = client.get("/api/kho/reports/nxt?from=2026-06-30&to=2026-06-01", headers=h)
    assert r.status_code == 422


def test_ledger_running_balance(client, h, mat_paper, wh):
    from datetime import datetime, timezone

    from app.models.warehouse_stock import StockMove

    db = SessionLocal()
    try:
        # Tồn đầu (trước kỳ) +200; trong kỳ: +50, −30, +10.
        for when, delta, mt in [
            (datetime(2026, 5, 15, tzinfo=timezone.utc), 200, "nhap"),
            (datetime(2026, 6, 5, tzinfo=timezone.utc), 50, "nhap"),
            (datetime(2026, 6, 12, tzinfo=timezone.utc), -30, "xuat"),
            (datetime(2026, 6, 18, tzinfo=timezone.utc), 10, "dieu_chinh"),
        ]:
            db.add(StockMove(material_id=mat_paper, warehouse_id=wh, qty_delta=delta,
                             unit="to", move_type=mt, created_at=when))
        db.commit()
    finally:
        db.close()

    r = client.get(f"/api/kho/reports/ledger?material_id={mat_paper}&from=2026-06-01&to=2026-06-30", headers=h)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["opening"] == 200
    assert body["total_in"] == 60  # 50 + 10
    assert body["total_out"] == 30
    assert body["closing"] == 230  # 200 + 60 − 30
    # Tồn lũy kế đúng thứ tự thời gian: 250 → 220 → 230.
    assert [x["balance"] for x in body["items"]] == [250, 220, 230]
    assert body["items"][0]["qty_in"] == 50 and body["items"][0]["qty_out"] == 0
    assert body["items"][1]["qty_out"] == 30


def test_ledger_no_date_filter_opening_zero(client, h, mat_paper, wh):
    _move(client, h, mat_paper, wh, 100, "nhap")
    _move(client, h, mat_paper, wh, 40, "xuat")
    r = client.get(f"/api/kho/reports/ledger?material_id={mat_paper}", headers=h)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["opening"] == 0  # không lọc ngày → tồn đầu = 0
    assert body["closing"] == 60
    assert body["total"] == 2


def test_min_level_and_low_stock(client, h, mat_paper, wh):
    # Đặt ngưỡng min 500, nhập 300 → dưới ngưỡng, cảnh báo shortfall 200.
    up = client.put("/api/kho/min-levels",
                    json={"material_id": mat_paper, "warehouse_id": wh, "min_qty": 500},
                    headers=h)
    assert up.status_code == 200, up.text
    _move(client, h, mat_paper, wh, 300, "nhap")

    low = client.get("/api/kho/reports/low-stock", headers=h).json()
    row = next(x for x in low["items"] if x["material_id"] == mat_paper and x["warehouse_id"] == wh)
    assert row["min_qty"] == 500 and row["on_hand"] == 300
    assert row["shortfall"] == 200 and row["below"] is True

    # Nhập thêm 300 → tồn 600 ≥ 500 → hết cảnh báo (only_below mặc định).
    _move(client, h, mat_paper, wh, 300, "nhap")
    low2 = client.get("/api/kho/reports/low-stock", headers=h).json()
    assert not any(x["material_id"] == mat_paper for x in low2["items"])
    # only_below=false vẫn liệt kê (below=False).
    low3 = client.get("/api/kho/reports/low-stock?only_below=false", headers=h).json()
    r3 = next(x for x in low3["items"] if x["material_id"] == mat_paper)
    assert r3["below"] is False and r3["on_hand"] == 600


def test_min_level_upsert_idempotent(client, h, mat_paper, wh):
    client.put("/api/kho/min-levels", json={"material_id": mat_paper, "warehouse_id": wh, "min_qty": 100}, headers=h)
    client.put("/api/kho/min-levels", json={"material_id": mat_paper, "warehouse_id": wh, "min_qty": 250}, headers=h)
    rows = client.get("/api/kho/min-levels", headers=h).json()["items"]
    mine = [x for x in rows if x["material_id"] == mat_paper and x["warehouse_id"] == wh]
    assert len(mine) == 1 and mine[0]["min_qty"] == 250  # upsert, không tạo trùng


def test_stock_by_location(client, h, mat_paper, wh):
    lot = client.post("/api/kho/lots",
                      json={"material_id": mat_paper, "warehouse_id": wh, "location": "A1-01"},
                      headers=h).json()
    _move(client, h, mat_paper, wh, 120, "nhap", lot_id=lot["id"])
    r = client.get(f"/api/kho/reports/by-location?warehouse_id={wh}", headers=h).json()
    row = next(x for x in r["items"] if x["location"] == "A1-01" and x["material_id"] == mat_paper)
    assert row["on_hand"] == 120


def test_seam22_referenced(client, h, mat_paper, wh):
    from app.ports.paper_stock_usage_port import is_paper_referenced_in_stock

    # chưa có move → chưa tham chiếu
    assert is_paper_referenced_in_stock(mat_paper) is False
    _move(client, h, mat_paper, wh, 10, "nhap")
    # có tồn → được tham chiếu (chặn xóa vật tư)
    assert is_paper_referenced_in_stock(mat_paper) is True
