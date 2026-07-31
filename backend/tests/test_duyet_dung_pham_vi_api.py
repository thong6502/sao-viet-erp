"""Duyệt phải ĐÚNG PHẠM VI — tăng ca + nghỉ phép + tạm ứng (chủ 29/07/2026).

Chủ báo: *"Tổ trưởng có thể duyệt tăng ca của tổ khác nếu biết mã phiếu."* Và chủ chốt chính sách:
*"Tạm ứng, YC cập nhật hồ sơ thì cho bên nhân sự duyệt; còn tăng ca với nghỉ phép thì để cho tổ
trưởng duyệt mà phạm vi trong tổ nó thôi."*

Mỗi luồng có **hai** test đi cặp, và cặp đó mới là điểm của file này:
  1. tổ KHÁC ⇒ chặn (403 / rơi vào `skipped`)
  2. tổ MÌNH ⇒ **vẫn duyệt được bình thường**

Vế 2 quan trọng không kém: vá quá tay làm tổ trưởng thật không duyệt nổi phiếu tổ mình thì còn
tệ hơn cái lỗ ban đầu.
"""
from __future__ import annotations

from datetime import date as _date

from app.db import SessionLocal
from app.repositories.rbac_repo import DepartmentRepository, RoleRepository
from app.repositories.user_repo import UserRepository
from app.security import create_access_token, hash_password
from tests.test_luong_api import _admin_token, _h


def _emp(client, token, *, name, dept):
    """Hồ sơ NV thuộc một phòng cụ thể."""
    db = SessionLocal()
    try:
        did = DepartmentRepository(db).get_by_name(dept).id
    finally:
        db.close()
    body = {"full_name": name, "department_id": did, "hire_date": "2020-01-01",
            "gender": "male", "status": "active"}
    r = client.post("/api/employees", json=body, headers=_h(token))
    assert r.status_code == 201, r.text
    return r.json()["employee"]["id"]


def _lead_token() -> str:
    """Tài khoản vai 'Tổ trưởng SX' — `tang_ca`/`nghi_phep` approve, scope `department`."""
    db = SessionLocal()
    try:
        users = UserRepository(db)
        co = users.get_by_username("to-truong-scope")
        if co is not None:
            return create_access_token(str(co.id))
        sx = DepartmentRepository(db).get_by_name("Sản xuất")
        role = RoleRepository(db).get_by_name_and_department("Tổ trưởng SX", sx.id)
        u = users.create(username="to-truong-scope", name="Tổ trưởng",
                         password_hash=hash_password("x"))
        users.set_assignment(u, department_id=sx.id, role_id=role.id, is_active=True)
        return create_access_token(str(u.id))
    finally:
        db.close()


def _ot_pending(eid: int, *, work_date="2026-08-10") -> int:
    """Phiếu tăng ca CHỜ DUYỆT cho NV bất kỳ — ghi thẳng repo, vì `/me` chỉ tạo cho chính mình."""
    from app.repositories.overtime_repo import OvertimeRepository
    db = SessionLocal()
    try:
        r = OvertimeRepository(db).create_request(
            employee_id=eid, work_date=_date.fromisoformat(work_date), from_minute=1080,
            to_minute=1200, reason="test", status="pending", created_by=None,
        )
        return r.id
    finally:
        db.close()


def _loai_nghi(client, token) -> int:
    """Một loại nghỉ để gắn đơn. Test DB không seed sẵn loại nào ⇒ tự tạo (idempotent)."""
    items = client.get("/api/leaves/types", headers=_h(token)).json()["items"]
    if items:
        return items[0]["id"]
    r = client.post("/api/leaves/types",
                    json={"name": "Phép năm", "is_paid": True, "annual_quota": 12},
                    headers=_h(token))
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _leave_pending(client, token, eid: int, *, start="2026-08-11") -> int:
    from app.repositories.leave_repo import LeaveRepository
    tid = _loai_nghi(client, token)
    db = SessionLocal()
    try:
        r = LeaveRepository(db).create_request(
            employee_id=eid, leave_type_id=tid,
            start_date=_date.fromisoformat(start), end_date=_date.fromisoformat(start),
            days=1, reason="test", status="pending", created_by=None,
        )
        return r.id
    finally:
        db.close()


# --- TĂNG CA ---------------------------------------------------------------

def test_tang_ca_to_truong_KHONG_duyet_duoc_to_khac(client):
    """⭐ Đúng lỗ chủ báo: biết mã phiếu là duyệt được phiếu tổ khác.

    Màn đã lọc nên tổ trưởng KHÔNG thấy phiếu này — che ở màn không phải là khoá."""
    token = _admin_token(client)
    kd = _emp(client, token, name="NV Kinh Doanh OT", dept="Kinh doanh")
    lead = _lead_token()
    rid = _ot_pending(kd)

    assert client.post(f"/api/overtime/{rid}/approve", json={"note": None},
                       headers=_h(lead)).status_code == 403
    assert client.post(f"/api/overtime/{rid}/reject", json={"note": "không"},
                       headers=_h(lead)).status_code == 403

    # Duyệt cả mẻ: phiếu ngoài tổ rơi vào `skipped`, KHÔNG bị duyệt lén.
    bulk = client.post("/api/overtime/bulk-approve", json={"ids": [rid]}, headers=_h(lead))
    assert bulk.status_code == 200 and bulk.json()["done"] == []
    assert bulk.json()["skipped"] == [rid]


def test_tang_ca_to_truong_VAN_duyet_duoc_to_minh(client):
    """⭐ Vế còn lại: vá xong mà tổ trưởng không duyệt nổi tổ mình là hỏng việc thật."""
    token = _admin_token(client)
    sx = _emp(client, token, name="Thợ Trong Tổ OT", dept="Sản xuất")
    lead = _lead_token()

    r = client.post(f"/api/overtime/{_ot_pending(sx, work_date='2026-08-12')}/approve",
                    json={"note": None}, headers=_h(lead))
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "approved"

    rid2 = _ot_pending(sx, work_date="2026-08-13")
    bulk = client.post("/api/overtime/bulk-approve", json={"ids": [rid2]}, headers=_h(lead))
    assert bulk.json()["done"] == [rid2], "duyệt cả mẻ trong tổ phải chạy trọn mẻ"


def test_tang_ca_HCNS_duyet_duoc_moi_to(client):
    """Duyệt tập trung không được vỡ: scope `all` vẫn duyệt được phiếu mọi tổ."""
    token = _admin_token(client)
    kd = _emp(client, token, name="NV KD Cho HCNS Duyet", dept="Kinh doanh")
    r = client.post(f"/api/overtime/{_ot_pending(kd, work_date='2026-08-14')}/approve",
                    json={"note": None}, headers=_h(token))
    assert r.status_code == 200 and r.json()["status"] == "approved"


# --- NGHỈ PHÉP -------------------------------------------------------------

def test_nghi_phep_to_truong_duyet_duoc_to_minh(client):
    """⭐ Quyền MỚI cấp 29/07/2026 — trước đó tổ trưởng chỉ tự xin nghỉ cho bản thân."""
    token = _admin_token(client)
    sx = _emp(client, token, name="Thợ Trong Tổ Nghỉ", dept="Sản xuất")
    lead = _lead_token()

    r = client.post(f"/api/leaves/{_leave_pending(client, token, sx)}/approve",
                    json={"note": None}, headers=_h(lead))
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "approved"


def test_nghi_phep_to_truong_KHONG_duyet_duoc_to_khac(client):
    token = _admin_token(client)
    kd = _emp(client, token, name="NV KD Nghỉ", dept="Kinh doanh")
    lead = _lead_token()
    rid = _leave_pending(client, token, kd, start="2026-08-15")

    assert client.post(f"/api/leaves/{rid}/approve", json={"note": None},
                       headers=_h(lead)).status_code == 403
    bulk = client.post("/api/leaves/bulk-approve", json={"ids": [rid]}, headers=_h(lead))
    assert bulk.json()["done"] == [] and bulk.json()["skipped"] == [rid]


def test_nghi_phep_to_truong_KHONG_sua_duoc_danh_muc_loai_nghi(client):
    """⭐ Cấp quyền duyệt mà lọt cả danh mục loại nghỉ là cấp NHẦM.

    Loại nghỉ là chính sách toàn công ty (có lương / quota năm) — phải giữ ở HCNS."""
    lead = _lead_token()
    assert client.post("/api/leaves/types", json={"name": "Nghỉ tự chế", "is_paid": True},
                       headers=_h(lead)).status_code == 403


def test_nghi_phep_HCNS_van_quan_duoc_danh_muc(client):
    """Đổi ô quyền của danh mục sang `update` không được làm HCNS mất quyền."""
    token = _admin_token(client)
    r = client.post("/api/leaves/types", json={"name": "Nghỉ việc riêng có lương", "is_paid": True},
                    headers=_h(token))
    assert r.status_code == 201, r.text
    tid = r.json()["id"]
    assert client.put(f"/api/leaves/types/{tid}",
                      json={"name": "Nghỉ việc riêng", "is_paid": True},
                      headers=_h(token)).status_code == 200


def test_nghi_phep_lich_nghi_loc_theo_pham_vi(client):
    """Lịch nghỉ gác bằng `approve` — tổ trưởng nay có cờ đó nên phải LỌC, không thì họ đọc được
    lịch nghỉ của cả công ty."""
    token = _admin_token(client)
    sx = _emp(client, token, name="Thợ SX Lịch", dept="Sản xuất")
    kd = _emp(client, token, name="NV KD Lịch", dept="Kinh doanh")
    client.post(f"/api/leaves/{_leave_pending(client, token, sx, start='2026-09-02')}/approve",
                json={"note": None}, headers=_h(token))
    client.post(f"/api/leaves/{_leave_pending(client, token, kd, start='2026-09-03')}/approve",
                json={"note": None}, headers=_h(token))

    ai = {e["employee_id"] for e in client.get(
        "/api/leaves/calendar?year=2026&month=9", headers=_h(_lead_token())).json()["employees"]}
    assert sx in ai, "tổ trưởng phải thấy người tổ mình"
    assert kd not in ai, "tổ trưởng KHÔNG được thấy người tổ khác"

    ai_hcns = {e["employee_id"] for e in client.get(
        "/api/leaves/calendar?year=2026&month=9", headers=_h(token)).json()["employees"]}
    assert {sx, kd} <= ai_hcns, "HCNS (scope all) vẫn thấy toàn công ty"


# --- TẠM ỨNG ---------------------------------------------------------------

def test_tam_ung_van_do_HCNS_duyet_binh_thuong(client):
    """Chủ chốt: tạm ứng do bên nhân sự duyệt. Chốt phạm vi thêm vào KHÔNG được cản HCNS."""
    token = _admin_token(client)
    eid = _emp(client, token, name="NV Xin Tạm Ứng", dept="Sản xuất")
    client.post(f"/api/luong/salaries/{eid}",
                json={"effective_from": "2026-01-01", "luong_vi_tri": 10_000_000},
                headers=_h(token))
    adv = client.post("/api/luong/advances",
                      json={"employee_id": eid, "period_year": 2026, "period_month": 8,
                            "advance_date": "2026-08-05", "amount": 2_000_000},
                      headers=_h(token))
    assert adv.status_code == 201, adv.text
    r = client.post(f"/api/luong/advances/{adv.json()['id']}/approve", json={"note": None},
                    headers=_h(token))
    assert r.status_code == 200 and r.json()["status"] == "approved"
