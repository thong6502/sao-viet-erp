"""Lương khoán (module `luong` nhịp 2): đơn giá + sổ khoán (quỹ tổ + bù lỗ + thưởng vượt
+ chia tổ trưởng 5% + hệ số) + nối vào bảng lương (cột khoan → gross)."""
from __future__ import annotations

from app.db import SessionLocal
from app.repositories.rbac_repo import DepartmentRepository

ADMIN = {"username": "admin", "password": "admin123"}


def _admin_token(client) -> str:
    return client.post("/api/auth/login", json=ADMIN).json()["access_token"]


def _h(t: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {t}"}


def _dept_id(name: str) -> int:
    db = SessionLocal()
    try:
        return DepartmentRepository(db).get_by_name(name).id
    finally:
        db.close()


def _make_emp(client, token, *, name, status=None) -> int:
    body = {"full_name": name, "department_id": _dept_id("Hành chính nhân sự"),
            "hire_date": "2020-01-01", "gender": "male"}
    if status:
        body["status"] = status
    return client.post("/api/employees", json=body, headers=_h(token)).json()["employee"]["id"]


def _open(client, token, y, m, g):
    return client.post(f"/api/luong/khoan/sheet?year={y}&month={m}&group_name={g}", headers=_h(token)).json()


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


def test_sheet_distribution(client):
    """Quỹ 100k, tổ trưởng 5% + 2 thành viên hệ số 1:1 → 52.500 / 47.500."""
    token = _admin_token(client)
    e1 = _make_emp(client, token, name="Khoán A")
    e2 = _make_emp(client, token, name="Khoán B")
    bid = _open(client, token, 2026, 8, "to_boi")["batch"]["id"]
    client.put(f"/api/luong/khoan/batches/{bid}/config", json={"leader_employee_id": e1, "leader_pct": 0.05}, headers=_h(token))
    client.post(f"/api/luong/khoan/batches/{bid}/entries", json={"work_name": "Bồi", "unit": "m2", "unit_price": 1000, "quantity": 100}, headers=_h(token))
    client.post(f"/api/luong/khoan/batches/{bid}/shares", json={"employee_id": e1, "weight": 1}, headers=_h(token))
    sh = client.post(f"/api/luong/khoan/batches/{bid}/shares", json={"employee_id": e2, "weight": 1}, headers=_h(token)).json()

    assert sh["meta"]["revenue"] == 100000 and sh["meta"]["total"] == 100000 and sh["meta"]["leader_cut"] == 5000
    amt = {s["employee_id"]: s["amount"] for s in sh["shares"]}
    assert amt[e1] == 52500 and amt[e2] == 47500   # 5000 + 47500 ; 47500


def test_bu_lo_min_guarantee(client):
    """Quỹ 100k < bù lỗ 200k → tổng lấy 200k."""
    token = _admin_token(client)
    e = _make_emp(client, token, name="Khoán C")
    bid = _open(client, token, 2026, 9, "may_in_5mau")["batch"]["id"]
    client.put(f"/api/luong/khoan/batches/{bid}/config", json={"min_guarantee": 200000}, headers=_h(token))
    client.post(f"/api/luong/khoan/batches/{bid}/entries", json={"work_name": "In", "unit": "bai_in", "unit_price": 1000, "quantity": 100}, headers=_h(token))
    sh = client.post(f"/api/luong/khoan/batches/{bid}/shares", json={"employee_id": e, "weight": 1}, headers=_h(token)).json()
    assert sh["meta"]["revenue"] == 100000 and sh["meta"]["total"] == 200000
    assert sh["shares"][0]["amount"] == 200000


def test_over_bonus(client):
    """Quỹ 300k, mốc vượt 200k, thưởng 40% → tổng 340k."""
    token = _admin_token(client)
    e = _make_emp(client, token, name="Khoán E")
    bid = _open(client, token, 2026, 11, "may_in_5mau")["batch"]["id"]
    client.put(f"/api/luong/khoan/batches/{bid}/config", json={"over_target": 200000, "over_bonus_pct": 0.4}, headers=_h(token))
    client.post(f"/api/luong/khoan/batches/{bid}/entries", json={"work_name": "In", "unit": "bai_in", "unit_price": 1000, "quantity": 300}, headers=_h(token))
    sh = client.post(f"/api/luong/khoan/batches/{bid}/shares", json={"employee_id": e, "weight": 1}, headers=_h(token)).json()
    assert sh["meta"]["revenue"] == 300000 and sh["meta"]["total"] == 340000   # 300k + (100k×0.4)


def test_khoan_flows_into_payroll(client):
    """Tiền khoán mỗi NV → cột khoan của bảng lương, cộng vào gross."""
    token = _admin_token(client)
    e = _make_emp(client, token, name="Khoán D", status="active")
    bid = _open(client, token, 2026, 10, "to_cat")["batch"]["id"]
    client.post(f"/api/luong/khoan/batches/{bid}/entries", json={"work_name": "Cắt giấy", "unit": "tan", "unit_price": 100000, "quantity": 5}, headers=_h(token))  # 500k
    client.post(f"/api/luong/khoan/batches/{bid}/shares", json={"employee_id": e, "weight": 1}, headers=_h(token))

    gen = client.post("/api/luong/generate", json={"year": 2026, "month": 10}, headers=_h(token)).json()
    line = next(l for l in gen["lines"] if l["employee_id"] == e)
    assert line["khoan"] == 500000
    # NV không có lương thời gian → gross = khoán.
    assert line["gross"] == 500000

    # xóa dòng sản lượng → tính lại quỹ = 0 → khoan về 0 sau generate lại
    entries = client.get(f"/api/luong/khoan/sheet?year=2026&month=10&group_name=to_cat", headers=_h(token)).json()["entries"]
    client.delete(f"/api/luong/khoan/entries/{entries[0]['id']}", headers=_h(token))
    gen2 = client.post("/api/luong/generate", json={"year": 2026, "month": 10}, headers=_h(token)).json()
    line2 = next(l for l in gen2["lines"] if l["employee_id"] == e)
    assert line2["khoan"] == 0
