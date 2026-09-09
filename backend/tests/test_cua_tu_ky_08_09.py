"""Cửa "làm hộ / tự ký" — bản rà liên thông 5 phân hệ (08/09/2026), nhóm 2.

Chốt 07/09 "không tự duyệt phiếu của mình khi phạm vi chỉ là tổ" mới đặt ở nút Duyệt; đường
"tạo hộ / khai hộ" (= duyệt luôn), duyệt yêu cầu chỉnh công, duyệt tạm ứng, duyệt yêu cầu sửa hồ
sơ vẫn lọt. Mỗi chốt có vế đối chứng: cho NGƯỜI KHÁC trong tổ vẫn làm được, HCNS (toàn công ty)
vẫn là cấp duyệt cuối.
"""
from __future__ import annotations

from app.db import SessionLocal
from app.repositories.employee_repo import EmployeeRepository
from app.repositories.rbac_repo import DepartmentRepository, RoleRepository
from app.repositories.user_repo import UserRepository
from app.security import create_access_token, hash_password
from tests.test_duyet_dung_pham_vi_api import _emp, _lead_token
from tests.test_lo_quyen_tang_ca import _noi_ho_so, _uid
from tests.test_luong_api import _admin_token, _h

NGAY = "2026-08-10"


def _vai_rieng(username: str, dept: str, perms: dict) -> tuple[int, str]:
    """Tài khoản với vai TỰ DỰNG (phạm vi tổ) — `perms` = {module_key: {can_*, scope}}."""
    db = SessionLocal()
    try:
        users = UserRepository(db)
        u = users.get_by_username(username)
        if u is None:
            did = DepartmentRepository(db).get_by_name(dept).id
            role = RoleRepository(db).create(name=f"Vai {username}", department_id=did)
            for khoa, co in perms.items():
                RoleRepository(db).set_permission(role_id=role.id, module_key=khoa, **co)
            u = users.create(username=username, name=username, password_hash=hash_password("x"))
            users.set_assignment(u, department_id=did, role_id=role.id, is_active=True)
            db.commit()
        return u.id, create_access_token(str(u.id))
    finally:
        db.close()


def _ho_so_cua(client, admin, *, name, dept, uid) -> int:
    eid = _emp(client, admin, name=name, dept=dept)
    _noi_ho_so(client, admin, eid, uid)
    return eid


def _gan_ca(client, admin, eid: int) -> None:
    """Ca nền 8h tròn (08:00–16:00) từ ngày vào — yêu cầu chỉnh công đòi có ca hôm đó."""
    items = client.get("/api/attendance/shifts", headers=_h(admin)).json().get("items", [])
    sid = next((s["id"] for s in items if s["name"] == "HC 8-16 (tự ký)"), None)
    if sid is None:
        r = client.post("/api/attendance/shifts", json={"name": "HC 8-16 (tự ký)", "start_time": "08:00",
                                                        "end_time": "16:00"}, headers=_h(admin))
        assert r.status_code == 201, r.text
        sid = r.json()["id"]
    r = client.put(f"/api/employees/{eid}/shift", json={"default_shift_id": sid, "effective_from": "2020-01-01"},
                   headers=_h(admin))
    assert r.status_code == 200, r.text


# --- 1. Tăng ca: tạo hộ cho CHÍNH MÌNH -------------------------------------------------------


def test_to_truong_KHONG_tao_ho_tang_ca_cho_chinh_minh(client):
    admin = _admin_token(client)
    lead = _lead_token()
    me = _ho_so_cua(client, admin, name="Tổ trưởng SX", dept="Sản xuất", uid=_uid("to-truong-scope"))
    r = client.post("/api/overtime", json={"employee_id": me, "work_date": NGAY, "from_minute": 1080,
                                           "to_minute": 1200, "reason": "tự ký"}, headers=_h(lead))
    assert r.status_code == 403 and "chính mình" in r.json()["detail"], r.text
    # Đối chứng: cho thợ trong tổ vẫn ra phiếu đã duyệt; HCNS toàn công ty tạo cho ai cũng được.
    tho = _emp(client, admin, name="Thợ SX", dept="Sản xuất")
    r = client.post("/api/overtime", json={"employee_id": tho, "work_date": NGAY, "from_minute": 1080,
                                           "to_minute": 1200, "reason": "chạy đơn"}, headers=_h(lead))
    assert r.status_code == 201 and r.json()["status"] == "approved", r.text
    r = client.post("/api/overtime", json={"employee_id": me, "work_date": "2026-08-11", "from_minute": 1080,
                                           "to_minute": 1200, "reason": "HCNS tạo"}, headers=_h(admin))
    assert r.status_code == 201, r.text


# --- 2. Đi muộn / về sớm: khai hộ cho CHÍNH MÌNH ----------------------------------------------


def test_to_truong_KHONG_khai_ho_di_muon_cho_chinh_minh(client):
    admin = _admin_token(client)
    lead = _lead_token()
    me = _ho_so_cua(client, admin, name="Tổ trưởng SX", dept="Sản xuất", uid=_uid("to-truong-scope"))
    body = {"work_date": "2026-08-12", "from_minute": 480, "to_minute": 540, "reason": "tự miễn phạt"}
    r = client.post("/api/late-early", json={"employee_id": me, **body}, headers=_h(lead))
    assert r.status_code == 403 and "chính mình" in r.json()["detail"], r.text
    tho = _emp(client, admin, name="Thợ SX", dept="Sản xuất")
    r = client.post("/api/late-early", json={"employee_id": tho, **body}, headers=_h(lead))
    assert r.status_code == 201, r.text


# --- 3. Yêu cầu chỉnh công: tự duyệt ------------------------------------------------------------


def test_KHONG_tu_duyet_yeu_cau_chinh_cong_cua_minh(client):
    admin = _admin_token(client)
    uid, tok = _vai_rieng("duyet-chinh-cong-to", "Sản xuất", {
        "cham_cong": dict(can_read=True, can_create=True, can_approve=True, scope="department"),
    })
    me = _ho_so_cua(client, admin, name="Trưởng tổ duyệt công", dept="Sản xuất", uid=uid)
    _gan_ca(client, admin, me)
    r = client.post("/api/attendance/me/adjust-request",
                    json={"date": "2026-09-01", "check_type": "in", "suggested_time": "08:00",
                          "reason": "quên bấm"}, headers=_h(tok))
    assert r.status_code == 200, r.text
    rid = r.json()["id"]
    r = client.post(f"/api/attendance/adjust-requests/{rid}/approve", json={}, headers=_h(tok))
    assert r.status_code == 403 and "chính mình" in r.json()["detail"], r.text
    # HCNS (toàn công ty) duyệt được.
    assert client.post(f"/api/attendance/adjust-requests/{rid}/approve", json={},
                       headers=_h(admin)).status_code == 200


# --- 4. Tạm ứng + yêu cầu sửa hồ sơ: tự duyệt -------------------------------------------------


def test_KHONG_tu_duyet_tam_ung_va_yeu_cau_ho_so_cua_minh(client):
    admin = _admin_token(client)
    uid, tok = _vai_rieng("duyet-tam-ung-to", "Sản xuất", {
        "luong": dict(can_read=True, can_create=True, can_approve=True, scope="department"),
        "nhan_su": dict(can_read=True, can_update=True, can_approve=True, scope="department"),
    })
    me = _ho_so_cua(client, admin, name="Trưởng tổ duyệt ứng", dept="Sản xuất", uid=uid)
    r = client.post("/api/luong/advances/me", json={"period_year": 2026, "period_month": 9,
                    "advance_date": "2026-09-05", "amount": 5_000_000, "reason": "p"}, headers=_h(tok))
    assert r.status_code == 201, r.text
    aid = r.json()["id"]
    r = client.post(f"/api/luong/advances/{aid}/approve", json={}, headers=_h(tok))
    assert r.status_code == 403 and "chính mình" in r.json()["detail"], r.text
    assert client.post(f"/api/luong/advances/{aid}/approve", json={}, headers=_h(admin)).status_code == 200

    r = client.post("/api/employees/me/update-requests",
                    json={"changes": {"bank_account": "0999888777"}, "reason": "đổi thẻ"}, headers=_h(tok))
    assert r.status_code in (200, 201), r.text
    qid = r.json()["id"]
    r = client.post(f"/api/employees/update-requests/{qid}/approve", json={}, headers=_h(tok))
    assert r.status_code == 403 and "chính mình" in r.json()["detail"], r.text
    assert client.post(f"/api/employees/update-requests/{qid}/approve", json={},
                       headers=_h(admin)).status_code == 200
    # Đối chứng: duyệt tạm ứng của THỢ trong tổ vẫn được.
    tho = _emp(client, admin, name="Thợ SX", dept="Sản xuất")
    r = client.post("/api/luong/advances", json={"employee_id": tho, "period_year": 2026, "period_month": 9,
                    "advance_date": "2026-09-05", "amount": 1_000_000}, headers=_h(admin))
    assert r.status_code == 201, r.text
    assert client.post(f"/api/luong/advances/{r.json()['id']}/approve", json={},
                       headers=_h(tok)).status_code == 200


# --- 5. Đi muộn PUT/cancel phải có ô quyền; /leaves/me chỉ cần đăng nhập -----------------------


def test_di_muon_sua_huy_can_o_quyen_va_leaves_me_khong_can_o(client):
    admin = _admin_token(client)
    uid0, tok0 = _vai_rieng("khong-o-nao", "Sản xuất", {})
    me = _ho_so_cua(client, admin, name="NV không ô", dept="Sản xuất", uid=uid0)
    # HCNS khai hộ một phiếu cho người này rồi người này (không ô nào) đòi sửa/huỷ.
    r = client.post("/api/late-early", json={"employee_id": me, "work_date": "2026-09-02",
                    "from_minute": 480, "to_minute": 600, "reason": "x"}, headers=_h(admin))
    assert r.status_code == 201, r.text
    le = r.json()["id"]
    r = client.put(f"/api/late-early/{le}", json={"work_date": "2026-09-02", "from_minute": 480,
                                                  "to_minute": 540, "reason": "sửa"}, headers=_h(tok0))
    assert r.status_code == 403, r.text
    assert client.post(f"/api/late-early/{le}/cancel", headers=_h(tok0)).status_code == 403
    # /leaves/me: vai không có ô Nghỉ phép vẫn xem được đơn/quota của mình.
    r = client.get("/api/leaves/me", headers=_h(tok0))
    assert r.status_code == 200 and r.json()["has_employee"] is True, r.text
