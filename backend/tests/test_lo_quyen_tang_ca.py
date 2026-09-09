"""LỖ QUYỀN tăng ca / nghỉ phép vá đợt 1 (07/09/2026 — mục 1.7).

  1. Tạo hộ (`POST /api/overtime`) phải đúng PHẠM VI — trước đó tổ trưởng tổ A gõ mã NV tổ B là
     có ngay phiếu ĐÃ DUYỆT cho người tổ khác.
  2. Hủy hộ cũng phải đúng phạm vi — trước đó hủy được phiếu đã duyệt của tổ khác chỉ cần biết mã.
  3. `PUT /{id}` và `POST /{id}/cancel` phải có ô quyền (create hoặc approve) — trước đó chỉ cần đăng nhập.
  4. `/tran-thang` chỉ cho xem người trong phạm vi — docstring nói vậy mà handler nhận mọi id.
  5. Tổ trưởng KHÔNG tự duyệt phiếu tăng ca / đơn nghỉ của chính mình (phạm vi tổ). HCNS/GĐ phạm vi
     toàn công ty vẫn được (cấp duyệt cuối).

Mỗi chốt có vế đối chứng "tổ MÌNH vẫn làm được" — vá quá tay làm tổ trưởng thật kẹt thì tệ hơn lỗ.
"""
from __future__ import annotations

from app.db import SessionLocal
from app.repositories.employee_repo import EmployeeRepository
from app.repositories.overtime_repo import OvertimeRepository
from app.repositories.rbac_repo import DepartmentRepository, RoleRepository
from app.repositories.user_repo import UserRepository
from app.security import create_access_token, hash_password
from tests.test_duyet_dung_pham_vi_api import _emp, _lead_token, _leave_pending, _ot_pending
from tests.test_luong_api import _admin_token, _h

NGAY = "2026-08-10"


def _phieu_duyet(client, token, eid: int, *, work_date=NGAY, expect=201):
    r = client.post("/api/overtime",
                    json={"employee_id": eid, "work_date": work_date, "from_minute": 1080,
                          "to_minute": 1200, "reason": "chạy đơn"}, headers=_h(token))
    assert r.status_code == expect, r.text
    return r.json() if r.status_code < 400 else None


def _uid(username: str) -> int:
    db = SessionLocal()
    try:
        return UserRepository(db).get_by_username(username).id
    finally:
        db.close()


def _noi_ho_so(client, token, eid: int, uid: int) -> None:
    r = client.post(f"/api/employees/{eid}/account", json={"user_id": uid}, headers=_h(token))
    assert r.status_code in (200, 201), r.text


def _nv_thuong_token(client, admin, *, name="NV thường", dept="Kinh doanh") -> tuple[str, int]:
    """Tài khoản vai 'NV Sales' — KHÔNG có ô `tang_ca` nào, đã nối hồ sơ NV. Trả (token, employee_id)."""
    eid = _emp(client, admin, name=name, dept=dept)
    db = SessionLocal()
    try:
        users = UserRepository(db)
        u = users.get_by_username("nv-thuong-lo") or None
        if u is None:
            kd = DepartmentRepository(db).get_by_name(dept)
            role = RoleRepository(db).get_by_name_and_department("NV Sales", kd.id)
            u = users.create(username="nv-thuong-lo", name=name, password_hash=hash_password("x"))
            users.set_assignment(u, department_id=kd.id, role_id=role.id, is_active=True)
        emps = EmployeeRepository(db)
        emps.update(emps.get_by_id(eid), user_id=u.id)
        return create_access_token(str(u.id)), eid
    finally:
        db.close()


# --- 1. tạo hộ đúng phạm vi ---------------------------------------------------


def test_to_truong_KHONG_tao_ho_duoc_cho_to_khac(client):
    admin = _admin_token(client)
    kd = _emp(client, admin, name="KD ngoài tổ", dept="Kinh doanh")
    lead = _lead_token()
    _phieu_duyet(client, lead, kd, expect=403)


def test_to_truong_VAN_tao_ho_duoc_cho_to_minh(client):
    admin = _admin_token(client)
    sx = _emp(client, admin, name="Thợ SX", dept="Sản xuất")
    lead = _lead_token()
    r = _phieu_duyet(client, lead, sx)
    assert r["status"] == "approved"


# --- 2. hủy hộ đúng phạm vi -----------------------------------------------------


def test_to_truong_KHONG_huy_duoc_phieu_to_khac(client):
    admin = _admin_token(client)
    kd = _emp(client, admin, name="KD ngoài tổ", dept="Kinh doanh")
    rid = _phieu_duyet(client, admin, kd)["id"]
    lead = _lead_token()
    r = client.post(f"/api/overtime/{rid}/cancel", headers=_h(lead))
    assert r.status_code == 403, r.text
    assert client.get("/api/overtime?status=approved", headers=_h(admin)).json()["items"]


def test_to_truong_VAN_huy_duoc_phieu_to_minh(client):
    admin = _admin_token(client)
    sx = _emp(client, admin, name="Thợ SX", dept="Sản xuất")
    rid = _phieu_duyet(client, admin, sx)["id"]
    lead = _lead_token()
    r = client.post(f"/api/overtime/{rid}/cancel", headers=_h(lead))
    assert r.status_code == 200 and r.json()["status"] == "cancelled"


# --- 3. PUT / cancel phải có ô quyền ---------------------------------------------


def test_khong_o_quyen_thi_khong_sua_khong_huy_duoc(client):
    admin = _admin_token(client)
    tok, eid = _nv_thuong_token(client, admin)
    rid = _ot_pending(eid)
    r = client.put(f"/api/overtime/{rid}",
                   json={"work_date": NGAY, "from_minute": 1080, "to_minute": 1140, "reason": "x"},
                   headers=_h(tok))
    assert r.status_code == 403
    assert client.post(f"/api/overtime/{rid}/cancel", headers=_h(tok)).status_code == 403


# --- 4. tran-thang trong phạm vi -------------------------------------------------


def test_tran_thang_khong_xem_duoc_nguoi_ngoai_pham_vi(client):
    admin = _admin_token(client)
    tok, eid = _nv_thuong_token(client, admin)
    khac = _emp(client, admin, name="Người khác", dept="Sản xuất")
    q = {"year": 2026, "month": 8}
    assert client.get("/api/overtime/tran-thang", params=q, headers=_h(tok)).status_code == 200
    assert client.get("/api/overtime/tran-thang", params={**q, "employee_id": eid},
                      headers=_h(tok)).status_code == 200
    assert client.get("/api/overtime/tran-thang", params={**q, "employee_id": khac},
                      headers=_h(tok)).status_code == 403
    # HCNS/Admin (phạm vi toàn công ty) xem được ai cũng được; tổ trưởng xem tổ mình được.
    assert client.get("/api/overtime/tran-thang", params={**q, "employee_id": khac},
                      headers=_h(admin)).status_code == 200
    assert client.get("/api/overtime/tran-thang", params={**q, "employee_id": khac},
                      headers=_h(_lead_token())).status_code == 200
    assert client.get("/api/overtime/tran-thang", params={**q, "employee_id": eid},
                      headers=_h(_lead_token())).status_code == 403


# --- 5. không tự duyệt phiếu/đơn của mình ---------------------------------------


def test_to_truong_KHONG_tu_duyet_phieu_tang_ca_cua_minh(client):
    admin = _admin_token(client)
    lead = _lead_token()
    me = _emp(client, admin, name="Chính tổ trưởng", dept="Sản xuất")
    _noi_ho_so(client, admin, me, _uid("to-truong-scope"))
    rid = _ot_pending(me)
    r = client.post(f"/api/overtime/{rid}/approve", json={}, headers=_h(lead))
    assert r.status_code == 403 and "chính mình" in r.json()["detail"]
    # Hàng loạt: rơi vào skipped, không vỡ mẻ.
    b = client.post("/api/overtime/bulk-approve", json={"ids": [rid]}, headers=_h(lead)).json()
    assert b["done"] == [] and b["skipped"] == [rid]
    # HCNS/Admin (toàn công ty) duyệt được.
    assert client.post(f"/api/overtime/{rid}/approve", json={}, headers=_h(admin)).status_code == 200


def test_to_truong_KHONG_tu_duyet_don_nghi_cua_minh(client):
    admin = _admin_token(client)
    lead = _lead_token()
    me = _emp(client, admin, name="Chính tổ trưởng", dept="Sản xuất")
    _noi_ho_so(client, admin, me, _uid("to-truong-scope"))
    rid = _leave_pending(client, admin, me)
    r = client.post(f"/api/leaves/{rid}/approve", json={}, headers=_h(lead))
    assert r.status_code == 403 and "chính mình" in r.json()["detail"]
    assert client.post(f"/api/leaves/{rid}/approve", json={}, headers=_h(admin)).status_code == 200


def test_to_truong_VAN_duyet_duoc_nguoi_khac_trong_to(client):
    admin = _admin_token(client)
    lead = _lead_token()
    tho = _emp(client, admin, name="Thợ trong tổ", dept="Sản xuất")
    rid = _ot_pending(tho)
    assert client.post(f"/api/overtime/{rid}/approve", json={}, headers=_h(lead)).status_code == 200
    lid = _leave_pending(client, admin, tho)
    assert client.post(f"/api/leaves/{lid}/approve", json={}, headers=_h(lead)).status_code == 200
