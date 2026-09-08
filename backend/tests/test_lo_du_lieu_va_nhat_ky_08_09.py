"""Bước 9 bản rà liên thông (08/09/2026): E4 trạng thái kỳ không lộ toàn công ty cho vai "của tôi",
E10 hàng đợi yêu cầu sửa hồ sơ che STK/CCCD khi thiếu `view_salary`, E7 từ chối/huỷ yêu cầu chỉnh công
có nhật ký, C5b hạn mức phép tách phần đang chờ.
"""
from __future__ import annotations

from app.db import SessionLocal
from app.repositories.audit_repo import AuditLogRepository
from tests.test_cua_tu_ky_08_09 import _gan_ca, _ho_so_cua, _vai_rieng
from tests.test_duyet_dung_pham_vi_api import _emp
from tests.test_luong_api import _admin_token, _h
from tests.test_ra_soat_nhan_su_luong_07_09 import NAM


def test_E4_vai_cua_toi_khong_thay_danh_sach_tang_ca_ca_xuong(client):
    admin = _admin_token(client)
    uid, tok = _vai_rieng("tho-period", "Sản xuất", {"cham_cong": dict(can_read=True, scope="own")})
    _ho_so_cua(client, admin, name="Thợ xem kỳ", dept="Sản xuất", uid=uid)
    kd = _emp(client, admin, name="NV KD", dept="Kinh doanh")
    _gan_ca(client, admin, kd)
    # Phiếu TC đã duyệt ngày đã qua, không bấm ⇒ `ot_thieu_cap_list` có tên người phòng khác.
    r = client.post("/api/overtime", json={"employee_id": kd, "work_date": f"{NAM}-08-10", "from_minute": 1080,
                    "to_minute": 1200, "reason": "x"}, headers=_h(admin))
    assert r.status_code == 201, r.text
    full = client.get(f"/api/attendance/period?year={NAM}&month=8", headers=_h(admin)).json()
    assert full["employee_count"] >= 1 and full["ot_thieu_cap_list"], full
    own = client.get(f"/api/attendance/period?year={NAM}&month=8", headers=_h(tok)).json()
    assert own["status"] == full["status"]
    assert own["employee_count"] == 0 and own["hanging_days"] == 0 and own["ot_thieu_cap_list"] == [], own


def test_E10_hang_doi_yeu_cau_che_so_tai_khoan_khi_thieu_view_salary(client):
    admin = _admin_token(client)
    uid_tho, tok_tho = _vai_rieng("tho-yc", "Sản xuất", {"nhan_su": dict(can_read=True, scope="own")})
    tho = _ho_so_cua(client, admin, name="Thợ đổi thẻ", dept="Sản xuất", uid=uid_tho)
    r = client.post("/api/employees/me/update-requests",
                    json={"changes": {"bank_account": "0999888777"}, "reason": "đổi thẻ"}, headers=_h(tok_tho))
    assert r.status_code in (200, 201), r.text
    _, tok_doc = _vai_rieng("doc-yc", "Sản xuất", {"nhan_su": dict(can_read=True, scope="department")})
    items = client.get("/api/employees/update-requests", headers=_h(tok_doc)).json()["items"]
    yc = next(i for i in items if i["employee_id"] == tho)
    assert yc["changes"]["bank_account"] == "••••", yc
    # HCNS (view_salary) thấy số thật.
    items = client.get("/api/employees/update-requests", headers=_h(admin)).json()["items"]
    assert next(i for i in items if i["employee_id"] == tho)["changes"]["bank_account"] == "0999888777"


def test_E7_tu_choi_va_huy_yeu_cau_chinh_cong_co_nhat_ky(client):
    admin = _admin_token(client)
    uid, tok = _vai_rieng("nv-yc-cong", "Sản xuất", {"cham_cong": dict(can_read=True, can_create=True, scope="own")})
    e = _ho_so_cua(client, admin, name="NV quên bấm", dept="Sản xuất", uid=uid)
    _gan_ca(client, admin, e)
    r1 = client.post("/api/attendance/me/adjust-request", json={"date": f"{NAM}-09-01", "check_type": "in",
                     "suggested_time": "08:00", "reason": "quên"}, headers=_h(tok))
    r2 = client.post("/api/attendance/me/adjust-request", json={"date": f"{NAM}-09-02", "check_type": "out",
                     "suggested_time": "16:00", "reason": "quên"}, headers=_h(tok))
    assert r1.status_code == 200 and r2.status_code == 200, (r1.text, r2.text)
    assert client.post(f"/api/attendance/adjust-requests/{r1.json()['id']}/reject", json={"note": "không đủ căn cứ"},
                       headers=_h(admin)).status_code == 200
    assert client.post(f"/api/attendance/me/adjust-requests/{r2.json()['id']}/cancel", headers=_h(tok)).status_code == 200
    db = SessionLocal()
    try:
        assert AuditLogRepository(db).list_by_action("reject_attendance_adjust_request")
        assert AuditLogRepository(db).list_by_action("cancel_attendance_adjust_request")
    finally:
        db.close()


def test_C5b_han_muc_phep_tach_dang_cho(client):
    admin = _admin_token(client)
    uid, tok = _vai_rieng("nv-quota", "Sản xuất", {"nghi_phep": dict(can_read=True, can_create=True, scope="own")})
    _ho_so_cua(client, admin, name="NV phép", dept="Sản xuất", uid=uid)
    lt = client.get("/api/leaves/types", headers=_h(admin)).json()["items"]
    tid = (next((t["id"] for t in lt if t["annual_quota"] > 0), None)
           or client.post("/api/leaves/types", json={"name": "Phép năm", "is_paid": True, "annual_quota": 12},
                          headers=_h(admin)).json()["id"])
    a = client.post("/api/leaves", json={"leave_type_id": tid, "start_date": f"{NAM}-09-14", "end_date": f"{NAM}-09-14"},
                    headers=_h(tok))
    b = client.post("/api/leaves", json={"leave_type_id": tid, "start_date": f"{NAM}-09-15", "end_date": f"{NAM}-09-15"},
                    headers=_h(tok))
    assert a.status_code == 201 and b.status_code == 201, (a.text, b.text)
    assert client.post(f"/api/leaves/{a.json()['id']}/approve", json={}, headers=_h(admin)).status_code == 200
    q = next(x for x in client.get("/api/leaves/me", headers=_h(tok)).json()["quotas"] if x["leave_type_id"] == tid)
    assert q["used"] == 2 and q["pending"] == 1, q
