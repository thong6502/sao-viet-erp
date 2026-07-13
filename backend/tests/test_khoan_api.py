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
    """Chốt sổ → tiền khoán mỗi NV chảy vào cột khoan; sổ chưa chốt KHÔNG vào lương."""
    token = _admin_token(client)
    e = _make_emp(client, token, name="Khoán D", status="active")
    bid = _open(client, token, 2026, 10, "to_cat")["batch"]["id"]
    client.post(f"/api/luong/khoan/batches/{bid}/entries", json={"work_name": "Cắt giấy", "unit": "tan", "unit_price": 100000, "quantity": 5}, headers=_h(token))  # 500k
    client.post(f"/api/luong/khoan/batches/{bid}/shares", json={"employee_id": e, "weight": 1}, headers=_h(token))

    # Sổ CHƯA chốt → khoán chưa vào lương.
    gen0 = client.post("/api/luong/generate", json={"year": 2026, "month": 10}, headers=_h(token)).json()
    assert next(l for l in gen0["lines"] if l["employee_id"] == e)["khoan"] == 0

    # Chốt sổ → vào lương.
    assert client.post(f"/api/luong/khoan/batches/{bid}/lock", headers=_h(token)).status_code == 200
    gen = client.post("/api/luong/generate", json={"year": 2026, "month": 10}, headers=_h(token)).json()
    line = next(l for l in gen["lines"] if l["employee_id"] == e)
    assert line["khoan"] == 500000 and line["gross"] == 500000

    # Mở lại sổ → xóa dòng → chốt lại → khoan về 0.
    client.post(f"/api/luong/khoan/batches/{bid}/reopen", headers=_h(token))
    entries = client.get(f"/api/luong/khoan/sheet?year=2026&month=10&group_name=to_cat", headers=_h(token)).json()["entries"]
    client.delete(f"/api/luong/khoan/entries/{entries[0]['id']}", headers=_h(token))
    client.post(f"/api/luong/khoan/batches/{bid}/lock", headers=_h(token))
    gen2 = client.post("/api/luong/generate", json={"year": 2026, "month": 10}, headers=_h(token)).json()
    assert next(l for l in gen2["lines"] if l["employee_id"] == e)["khoan"] == 0


def test_leader_cut_excludes_bu_lo(client):
    """Q3: % tổ trưởng tính trên quỹ thực (100k), KHÔNG trên phần bù lỗ (tổng 300k)."""
    token = _admin_token(client)
    lead = _make_emp(client, token, name="Tổ trưởng")
    mem = _make_emp(client, token, name="Thợ")
    bid = _open(client, token, 2026, 7, "to_can_phu")["batch"]["id"]
    client.put(f"/api/luong/khoan/batches/{bid}/config",
               json={"leader_employee_id": lead, "leader_pct": 0.05, "min_guarantee": 300000}, headers=_h(token))
    client.post(f"/api/luong/khoan/batches/{bid}/entries", json={"work_name": "Cán", "unit": "m2", "unit_price": 1000, "quantity": 100}, headers=_h(token))  # 100k
    client.post(f"/api/luong/khoan/batches/{bid}/shares", json={"employee_id": lead, "weight": 1}, headers=_h(token))
    sh = client.post(f"/api/luong/khoan/batches/{bid}/shares", json={"employee_id": mem, "weight": 1}, headers=_h(token)).json()
    assert sh["meta"]["total"] == 300000 and sh["meta"]["leader_cut"] == 5000   # 100k×5%, KHÔNG 300k×5%
    amt = {s["employee_id"]: s["amount"] for s in sh["shares"]}
    assert amt[lead] == 152500 and amt[mem] == 147500 and amt[lead] + amt[mem] == 300000


def test_rounding_keeps_total(client):
    """Đồng lẻ làm tròn dồn 1 người → Σ chia == total tuyệt đối."""
    token = _admin_token(client)
    ids = [_make_emp(client, token, name=f"Chia {i}") for i in range(3)]
    bid = _open(client, token, 2026, 6, "to_cat")["batch"]["id"]
    client.post(f"/api/luong/khoan/batches/{bid}/entries", json={"work_name": "Cắt", "unit": "tan", "unit_price": 1, "quantity": 100000}, headers=_h(token))
    sh = None
    for i in ids:
        sh = client.post(f"/api/luong/khoan/batches/{bid}/shares", json={"employee_id": i, "weight": 1}, headers=_h(token)).json()
    assert sum(s["amount"] for s in sh["shares"]) == 100000   # 33333+33333+33334


def test_leader_no_share_blocks_lock(client):
    """Tổ trưởng không có dòng chia → sổ không hợp lệ, chặn chốt sổ (Q2=A)."""
    token = _admin_token(client)
    lead = _make_emp(client, token, name="TT vắng")
    mem = _make_emp(client, token, name="TV")
    bid = _open(client, token, 2026, 5, "to_boi")["batch"]["id"]
    client.put(f"/api/luong/khoan/batches/{bid}/config", json={"leader_employee_id": lead, "leader_pct": 0.05}, headers=_h(token))
    client.post(f"/api/luong/khoan/batches/{bid}/entries", json={"work_name": "Bồi", "unit": "m2", "unit_price": 1000, "quantity": 100}, headers=_h(token))
    sh = client.post(f"/api/luong/khoan/batches/{bid}/shares", json={"employee_id": mem, "weight": 1}, headers=_h(token)).json()
    assert sh["meta"]["valid"] is False and sh["meta"]["leader_no_share"] is True
    assert client.post(f"/api/luong/khoan/batches/{bid}/lock", headers=_h(token)).status_code == 400


def test_zero_weight_blocks_lock(client):
    """Chưa nhập hệ số (weight=0) → sổ không hợp lệ, chặn chốt (Q2=A)."""
    token = _admin_token(client)
    e = _make_emp(client, token, name="Hệ số 0")
    bid = _open(client, token, 2026, 4, "to_cat")["batch"]["id"]
    client.post(f"/api/luong/khoan/batches/{bid}/entries", json={"work_name": "Cắt", "unit": "tan", "unit_price": 1000, "quantity": 100}, headers=_h(token))
    sh = client.post(f"/api/luong/khoan/batches/{bid}/shares", json={"employee_id": e, "weight": 0}, headers=_h(token)).json()
    assert sh["meta"]["valid"] is False and sh["meta"]["zero_weight"] is True
    assert client.post(f"/api/luong/khoan/batches/{bid}/lock", headers=_h(token)).status_code == 400


def test_locked_sheet_blocks_edit(client):
    """Sổ đã chốt → cấm sửa sản lượng."""
    token = _admin_token(client)
    e = _make_emp(client, token, name="Khoá sổ")
    bid = _open(client, token, 2026, 3, "to_cat")["batch"]["id"]
    client.post(f"/api/luong/khoan/batches/{bid}/entries", json={"work_name": "Cắt", "unit": "tan", "unit_price": 1000, "quantity": 100}, headers=_h(token))
    client.post(f"/api/luong/khoan/batches/{bid}/shares", json={"employee_id": e, "weight": 1}, headers=_h(token))
    assert client.post(f"/api/luong/khoan/batches/{bid}/lock", headers=_h(token)).status_code == 200
    r = client.post(f"/api/luong/khoan/batches/{bid}/entries", json={"work_name": "Thêm", "unit": "tan", "unit_price": 1, "quantity": 1}, headers=_h(token))
    assert r.status_code == 400


def test_payroll_locked_blocks_sheet_edit(client):
    """Kỳ lương đã chốt → cấm sửa sổ khoán tháng đó (đồng bộ khóa)."""
    token = _admin_token(client)
    e = _make_emp(client, token, name="Đồng bộ", status="active")
    bid = _open(client, token, 2026, 2, "to_cat")["batch"]["id"]
    client.post(f"/api/luong/khoan/batches/{bid}/entries", json={"work_name": "Cắt", "unit": "tan", "unit_price": 1000, "quantity": 100}, headers=_h(token))
    client.post(f"/api/luong/khoan/batches/{bid}/shares", json={"employee_id": e, "weight": 1}, headers=_h(token))
    client.post("/api/luong/generate", json={"year": 2026, "month": 2}, headers=_h(token))
    assert client.post("/api/luong/lock", json={"year": 2026, "month": 2}, headers=_h(token)).status_code == 200
    r = client.post(f"/api/luong/khoan/batches/{bid}/shares", json={"employee_id": e, "weight": 2}, headers=_h(token))
    assert r.status_code == 400
