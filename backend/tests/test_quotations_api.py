"""Báo giá H-V-I API (Quote → QuoteVersion → QuoteItem).

Covers: list + status filter + stats; create bằng PICK từ phiếu tính giá — cả đường cũ
(1 phiếu: estimate_id + selected_option_ids) lẫn đường mới (đa phiếu: picks[]) với giá vốn
khóa per dòng + gói biên áp chung; validation (phiếu chưa tính → 422, hạn quá khứ → 422);
khóa sửa sau khi gửi (409); lifecycle draft→sent (freeze snapshot) → accepted/rejected,
transition sai → 409/422, hủy cần lý do; requote sinh phiên bản mới; SEAM-13 picker honest.
"""
from __future__ import annotations

from datetime import date, timedelta

from app.db import SessionLocal
from app.models.estimate import Estimate, EstimateOption

ADMIN = {"username": "admin", "password": "admin123"}
TOMORROW = (date.today() + timedelta(days=30)).isoformat()
YESTERDAY = (date.today() - timedelta(days=1)).isoformat()


def _admin_token(client) -> str:
    return client.post("/api/auth/login", json=ADMIN).json()["access_token"]


def _h(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _mk_estimate(*, product_name="Catalogue A4", quantities=(1000, 2000), unit_cost=1000,
                 status="calculated") -> tuple[int, list[int]]:
    """Dựng phiếu tính giá đã-tính trực tiếp (engine không tham gia): mỗi mức SL 1 option,
    total_cost = quantity × unit_cost. Trả (estimate_id, [option_ids])."""
    db = SessionLocal()
    try:
        n = db.query(Estimate).count() + 1
        est = Estimate(
            estimate_number=f"TGT-{n:04d}", product_type="brochure", product_name=product_name,
            status=status, input_spec_json={"finished_width": 21, "finished_height": 29.7,
                                            "colors": 4, "sides": 2},
            quantity_list_json=list(quantities),
        )
        db.add(est)
        db.flush()
        opt_ids = []
        for q in quantities:
            opt = EstimateOption(
                estimate_id=est.id, quantity=q, total_cost=q * unit_cost, warnings_json=[],
                margin_percent=20, vat_percent=10,
            )
            db.add(opt)
            db.flush()
            opt_ids.append(opt.id)
        db.commit()
        return est.id, opt_ids
    finally:
        db.close()


def _create_multi(client, token, picks, **over) -> dict:
    body = {"customer_id": None, "picks": picks, "valid_until": TOMORROW}
    body.update(over)
    r = client.post("/api/quotations", json=body, headers=_h(token))
    assert r.status_code == 201, r.text
    return r.json()


# --- list + stats ---------------------------------------------------------------

def test_list_empty_then_shows_created(client):
    token = _admin_token(client)
    r = client.get("/api/quotations", headers=_h(token))
    assert r.status_code == 200 and r.json()["total"] == 0

    eid, opts = _mk_estimate()
    q = _create_multi(client, token, [{"estimate_id": eid, "option_ids": opts[:1]}])

    body = client.get("/api/quotations?page=1&size=10", headers=_h(token)).json()
    assert body["total"] == 1
    row = body["items"][0]
    assert row["code"].startswith("BG")
    assert row["version"] == 1
    assert row["status"] == "draft"
    assert row["total"] == q["total"]
    # ↳ tham chiếu phiếu tính giá hiện trên list
    assert row["estimate_refs"] and row["estimate_refs"][0].startswith("TGT-")
    assert row["product_summary"] == "Catalogue A4"


def test_list_status_filter_and_stats(client):
    token = _admin_token(client)
    eid, opts = _mk_estimate()
    _create_multi(client, token, [{"estimate_id": eid, "option_ids": opts}])

    r = client.get("/api/quotations?status=accepted", headers=_h(token))
    assert r.status_code == 200 and r.json()["total"] == 0

    stats = client.get("/api/quotations/stats", headers=_h(token)).json()
    assert stats["total"] == 1 and stats["draft"] == 1 and stats["need_action"] == 1


# --- create: pick từ phiếu tính giá ---------------------------------------------

def test_create_multi_pick_from_two_estimates(client):
    """Logic chốt: 1 báo giá pick từ NHIỀU phiếu tính giá — mỗi dòng khóa giá vốn riêng."""
    token = _admin_token(client)
    e1, o1 = _mk_estimate(product_name="Catalogue A4", quantities=(1000,), unit_cost=1000)
    e2, o2 = _mk_estimate(product_name="Tờ rơi A5", quantities=(5000, 10000), unit_cost=200)

    q = _create_multi(client, token, [
        {"estimate_id": e1, "option_ids": o1},
        {"estimate_id": e2, "option_ids": o2},
    ], margin_percent=25)

    assert len(q["items"]) == 3  # 1 mức + 2 mức
    by_est = {}
    for it in q["items"]:
        by_est.setdefault(it["estimate_id"], []).append(it)
        assert it["estimate_number"].startswith("TGT-")
        assert it["margin_percent"] == 25.0  # gói biên áp chung
        assert it["total_cost_snapshot"] > 0  # giá vốn khóa per dòng
    assert set(by_est) == {e1, e2}

    # Giá bán mỗi dòng = giá vốn / (1 − 25%) rồi + VAT 10%
    it1 = by_est[e1][0]
    assert abs(it1["selling_price"] - 1_000_000 / 0.75) < 1
    assert abs(it1["final_amount"] - it1["selling_price"] * 1.10) < 1

    # Tổng version = cộng các dòng
    assert abs(q["total"] - sum(it["final_amount"] for it in q["items"])) < 1

    # Phiếu nguồn bị đánh dấu đã lên báo giá (không pick lại được)
    db = SessionLocal()
    try:
        assert db.get(Estimate, e1).status == "converted_to_quote"
        assert db.get(Estimate, e2).status == "converted_to_quote"
    finally:
        db.close()


def test_create_picks_requires_calculated_estimate(client):
    token = _admin_token(client)
    eid, opts = _mk_estimate(status="draft")  # chưa tính
    r = client.post(
        "/api/quotations",
        json={"picks": [{"estimate_id": eid, "option_ids": opts}], "valid_until": TOMORROW},
        headers=_h(token),
    )
    assert r.status_code == 422
    assert "Đã tính" in r.json()["detail"]

    r = client.post(
        "/api/quotations",
        json={"picks": [{"estimate_id": 99999, "option_ids": [1]}], "valid_until": TOMORROW},
        headers=_h(token),
    )
    assert r.status_code == 422


def test_create_legacy_single_estimate_path(client):
    token = _admin_token(client)
    eid, opts = _mk_estimate(quantities=(1000, 2000))
    r = client.post(
        "/api/quotations",
        json={"estimate_id": eid, "selected_option_ids": opts[:1], "valid_until": TOMORROW},
        headers=_h(token),
    )
    assert r.status_code == 201
    body = r.json()
    assert len(body["items"]) == 1
    assert body["items"][0]["estimate_id"] == eid


def test_create_past_valid_until_422(client):
    token = _admin_token(client)
    r = client.post("/api/quotations", json={"valid_until": YESTERDAY}, headers=_h(token))
    assert r.status_code == 422


# --- update draft only -----------------------------------------------------------

def test_update_locked_after_send(client):
    token = _admin_token(client)
    eid, opts = _mk_estimate()
    q = _create_multi(client, token, [{"estimate_id": eid, "option_ids": opts[:1]}])

    # sửa được khi draft (đổi % biên dòng đầu)
    item_id = q["items"][0]["id"]
    r = client.put(
        f"/api/quotations/{q['id']}",
        json={"items": [{"id": item_id, "margin_percent": 30, "vat_percent": 10}]},
        headers=_h(token),
    )
    assert r.status_code == 200, r.text
    assert r.json()["items"][0]["margin_percent"] == 30.0

    # gửi khách → khóa
    r = client.post(f"/api/quotations/{q['id']}/transition", json={"to_status": "sent"}, headers=_h(token))
    assert r.status_code == 200
    r = client.put(
        f"/api/quotations/{q['id']}",
        json={"items": [{"id": item_id, "margin_percent": 5}]},
        headers=_h(token),
    )
    assert r.status_code == 409


# --- lifecycle --------------------------------------------------------------------

def test_send_freezes_snapshot_then_accept(client):
    token = _admin_token(client)
    eid, opts = _mk_estimate()
    q = _create_multi(client, token, [{"estimate_id": eid, "option_ids": opts}])

    r = client.post(f"/api/quotations/{q['id']}/transition", json={"to_status": "sent"}, headers=_h(token))
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "sent"
    assert "accepted" in body["allowed_transitions"]

    r = client.post(f"/api/quotations/{q['id']}/transition", json={"to_status": "accepted"}, headers=_h(token))
    assert r.status_code == 200 and r.json()["status"] == "accepted"


def test_illegal_transition_conflict(client):
    token = _admin_token(client)
    eid, opts = _mk_estimate()
    q = _create_multi(client, token, [{"estimate_id": eid, "option_ids": opts}])
    # draft → rejected là bất hợp lệ
    r = client.post(f"/api/quotations/{q['id']}/transition", json={"to_status": "rejected"}, headers=_h(token))
    assert r.status_code == 409
    # trạng thái lạ → 422
    r = client.post(f"/api/quotations/{q['id']}/transition", json={"to_status": "banana"}, headers=_h(token))
    assert r.status_code == 422


def test_cancel_requires_reason(client):
    token = _admin_token(client)
    eid, opts = _mk_estimate()
    q = _create_multi(client, token, [{"estimate_id": eid, "option_ids": opts}])
    r = client.post(f"/api/quotations/{q['id']}/transition", json={"to_status": "cancelled"}, headers=_h(token))
    assert r.status_code == 422
    r = client.post(
        f"/api/quotations/{q['id']}/transition",
        json={"to_status": "cancelled", "cancel_reason": "Khách đổi ý"},
        headers=_h(token),
    )
    assert r.status_code == 200 and r.json()["status"] == "cancelled"


def test_requote_new_version(client):
    token = _admin_token(client)
    eid, opts = _mk_estimate()
    q = _create_multi(client, token, [{"estimate_id": eid, "option_ids": opts}])
    client.post(f"/api/quotations/{q['id']}/transition", json={"to_status": "sent"}, headers=_h(token))

    # Tạo phiên bản mới BẮT BUỘC ghi chú — thiếu → 422.
    r0 = client.post(f"/api/quotations/{q['id']}/requote", json={"change_reason": "  "}, headers=_h(token))
    assert r0.status_code == 422, r0.text

    r = client.post(f"/api/quotations/{q['id']}/requote",
                    json={"change_reason": "KH đổi số lượng"}, headers=_h(token))
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["version"] == 2
    assert len(body["versions"]) == 2
    # phiên bản cũ giữ nguyên trong lịch sử
    assert {v["version"] for v in body["versions"]} == {1, 2}
    # ghi chú in vào phiên bản mới (Lịch sử phiên bản)
    v2 = next(v for v in body["versions"] if v["version"] == 2)
    assert v2["change_reason"] == "KH đổi số lượng"


def test_requote_from_draft_allowed(client):
    """Ngay khi còn NHÁP vẫn tạo được phiên bản mới (giữ v1, làm variant giá khác) — bắt buộc ghi chú."""
    token = _admin_token(client)
    eid, opts = _mk_estimate()
    q = _create_multi(client, token, [{"estimate_id": eid, "option_ids": opts}])
    r = client.post(f"/api/quotations/{q['id']}/requote",
                    json={"change_reason": "thử giá 25%"}, headers=_h(token))
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["version"] == 2
    assert {v["version"] for v in body["versions"]} == {1, 2}
    assert body["status"] == "draft"


def test_activity_feed_records_who_did_what(client):
    """Feed Hoạt động = nhật ký THẬT (ai làm gì): mọi thao tác để lại dấu vết + tên người."""
    token = _admin_token(client)
    eid, opts = _mk_estimate()
    q = _create_multi(client, token, [{"estimate_id": eid, "option_ids": opts}])
    client.post(f"/api/quotations/{q['id']}/transition", json={"to_status": "sent"}, headers=_h(token))

    r = client.get(f"/api/quotations/{q['id']}/activity", headers=_h(token))
    assert r.status_code == 200, r.text
    items = r.json()["items"]
    actions = [it["action"] for it in items]
    assert "create_quote" in actions
    assert "transition_sent" in actions
    # có TÊN người thao tác (biết ai làm) — không rỗng
    assert any(it["actor_name"] for it in items)
    # mới nhất trước: gửi khách đứng trước tạo báo giá
    assert actions.index("transition_sent") < actions.index("create_quote")


# --- SEAM-13 costing picker --------------------------------------------------------

def test_costing_picker_not_found_is_honest(client):
    token = _admin_token(client)
    r = client.get("/api/quotations/costings/99999", headers=_h(token))
    assert r.status_code == 200
    body = r.json()
    assert body["available"] is False
    assert body.get("options") in (None, [])  # never a fabricated cost


def test_costing_picker_pulls_calculated_estimate(client):
    token = _admin_token(client)
    eid, _ = _mk_estimate(quantities=(1000, 2000), unit_cost=500)
    r = client.get(f"/api/quotations/costings/{eid}", headers=_h(token))
    assert r.status_code == 200
    body = r.json()
    assert body["available"] is True
    assert [o["quantity"] for o in body["options"]] == [1000, 2000]
    assert body["options"][0]["total_cost"] == 500_000
