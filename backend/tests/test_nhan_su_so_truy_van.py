"""Hồ sơ nhân sự: số truy vấn KHÔNG chạy theo số dòng + các đường đọc gộp (rà 14/09/2026).

Đo thật lúc rà trên DB dev: GET /api/employees bắn ~71 câu SQL cho một trang (tên phòng, tên tài
khoản, tên vai trò tra từng người; KPI kéo cả bảng về Python), hàng đợi đề nghị + Quá trình công
tác + Nhật ký tra tên người thao tác từng dòng. Nay gộp thành truy vấn IN / GROUP BY — bài này khoá
bằng SỐ ĐO để lần dọn dẹp sau không lặng lẽ đẻ lại N+1.
"""
from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy import event

from app.db import SessionLocal, engine
from app.models.audit import AuditLog
from app.models.employee import Employee
from app.repositories.user_repo import UserRepository

from .test_employees_api import _admin_token, _create, _dept_id, _h, _ns_no_salary_token

_dot = iter(range(1, 100))


def _dem_truy_van(fn):
    dem = {"n": 0}

    def _ghi(conn, cursor, statement, parameters, context, executemany):
        dem["n"] += 1

    event.listen(engine, "before_cursor_execute", _ghi)
    try:
        kq = fn()
    finally:
        event.remove(engine, "before_cursor_execute", _ghi)
    return kq, dem["n"]


def _dung_ho_so(n: int, actor_id: int) -> list[int]:
    """`n` hồ sơ, mỗi hồ sơ một tài khoản riêng + 2 dòng nhật ký do `n` người khác nhau ghi.

    Ghi thẳng ORM: bài đo TẢI, dựng qua API (băm mật khẩu từng tài khoản) chỉ tốn thời gian."""
    d = next(_dot)
    db = SessionLocal()
    try:
        users = UserRepository(db)
        dept = _dept_id("Hành chính nhân sự")
        ids = []
        for i in range(n):
            u = users.create(username=f"stq{d}_{i}", name=f"STQ {d}-{i}", password_hash="x")
            e = Employee(code=f"STQ{d}-{i}", full_name=f"STQ {d}-{i}", department_id=dept,
                         user_id=u.id, hire_date=date(2024, 1, 1),
                         probation_end_date=date(2025, 12, 31))
            db.add(e)
            db.flush()
            ids.append(e.id)
            for _ in range(2):
                db.add(AuditLog(actor_user_id=u.id, action="employee.update",
                                target=f"employee:{e.id}", detail="x"))
            db.add(AuditLog(actor_user_id=actor_id, action="employee.update",
                            target=f"employee:{ids[0]}", detail="x"))
            db.add(AuditLog(actor_user_id=u.id, action="employee.update",
                            target=f"employee:{ids[0]}", detail="x"))
        db.commit()
        return ids
    finally:
        db.close()


def _admin_id() -> int:
    db = SessionLocal()
    try:
        return UserRepository(db).get_by_username("admin").id
    finally:
        db.close()


def test_danh_sach_va_nhat_ky_khong_n_cong_1(client):
    token = _admin_token(client)
    admin_id = _admin_id()

    def _do():
        a = client.get("/api/employees?size=200", headers=_h(token))
        assert a.status_code == 200
        return a.json()

    ids_nho = _dung_ho_so(3, admin_id)
    _, it = _dem_truy_van(_do)
    _, it_nhat_ky = _dem_truy_van(
        lambda: client.get(f"/api/employees/{ids_nho[0]}/activity", headers=_h(token)))

    ids_lon = _dung_ho_so(12, admin_id)
    data, nhieu = _dem_truy_van(_do)
    r, nhieu_nhat_ky = _dem_truy_van(
        lambda: client.get(f"/api/employees/{ids_lon[0]}/activity", headers=_h(token)))

    assert nhieu == it, f"danh sách: {it} câu với ít dòng, {nhieu} câu khi thêm 9 hồ sơ"
    assert nhieu_nhat_ky == it_nhat_ky
    # Tên tài khoản vẫn đủ sau khi gộp truy vấn.
    by_id = {row["id"]: row for row in data["items"]}
    assert by_id[ids_lon[0]]["account_username"].startswith("stq")
    names = {row["actor_name"] for row in r.json()["items"]}
    assert len(names) == 13  # 12 người + admin


def test_loc_sap_het_thu_viec_o_may_chu_khop_kpi(client):
    token = _admin_token(client)
    soon = (date.today() + timedelta(days=10)).isoformat()
    later = (date.today() + timedelta(days=90)).isoformat()
    a = _create(client, token, full_name="Sắp hết TV", probation_end_date=soon).json()["employee"]["id"]
    b = _create(client, token, full_name="Còn lâu", probation_end_date=later).json()["employee"]["id"]

    data = client.get("/api/employees?ending_soon=true&size=200", headers=_h(token)).json()
    ids = {row["id"] for row in data["items"]}
    assert a in ids and b not in ids
    assert data["total"] == data["kpis"]["probation_ending_soon"]


def test_chi_tiet_tra_ca_nen_dang_hieu_luc(client):
    token = _admin_token(client)
    eid = _create(client, token, full_name="Có ca").json()["employee"]["id"]
    s1 = client.post("/api/attendance/shifts", headers=_h(token),
                     json={"name": "Ca STQ sáng", "start_time": "06:00", "end_time": "14:00"}).json()
    s2 = client.post("/api/attendance/shifts", headers=_h(token),
                     json={"name": "Ca STQ chiều", "start_time": "14:00", "end_time": "22:00"}).json()
    hom_qua = (date.today() - timedelta(days=1)).isoformat()
    tuan_sau = (date.today() + timedelta(days=7)).isoformat()
    assert client.put(f"/api/employees/{eid}/shift", headers=_h(token),
                      json={"default_shift_id": s1["id"], "effective_from": hom_qua}).status_code == 200
    # Mốc TƯƠNG LAI không được thắng mốc đang hiệu lực hôm nay.
    assert client.put(f"/api/employees/{eid}/shift", headers=_h(token),
                      json={"default_shift_id": s2["id"], "effective_from": tuan_sau}).status_code == 200

    got = client.get(f"/api/employees/{eid}", headers=_h(token)).json()
    assert got["current_shift_id"] == s1["id"]
    assert got["current_shift_name"] == "Ca STQ sáng"


def test_response_ghi_cung_che_truong_luong(client):
    """Người không có `view_salary` sửa hồ sơ: response PUT không được lộ số tài khoản mà GET
    đã che."""
    admin = _admin_token(client)
    tok = _ns_no_salary_token()
    eid = _create(client, admin, full_name="Che lương").json()["employee"]["id"]
    assert client.put(f"/api/employees/{eid}", headers=_h(admin),
                      json={"full_name": "Che lương", "bank_account": "111",
                            "probation_end_date": "2025-12-31"}).status_code == 200

    upd = client.put(f"/api/employees/{eid}", headers=_h(tok),
                     json={"full_name": "Che lương", "phone": "0911",
                           "probation_end_date": "2025-12-31"})
    assert upd.status_code == 200
    assert upd.json()["employee"]["phone"] == "0911"
    assert upd.json()["employee"]["bank_account"] is None
    assert client.get(f"/api/employees/{eid}", headers=_h(tok)).json()["bank_account"] is None


def test_rbac_doc_mot_tai_khoan(client):
    token = _admin_token(client)
    uid = _admin_id()
    r = client.get(f"/api/users/{uid}", headers=_h(token))
    assert r.status_code == 200
    assert r.json()["username"] == "admin"
    assert r.json()["role_name"]
    assert client.get("/api/users/999999", headers=_h(token)).status_code == 404
    assert client.get(f"/api/users/{uid}/activity?limit=1",
                      headers=_h(token)).status_code == 200
