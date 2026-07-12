"""Lịch làm việc & Ngày lễ (module `nhan_su`, Pha 1 — nền dùng chung).

Kiểm qua API: cấu hình tuần (mặc định T2–T7, đổi, chặn 0 ngày làm) · CRUD ngày đặc biệt
(lễ + làm bù, chặn trùng ngày) · công chuẩn tháng động (loại lễ, cộng làm bù) · seed lễ dương.
"""
from __future__ import annotations

ADMIN = {"username": "admin", "password": "admin123"}


def _token(client) -> str:
    return client.post("/api/auth/login", json=ADMIN).json()["access_token"]


def _h(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


_ALL_DAYS = ("works_mon", "works_tue", "works_wed", "works_thu", "works_fri", "works_sat", "works_sun")


# --- cấu hình tuần ----------------------------------------------------------


def test_config_default_mon_to_sat(client):
    """Mặc định: T2–T7 làm, CN nghỉ."""
    t = _token(client)
    c = client.get("/api/calendar/config", headers=_h(t)).json()
    assert c["works_mon"] and c["works_fri"] and c["works_sat"]
    assert c["works_sun"] is False


def test_config_update_and_reject_empty_week(client):
    t = _token(client)
    ok = client.put("/api/calendar/config", json={"works_sat": False}, headers=_h(t))
    assert ok.status_code == 200 and ok.json()["works_sat"] is False
    # Tắt hết → không có ngày làm nào → 400.
    bad = client.put("/api/calendar/config", json={k: False for k in _ALL_DAYS}, headers=_h(t))
    assert bad.status_code == 400


def test_config_saturday_off_shrinks_standard_cong(client):
    """Tắt Thứ 7 → công chuẩn tháng giảm đúng số Thứ 7 trong tháng."""
    t = _token(client)
    base = client.get("/api/calendar/month", params={"year": 2026, "month": 8}, headers=_h(t)).json()
    assert base["working_days"] == 26  # T8/2026: 31 ngày − 5 CN
    client.put("/api/calendar/config", json={"works_sat": False}, headers=_h(t))
    after = client.get("/api/calendar/month", params={"year": 2026, "month": 8}, headers=_h(t)).json()
    assert after["working_days"] == 21  # trừ thêm 5 Thứ 7


# --- ngày đặc biệt ----------------------------------------------------------


def test_seeded_holidays_present(client):
    t = _token(client)
    d = client.get("/api/calendar/special-days", params={"year": 2026}, headers=_h(t)).json()
    assert d["statutory_paid"] == 11
    assert d["paid_off_count"] == 4  # 1/1, 30/4, 1/5, 2/9 (Tết/Giỗ Tổ do admin nhập)
    dates = {x["day"] for x in d["items"]}
    assert {"2026-01-01", "2026-04-30", "2026-05-01", "2026-09-02"} <= dates


def test_special_day_crud_and_duplicate(client):
    t = _token(client)
    r = client.post("/api/calendar/special-days",
                    json={"day": "2026-08-10", "kind": "off", "name": "Lễ test"}, headers=_h(t))
    assert r.status_code == 201
    sid = r.json()["id"]
    # Khai trùng ngày → 400.
    dup = client.post("/api/calendar/special-days",
                      json={"day": "2026-08-10", "kind": "off", "name": "Khác"}, headers=_h(t))
    assert dup.status_code == 400
    up = client.put(f"/api/calendar/special-days/{sid}",
                    json={"day": "2026-08-11", "kind": "off", "name": "Lễ test 2"}, headers=_h(t))
    assert up.status_code == 200 and up.json()["day"] == "2026-08-11"
    assert client.delete(f"/api/calendar/special-days/{sid}", headers=_h(t)).status_code == 204


def test_invalid_kind_rejected(client):
    t = _token(client)
    bad = client.post("/api/calendar/special-days",
                      json={"day": "2026-08-12", "kind": "xxx", "name": "Z"}, headers=_h(t))
    assert bad.status_code == 400


# --- công chuẩn tháng động --------------------------------------------------


def test_holiday_excluded_from_standard_cong(client):
    """Lễ 2/9 (ngày làm) bị loại khỏi công chuẩn tháng 9."""
    t = _token(client)
    m = client.get("/api/calendar/month", params={"year": 2026, "month": 9}, headers=_h(t)).json()
    assert m["working_days"] == 25  # 26 ngày làm − lễ 2/9
    assert any(h["date"] == "2026-09-02" for h in m["holidays"])
    cell = next(x for x in m["days"] if x["date"] == "2026-09-02")
    assert cell["kind"] == "holiday" and cell["is_working"] is False


def test_makeup_day_counts_as_working(client):
    """Làm bù vào Chủ Nhật → tính là ngày làm, công chuẩn +1."""
    t = _token(client)
    client.post("/api/calendar/special-days",
                json={"day": "2026-08-02", "kind": "work", "name": "Làm bù"}, headers=_h(t))
    m = client.get("/api/calendar/month", params={"year": 2026, "month": 8}, headers=_h(t)).json()
    cell = next(x for x in m["days"] if x["date"] == "2026-08-02")
    assert cell["kind"] == "makeup" and cell["is_working"] is True
    assert m["working_days"] == 27  # 26 + 1 làm bù


def test_new_holiday_on_workday_reduces_standard_cong(client):
    t = _token(client)
    client.post("/api/calendar/special-days",
                json={"day": "2026-08-03", "kind": "off", "name": "Nghỉ đặc biệt"}, headers=_h(t))
    m = client.get("/api/calendar/month", params={"year": 2026, "month": 8}, headers=_h(t)).json()
    assert m["working_days"] == 25  # 26 − 1
    cell = next(x for x in m["days"] if x["date"] == "2026-08-03")
    assert cell["kind"] == "holiday"
