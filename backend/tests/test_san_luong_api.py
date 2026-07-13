"""Phiếu sản lượng công đoạn (Pha 5b-1): phiếu theo tổ → Chốt sổ → vào lương; LSX bù; công đoạn không khoán."""
from __future__ import annotations

from app.db import SessionLocal
from app.repositories.rbac_repo import DepartmentRepository

ADMIN = {"username": "admin", "password": "admin123"}


def _token(client) -> str:
    return client.post("/api/auth/login", json=ADMIN).json()["access_token"]


def _h(t: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {t}"}


def _dept_id(name: str) -> int:
    db = SessionLocal()
    try:
        return DepartmentRepository(db).get_by_name(name).id
    finally:
        db.close()


def _make_emp(client, token, *, name) -> int:
    body = {"full_name": name, "department_id": _dept_id("Hành chính nhân sự"),
            "hire_date": "2020-01-01", "gender": "male", "status": "active"}
    return client.post("/api/employees", json=body, headers=_h(token)).json()["employee"]["id"]


def _make_cd(client, token, ma, ghi="to", pct=0, abs_=0):
    return client.post("/api/cong-doan", json={
        "ma": ma, "ten": f"In {ma}", "nhom": "print", "khoan_ghi_theo": ghi,
        "allowed_defect_pct": pct, "allowed_defect_abs": abs_,
        "che_do_tinh": "theo_san_luong", "pricing_basis": "per_other",
    }, headers=_h(token))


def _make_lsx(client, token, kind="thuong") -> int:
    return client.post("/api/san-xuat/orders", json={
        "product_name": "SP test", "quantity": 10000, "order_kind": kind,
    }, headers=_h(token)).json()["id"]


def test_output_flows_to_payroll_via_lock(client):
    """Ghi phiếu SL theo tổ → xem trước quỹ → chốt sổ → tiền vào lương; chưa chốt thì chưa vào."""
    token = _token(client)
    e = _make_emp(client, token, name="SL A")
    _make_cd(client, token, "IN-SLA", "to")
    lsx = _make_lsx(client, token)
    r = client.post("/api/san-luong/outputs", json={
        "production_order_id": lsx, "cong_doan": "IN-SLA", "year": 2027, "month": 1,
        "group_name": "to_boi", "work_name": "In", "unit": "m2", "unit_price": 170, "quantity": 30000,
    }, headers=_h(token))
    assert r.status_code == 201 and r.json()["amount"] == 5100000 and r.json()["tinh_khoan"] is True

    bid = client.post("/api/luong/khoan/sheet?year=2027&month=1&group_name=to_boi", headers=_h(token)).json()["batch"]["id"]
    client.post(f"/api/luong/khoan/batches/{bid}/shares", json={"employee_id": e, "weight": 1}, headers=_h(token))

    # Xem trước: kéo phiếu vào sổ (chưa chốt) → quỹ 5.1tr.
    sh = client.post(f"/api/luong/khoan/batches/{bid}/sync-outputs", headers=_h(token)).json()
    assert sh["meta"]["revenue"] == 5100000
    assert any(en["source"] == "phieu" for en in sh["entries"])

    # Sổ chưa chốt → chưa vào lương.
    gen0 = client.post("/api/luong/generate", json={"year": 2027, "month": 1}, headers=_h(token)).json()
    assert next(l for l in gen0["lines"] if l["employee_id"] == e)["khoan"] == 0

    # Chốt sổ → vào lương.
    assert client.post(f"/api/luong/khoan/batches/{bid}/lock", headers=_h(token)).status_code == 200
    gen = client.post("/api/luong/generate", json={"year": 2027, "month": 1}, headers=_h(token)).json()
    assert next(l for l in gen["lines"] if l["employee_id"] == e)["khoan"] == 5100000


def test_output_bu_lsx_default_no_khoan(client):
    """LSX bù → phiếu mặc định tinh_khoan=false → không chảy vào quỹ khi chốt."""
    token = _token(client)
    e = _make_emp(client, token, name="SL Bù")
    _make_cd(client, token, "IN-SLB", "to")
    lsx = _make_lsx(client, token, kind="bu")
    r = client.post("/api/san-luong/outputs", json={
        "production_order_id": lsx, "cong_doan": "IN-SLB", "year": 2027, "month": 2,
        "group_name": "to_cat", "work_name": "In lại", "unit": "m2", "unit_price": 170, "quantity": 10000,
    }, headers=_h(token))
    assert r.status_code == 201 and r.json()["tinh_khoan"] is False

    bid = client.post("/api/luong/khoan/sheet?year=2027&month=2&group_name=to_cat", headers=_h(token)).json()["batch"]["id"]
    client.post(f"/api/luong/khoan/batches/{bid}/shares", json={"employee_id": e, "weight": 1}, headers=_h(token))
    sh = client.post(f"/api/luong/khoan/batches/{bid}/sync-outputs", headers=_h(token)).json()
    assert sh["meta"]["revenue"] == 0   # tinh_khoan=false không materialize


def test_cong_doan_khong_khoan_rejected(client):
    """Công đoạn khai 'khong' → chặn ghi phiếu khoán."""
    token = _token(client)
    _make_cd(client, token, "IN-SLC", "khong")
    lsx = _make_lsx(client, token)
    r = client.post("/api/san-luong/outputs", json={
        "production_order_id": lsx, "cong_doan": "IN-SLC", "year": 2027, "month": 3,
        "group_name": "to_boi", "work_name": "In", "unit": "m2", "unit_price": 170, "quantity": 100,
    }, headers=_h(token))
    assert r.status_code == 400


def test_defect_deduction_loi_tho_only(client):
    """Trừ lỗi (5b-2): chỉ lỗi DO THỢ + vượt ngưỡng mới trừ; lỗi vật tư → không trừ."""
    token = _token(client)
    _make_cd(client, token, "IN-DEF", "to", pct=0.02, abs_=100)
    lsx = _make_lsx(client, token)
    # đạt 1000, hỏng 200, lỗi thợ; ngưỡng = max(1200×2%=24, 100)=100 → vượt 100 tờ × 170 = 17.000.
    r = client.post("/api/san-luong/outputs", json={
        "production_order_id": lsx, "cong_doan": "IN-DEF", "year": 2027, "month": 4,
        "group_name": "to_boi", "unit": "m2", "unit_price": 170, "quantity": 1000,
        "defect_qty": 200, "defect_cause": "loi_tho",
    }, headers=_h(token)).json()
    assert r["amount"] == 170000 and r["defect_deduction"] == 17000 and r["net_amount"] == 153000
    # Cùng số hỏng nhưng lỗi VẬT TƯ → không trừ.
    r2 = client.post("/api/san-luong/outputs", json={
        "production_order_id": lsx, "cong_doan": "IN-DEF", "year": 2027, "month": 4,
        "group_name": "to_cat", "unit": "m2", "unit_price": 170, "quantity": 1000,
        "defect_qty": 200, "defect_cause": "vat_tu",
    }, headers=_h(token)).json()
    assert r2["defect_deduction"] == 0 and r2["net_amount"] == 170000


def test_theo_nguoi_flows_to_payroll(client):
    """Ghi theo NGƯỜI → tiền vào lương khi chốt sổ tổ (dù sổ không có dòng chia quỹ)."""
    token = _token(client)
    e = _make_emp(client, token, name="Theo nguoi")
    _make_cd(client, token, "CAT-NG", "nguoi")
    lsx = _make_lsx(client, token)
    r = client.post("/api/san-luong/outputs", json={
        "production_order_id": lsx, "cong_doan": "CAT-NG", "year": 2027, "month": 5,
        "group_name": "to_cat", "employee_id": e, "unit": "m2", "unit_price": 200, "quantity": 500,
    }, headers=_h(token))
    assert r.status_code == 201 and r.json()["ghi_theo"] == "nguoi"

    # Mở sổ tổ (không cần dòng chia) → chốt được vì không có quỹ.
    bid = client.post("/api/luong/khoan/sheet?year=2027&month=5&group_name=to_cat", headers=_h(token)).json()["batch"]["id"]
    assert client.post(f"/api/luong/khoan/batches/{bid}/lock", headers=_h(token)).status_code == 200
    gen = client.post("/api/luong/generate", json={"year": 2027, "month": 5}, headers=_h(token)).json()
    assert next(l for l in gen["lines"] if l["employee_id"] == e)["khoan"] == 100000   # 500×200


def test_defect_report(client):
    """Report tỉ lệ hỏng theo tổ."""
    token = _token(client)
    _make_cd(client, token, "IN-RPT", "to")
    lsx = _make_lsx(client, token)
    client.post("/api/san-luong/outputs", json={
        "production_order_id": lsx, "cong_doan": "IN-RPT", "year": 2027, "month": 6,
        "group_name": "to_boi", "unit": "m2", "unit_price": 10, "quantity": 900, "defect_qty": 100,
        "defect_cause": "loi_tho",
    }, headers=_h(token))
    rep = client.get("/api/san-luong/defect-report?year=2027&month=6", headers=_h(token)).json()
    row = next(x for x in rep["items"] if x["group_name"] == "to_boi")
    assert row["defect_qty"] == 100 and row["defect_rate"] == 0.1   # 100/(900+100)
