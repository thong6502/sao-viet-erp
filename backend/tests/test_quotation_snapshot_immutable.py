"""Lát 11 — snapshot copy-on-write (nghiệm thu chốt của trụ Snapshot).

Yêu cầu thiết kế: "chốt báo giá xong, sửa bảng giá danh mục / tính lại phiếu tính giá
SAU đó KHÔNG được làm đổi giá vốn đã khóa trong báo giá đã tạo."

Chứng minh end-to-end: tạo báo giá từ 1 phiếu tính giá (giá vốn 1.000.000), rồi sửa
total_cost của phiếu tính giá thành 2.000.000 (mô phỏng đổi bảng giá → tính lại), đọc lại
báo giá → total_cost_snapshot vẫn 1.000.000 (không theo).
"""
from datetime import date, timedelta

from app.db import SessionLocal
from app.models.estimate import Estimate, EstimateOption

ADMIN = {"username": "admin", "password": "admin123"}
TOMORROW = (date.today() + timedelta(days=30)).isoformat()


def _token(client):
    return client.post("/api/auth/login", json=ADMIN).json()["access_token"]


def _h(t):
    return {"Authorization": f"Bearer {t}"}


def _mk_estimate(unit_cost, qty=1000):
    db = SessionLocal()
    try:
        n = db.query(Estimate).count() + 1
        est = Estimate(estimate_number=f"TGT-IMM-{n:04d}", product_type="brochure",
                       product_name="Cat", status="calculated",
                       input_spec_json={"colors": 4, "sides": 2}, quantity_list_json=[qty])
        db.add(est)
        db.flush()
        opt = EstimateOption(estimate_id=est.id, quantity=qty, total_cost=qty * unit_cost,
                             warnings_json=[], margin_percent=20, vat_percent=10)
        db.add(opt)
        db.flush()
        db.commit()
        return est.id, opt.id
    finally:
        db.close()


def test_quote_cost_frozen_after_estimate_cost_changes(client):
    token = _token(client)
    eid, oid = _mk_estimate(unit_cost=1000)  # total_cost = 1.000.000

    body = {"customer_id": None, "picks": [{"estimate_id": eid, "option_ids": [oid]}],
            "valid_until": TOMORROW}
    created = client.post("/api/quotations", json=body, headers=_h(token))
    assert created.status_code == 201, created.text
    qid = created.json()["id"]
    assert created.json()["items"][0]["total_cost_snapshot"] == 1_000_000

    # Mô phỏng "đổi bảng giá danh mục" → phiếu tính giá tính lại giá vốn gấp đôi.
    db = SessionLocal()
    try:
        opt = db.get(EstimateOption, oid)
        opt.total_cost = 2_000_000
        db.commit()
    finally:
        db.close()

    # Đọc lại báo giá đã tạo: giá vốn khóa KHÔNG đổi (copy-on-write, không tham chiếu sống).
    got = client.get(f"/api/quotations/{qid}", headers=_h(token))
    assert got.status_code == 200, got.text
    assert got.json()["items"][0]["total_cost_snapshot"] == 1_000_000
