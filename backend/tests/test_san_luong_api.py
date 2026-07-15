"""Phiếu sản lượng công đoạn: ghi theo NGƯỜI → cộng thẳng vào cột `khoan` bảng lương khi tính lương
(không còn sổ khoán ở giữa). LSX bù mặc định không tính khoán; trừ lỗi do thợ."""
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


def _make_cd(client, token, ma, ghi="nguoi", pct=0, abs_=0):
    return client.post("/api/cong-doan", json={
        "ma": ma, "ten": f"In {ma}", "nhom": "print", "khoan_ghi_theo": ghi,
        "allowed_defect_pct": pct, "allowed_defect_abs": abs_,
        "che_do_tinh": "theo_san_luong", "pricing_basis": "per_other",
    }, headers=_h(token))


def _make_lsx(client, token, kind="thuong") -> int:
    return client.post("/api/san-xuat/orders", json={
        "product_name": "SP test", "quantity": 10000, "order_kind": kind,
    }, headers=_h(token)).json()["id"]


def test_output_flows_to_payroll(client):
    """Ghi phiếu SL theo người (tính khoán) → tiền vào cột khoan khi tính lương (không cần chốt sổ)."""
    token = _token(client)
    e = _make_emp(client, token, name="SL A")
    _make_cd(client, token, "IN-SLA", "nguoi")
    lsx = _make_lsx(client, token)
    r = client.post("/api/san-luong/outputs", json={
        "production_order_id": lsx, "cong_doan": "IN-SLA", "year": 2027, "month": 1,
        "group_name": "to_boi", "employee_id": e, "work_name": "In", "unit": "m2",
        "unit_price": 170, "quantity": 30000,
    }, headers=_h(token))
    assert r.status_code == 201 and r.json()["amount"] == 5100000 and r.json()["ghi_theo"] == "nguoi"

    gen = client.post("/api/luong/generate", json={"year": 2027, "month": 1}, headers=_h(token)).json()
    assert next(l for l in gen["lines"] if l["employee_id"] == e)["khoan"] == 5100000


def test_output_missing_employee_rejected(client):
    """Phiếu khoán bắt buộc có nhân viên (ghi theo người)."""
    token = _token(client)
    _make_cd(client, token, "IN-NOEMP", "nguoi")
    lsx = _make_lsx(client, token)
    r = client.post("/api/san-luong/outputs", json={
        "production_order_id": lsx, "cong_doan": "IN-NOEMP", "year": 2027, "month": 1,
        "group_name": "to_boi", "unit": "m2", "unit_price": 170, "quantity": 100,
    }, headers=_h(token))
    assert r.status_code == 400


def test_output_bu_lsx_default_no_khoan(client):
    """LSX bù → phiếu mặc định tinh_khoan=false → không cộng vào cột khoan."""
    token = _token(client)
    e = _make_emp(client, token, name="SL Bù")
    _make_cd(client, token, "IN-SLB", "nguoi")
    lsx = _make_lsx(client, token, kind="bu")
    r = client.post("/api/san-luong/outputs", json={
        "production_order_id": lsx, "cong_doan": "IN-SLB", "year": 2027, "month": 2,
        "group_name": "to_cat", "employee_id": e, "unit": "m2", "unit_price": 170, "quantity": 10000,
    }, headers=_h(token))
    assert r.status_code == 201 and r.json()["tinh_khoan"] is False

    gen = client.post("/api/luong/generate", json={"year": 2027, "month": 2}, headers=_h(token)).json()
    assert next(l for l in gen["lines"] if l["employee_id"] == e)["khoan"] == 0


def test_cong_doan_khong_khoan_rejected(client):
    """Công đoạn khai 'khong' → chặn ghi phiếu khoán."""
    token = _token(client)
    _make_cd(client, token, "IN-SLC", "khong")
    lsx = _make_lsx(client, token)
    r = client.post("/api/san-luong/outputs", json={
        "production_order_id": lsx, "cong_doan": "IN-SLC", "year": 2027, "month": 3,
        "group_name": "to_boi", "employee_id": 1, "unit": "m2", "unit_price": 170, "quantity": 100,
    }, headers=_h(token))
    assert r.status_code == 400


def test_defect_deduction_loi_tho_only(client):
    """Trừ lỗi: chỉ lỗi DO THỢ + vượt ngưỡng mới trừ; lỗi vật tư → không trừ. Net vào cột khoan."""
    token = _token(client)
    e = _make_emp(client, token, name="Thợ lỗi")
    _make_cd(client, token, "IN-DEF", "nguoi", pct=0.02, abs_=100)
    lsx = _make_lsx(client, token)
    # đạt 1000, hỏng 200, lỗi thợ; ngưỡng = max(1200×2%=24, 100)=100 → vượt 100 tờ × 170 = 17.000.
    r = client.post("/api/san-luong/outputs", json={
        "production_order_id": lsx, "cong_doan": "IN-DEF", "year": 2027, "month": 4,
        "group_name": "to_boi", "employee_id": e, "unit": "m2", "unit_price": 170, "quantity": 1000,
        "defect_qty": 200, "defect_cause": "loi_tho",
    }, headers=_h(token)).json()
    assert r["amount"] == 170000 and r["defect_deduction"] == 17000 and r["net_amount"] == 153000
    # Cùng số hỏng nhưng lỗi VẬT TƯ → không trừ.
    r2 = client.post("/api/san-luong/outputs", json={
        "production_order_id": lsx, "cong_doan": "IN-DEF", "year": 2027, "month": 4,
        "group_name": "to_cat", "employee_id": e, "unit": "m2", "unit_price": 170, "quantity": 1000,
        "defect_qty": 200, "defect_cause": "vat_tu",
    }, headers=_h(token)).json()
    assert r2["defect_deduction"] == 0 and r2["net_amount"] == 170000

    # Cột khoan = net 2 phiếu = 153.000 + 170.000.
    gen = client.post("/api/luong/generate", json={"year": 2027, "month": 4}, headers=_h(token)).json()
    assert next(l for l in gen["lines"] if l["employee_id"] == e)["khoan"] == 323000


def _nvsx_token(client) -> str:
    """Token NV sản xuất: role 'Nhân viên sản xuất' (san_luong = read/create/update, KHÔNG delete)."""
    from app.repositories.user_repo import UserRepository
    from app.repositories.rbac_repo import RoleRepository
    from app.security import create_access_token, hash_password
    db = SessionLocal()
    try:
        users = UserRepository(db)
        ex = users.get_by_username("nvsx-test")
        if ex is not None:
            return create_access_token(str(ex.id))
        dept = DepartmentRepository(db).get_by_name("Sản xuất")
        role = RoleRepository(db).get_by_name_and_department("Nhân viên sản xuất", dept.id)
        u = users.create(username="nvsx-test", name="SX", password_hash=hash_password("x"))
        users.set_assignment(u, department_id=dept.id, role_id=role.id, is_active=True)
        return create_access_token(str(u.id))
    finally:
        db.close()


def test_delete_output_requires_delete_permission(client):
    """Xóa phiếu SL cần quyền `delete` — NV sản xuất (update nhưng KHÔNG delete) bị chặn; admin xóa được."""
    token = _token(client)
    e = _make_emp(client, token, name="Xóa SL")
    _make_cd(client, token, "IN-DEL", "nguoi")
    lsx = _make_lsx(client, token)
    oid = client.post("/api/san-luong/outputs", json={
        "production_order_id": lsx, "cong_doan": "IN-DEL", "year": 2027, "month": 8,
        "group_name": "to_boi", "employee_id": e, "unit": "m2", "unit_price": 100, "quantity": 10,
    }, headers=_h(token)).json()["id"]
    nvsx = _nvsx_token(client)
    assert client.delete(f"/api/san-luong/outputs/{oid}", headers=_h(nvsx)).status_code == 403
    assert client.delete(f"/api/san-luong/outputs/{oid}", headers=_h(token)).status_code == 204


def test_defect_report(client):
    """Report tỉ lệ hỏng theo người."""
    token = _token(client)
    e = _make_emp(client, token, name="Báo hỏng")
    _make_cd(client, token, "IN-RPT", "nguoi")
    lsx = _make_lsx(client, token)
    client.post("/api/san-luong/outputs", json={
        "production_order_id": lsx, "cong_doan": "IN-RPT", "year": 2027, "month": 6,
        "group_name": "to_boi", "employee_id": e, "unit": "m2", "unit_price": 10, "quantity": 900,
        "defect_qty": 100, "defect_cause": "loi_tho",
    }, headers=_h(token))
    rep = client.get("/api/san-luong/defect-report?year=2027&month=6", headers=_h(token)).json()
    row = next(x for x in rep["items"] if x["employee_id"] == e)
    assert row["defect_qty"] == 100 and row["defect_rate"] == 0.1   # 100/(900+100)
