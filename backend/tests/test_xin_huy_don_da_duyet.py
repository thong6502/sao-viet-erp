"""XIN HỦY đơn nghỉ phép / phiếu tăng ca ĐÃ DUYỆT (chủ chốt 23/09/2026).

Chủ: *"tôi gửi phiếu tăng ca với đơn nghỉ phép đã xong và đã được duyệt, vậy mà tôi được phép hủy…
nó sẽ bị xáo trộn hết các kế hoạch của công ty"*. Chốt 4 điểm: (1) đã duyệt ⇒ chỉ được XIN hủy;
(2) ai có quyền duyệt phiếu thì duyệt xin hủy; (3) không hạn chót; (4) nghỉ phép và tăng ca y hệt.
Thêm: nghỉ nhiều ngày đang dở ⇒ "tính nghỉ 1 ngày" (rút ngắn, giữ các ngày trước ngày xin hủy);
phiếu tăng ca đã chấm VÀO tăng ca ⇒ chặn luôn.

Ngày thử tính theo HÔM NAY thật (luật có "ngày đã qua"), luôn chọn ngày làm việc trong tương lai.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from app.db import SessionLocal
from app.repositories.attendance_repo import AttendanceRepository
from app.repositories.audit_repo import AuditLogRepository
from app.repositories.employee_repo import EmployeeRepository
from app.repositories.leave_repo import LeaveRepository
from app.repositories.rbac_repo import DepartmentRepository, RoleRepository
from app.repositories.user_repo import UserRepository
from app.repositories.yeu_cau_huy_repo import YeuCauHuyRepository
from app.security import create_access_token, hash_password
from app.services.leave_service import LeaveService, hom_nay_vn
from tests.test_duyet_dung_pham_vi_api import _emp, _lead_token
from tests.test_luong_api import _admin_token, _h

VN = timezone(timedelta(hours=7))


def _thu_hai_toi(sau_ngay: int = 14) -> date:
    """Thứ Hai đầu tiên cách hôm nay ít nhất `sau_ngay` ngày — luôn là tương lai, luôn ngày làm."""
    d = hom_nay_vn() + timedelta(days=sau_ngay)
    return d + timedelta(days=(7 - d.weekday()) % 7)


def _tho(client, admin, *, ten="Thợ xin hủy") -> tuple[str, int]:
    """Tài khoản THỢ ở tổ Sản xuất: gửi / hủy đơn nghỉ + phiếu tăng ca của mình, KHÔNG có ô duyệt.
    Tổ trưởng SX (`_lead_token`) cùng tổ ⇒ là người duyệt. Trả (token, employee_id)."""
    eid = _emp(client, admin, name=ten, dept="Sản xuất")
    db = SessionLocal()
    try:
        sx = DepartmentRepository(db).get_by_name("Sản xuất")
        roles = RoleRepository(db)
        role = roles.get_by_name_and_department("Thợ xin hủy", sx.id) or roles.create(
            name="Thợ xin hủy", department_id=sx.id)
        roles.set_permission(role_id=role.id, module_key="nghi_phep", can_read=True,
                             can_create=True, can_cancel=True, scope="own")
        roles.set_permission(role_id=role.id, module_key="tang_ca", can_read=True,
                             can_create=True, scope="own")
        users = UserRepository(db)
        ten_dn = f"tho-xin-huy-{eid}"
        u = users.create(username=ten_dn, name=ten, password_hash=hash_password("x"))
        users.set_assignment(u, department_id=sx.id, role_id=role.id, is_active=True)
        emps = EmployeeRepository(db)
        emps.update(emps.get_by_id(eid), user_id=u.id)
        return create_access_token(str(u.id)), eid
    finally:
        db.close()


def _loai_khong_luong(client, admin) -> int:
    # KHÔNG lương: tổ Sản xuất có thể đang ăn khoán ⇒ loại có lương bị chặn (15/09/2026).
    r = client.post("/api/leaves/types", json={"name": "Việc riêng KL", "is_paid": False,
                                               "annual_quota": 0}, headers=_h(admin))
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _don_da_duyet(client, tho, lead, loai, tu: date, den: date) -> int:
    r = client.post("/api/leaves", json={"leave_type_id": loai, "start_date": tu.isoformat(),
                                         "end_date": den.isoformat(), "reason": "việc nhà"},
                    headers=_h(tho))
    assert r.status_code == 201, r.text
    rid = r.json()["id"]
    ap = client.post(f"/api/leaves/{rid}/approve", json={}, headers=_h(lead))
    assert ap.status_code == 200, ap.text
    return rid


def _cho_duyet(client, lead, goc="/api/leaves") -> int:
    return client.get(f"{goc}/summary", headers=_h(lead)).json()["pending_in_scope"]


# --- nghỉ phép ------------------------------------------------------------------------------------


def test_NGHI_PHEP_da_duyet_chi_duoc_XIN_huy_nguoi_duyet_quyet(client):
    """⭐ Thợ không hủy thẳng được đơn đã duyệt; xin hủy → đơn VẪN hiệu lực, badge người duyệt +1;
    giữ nguyên phải có lý do; xin lại → đồng ý → đơn hủy."""
    admin = _admin_token(client)
    tho, _ = _tho(client, admin)
    lead = _lead_token()
    loai = _loai_khong_luong(client, admin)
    t2 = _thu_hai_toi()
    rid = _don_da_duyet(client, tho, lead, loai, t2, t2 + timedelta(days=2))

    r = client.post(f"/api/leaves/{rid}/cancel", headers=_h(tho))
    assert r.status_code == 400 and "Xin hủy" in r.json()["detail"], r.text

    assert client.post(f"/api/leaves/{rid}/xin-huy", json={"ly_do": ""},
                       headers=_h(tho)).status_code == 422
    truoc = _cho_duyet(client, lead)
    r = client.post(f"/api/leaves/{rid}/xin-huy", json={"ly_do": "Ở nhà xong việc sớm"},
                    headers=_h(tho))
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["status"] == "approved", "đơn phải VẪN hiệu lực tới khi người duyệt đồng ý"
    assert d["yeu_cau_huy"]["trang_thai"] == "cho"
    assert _cho_duyet(client, lead) == truoc + 1

    # Một đơn chỉ một yêu cầu chờ.
    r = client.post(f"/api/leaves/{rid}/xin-huy", json={"ly_do": "lần 2"}, headers=_h(tho))
    assert r.status_code == 400 and "đang chờ" in r.json()["detail"]

    hang_doi = client.get("/api/leaves/xin-huy", headers=_h(lead)).json()["items"]
    yc_id = next(x["yeu_cau"]["id"] for x in hang_doi if x["don"]["id"] == rid)

    # Thợ không tự quyết được yêu cầu của mình (không có ô duyệt).
    assert client.post(f"/api/leaves/xin-huy/{yc_id}/quyet", json={"dong_y": True},
                       headers=_h(tho)).status_code == 403
    # Giữ nguyên mà không ghi lý do ⇒ chặn.
    r = client.post(f"/api/leaves/xin-huy/{yc_id}/quyet", json={"dong_y": False}, headers=_h(lead))
    assert r.status_code == 400, r.text
    r = client.post(f"/api/leaves/xin-huy/{yc_id}/quyet",
                    json={"dong_y": False, "ghi_chu": "Tổ đã xếp người thay, cứ nghỉ"},
                    headers=_h(lead))
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["status"] == "approved"
    assert d["yeu_cau_huy"]["trang_thai"] == "giu_nguyen"
    assert d["yeu_cau_huy"]["ly_do_quyet"] == "Tổ đã xếp người thay, cứ nghỉ"
    assert _cho_duyet(client, lead) == truoc

    # Xin lại được (không hạn chót) → đồng ý → hủy cả đơn (chưa tới ngày bắt đầu).
    r = client.post(f"/api/leaves/{rid}/xin-huy", json={"ly_do": "Việc nhà đã xong"}, headers=_h(tho))
    yc2 = r.json()["yeu_cau_huy"]["id"]
    r = client.post(f"/api/leaves/xin-huy/{yc2}/quyet", json={"dong_y": True}, headers=_h(lead))
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "cancelled"
    assert r.json()["yeu_cau_huy"]["trang_thai"] == "dong_y"


def test_NGHI_PHEP_rut_lai_yeu_cau_va_don_cho_duyet_van_tu_huy_thang(client):
    admin = _admin_token(client)
    tho, _ = _tho(client, admin, ten="Thợ rút lại")
    lead = _lead_token()
    loai = _loai_khong_luong(client, admin)
    t2 = _thu_hai_toi(21)
    rid = _don_da_duyet(client, tho, lead, loai, t2, t2)
    yc = client.post(f"/api/leaves/{rid}/xin-huy", json={"ly_do": "đổi ý"},
                     headers=_h(tho)).json()["yeu_cau_huy"]["id"]
    # Người khác không rút lại hộ được.
    assert client.post(f"/api/leaves/xin-huy/{yc}/rut-lai", headers=_h(lead)).status_code == 403
    r = client.post(f"/api/leaves/xin-huy/{yc}/rut-lai", headers=_h(tho))
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "approved" and r.json()["yeu_cau_huy"]["trang_thai"] == "rut_lai"
    # Rút rồi thì người duyệt không quyết được nữa.
    assert client.post(f"/api/leaves/xin-huy/{yc}/quyet", json={"dong_y": True},
                       headers=_h(lead)).status_code == 400

    # Đơn CHỜ duyệt: vẫn tự hủy thẳng như trước — chưa vào kế hoạch nào.
    r = client.post("/api/leaves", json={"leave_type_id": loai, "start_date": (t2 + timedelta(days=7)).isoformat(),
                                         "end_date": (t2 + timedelta(days=7)).isoformat()}, headers=_h(tho))
    r = client.post(f"/api/leaves/{r.json()['id']}/cancel", headers=_h(tho))
    assert r.status_code == 200 and r.json()["status"] == "cancelled"


def test_NGHI_PHEP_da_qua_khong_xin_huy_nguoi_duyet_huy_thang_phai_co_ly_do(client):
    admin = _admin_token(client)
    tho, _ = _tho(client, admin, ten="Thợ đơn cũ")
    lead = _lead_token()
    loai = _loai_khong_luong(client, admin)
    cu = hom_nay_vn() - timedelta(days=10)
    cu = cu - timedelta(days=cu.weekday())          # Thứ Hai của tuần đó — ngày làm việc
    rid = _don_da_duyet(client, tho, lead, loai, cu, cu)
    r = client.post(f"/api/leaves/{rid}/xin-huy", json={"ly_do": "nhầm"}, headers=_h(tho))
    assert r.status_code == 400 and "đã qua" in r.json()["detail"], r.text

    # Người duyệt hủy thẳng đơn đã duyệt: thiếu lý do ⇒ chặn; có lý do ⇒ hủy + lý do đọc lại được.
    assert client.post(f"/api/leaves/{rid}/cancel", headers=_h(lead)).status_code == 400
    r = client.post(f"/api/leaves/{rid}/cancel", json={"ly_do": "Hôm đó vẫn đi làm, gỡ đơn"},
                    headers=_h(lead))
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["status"] == "cancelled"
    assert d["yeu_cau_huy"]["truc_tiep"] is True
    assert d["yeu_cau_huy"]["ly_do_quyet"] == "Hôm đó vẫn đi làm, gỡ đơn"


def test_NGHI_PHEP_dang_do_dong_y_la_RUT_NGAN_giu_cac_ngay_truoc(client):
    """⭐ Chủ chốt *"tính nghỉ 1 ngày"*: nghỉ T2–T4, sáng T3 xin hủy ⇒ đồng ý thì đơn còn T2, 1 ngày;
    đơn vẫn `approved`. Gọi service với `hom_nay` = T3 (API dùng ngày thật)."""
    admin = _admin_token(client)
    tho, _ = _tho(client, admin, ten="Thợ nghỉ dở")
    lead = _lead_token()
    loai = _loai_khong_luong(client, admin)
    t2 = _thu_hai_toi(28)
    rid = _don_da_duyet(client, tho, lead, loai, t2, t2 + timedelta(days=2))

    db = SessionLocal()
    try:
        svc = LeaveService(LeaveRepository(db), EmployeeRepository(db), AuditLogRepository(db),
                           attendance=AttendanceRepository(db), yeu_cau_huy=YeuCauHuyRepository(db))
        emp = LeaveRepository(db).get_request(rid).employee_id
        tho_user = UserRepository(db).get_by_id(EmployeeRepository(db).get_by_id(emp).user_id)
        _, yc = svc.xin_huy(actor=tho_user, request_id=rid, ly_do="Khỏi ốm, đi làm lại",
                            hom_nay=t2 + timedelta(days=1))
        yc_id = yc.id
        assert yc.huy_tu_ngay == t2 + timedelta(days=1)
    finally:
        db.close()

    r = client.post(f"/api/leaves/xin-huy/{yc_id}/quyet", json={"dong_y": True}, headers=_h(lead))
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["status"] == "approved", "nghỉ dở ⇒ RÚT NGẮN, không hủy cả đơn"
    assert (d["start_date"], d["end_date"], d["days"]) == (t2.isoformat(), t2.isoformat(), 1)
    assert d["yeu_cau_huy"]["den_ngay_cu"] == (t2 + timedelta(days=2)).isoformat()


# --- tăng ca --------------------------------------------------------------------------------------


def test_TANG_CA_da_duyet_chi_duoc_XIN_huy_cung_luat_nghi_phep(client):
    admin = _admin_token(client)
    tho, _ = _tho(client, admin, ten="Thợ tăng ca")
    lead = _lead_token()
    ngay = _thu_hai_toi()
    r = client.post("/api/overtime/me", json={"work_date": ngay.isoformat(), "from_minute": 1080,
                                              "to_minute": 1200, "reason": "chạy đơn"},
                    headers=_h(tho))
    assert r.status_code == 201, r.text
    rid = r.json()["id"]
    assert client.post(f"/api/overtime/{rid}/approve", json={}, headers=_h(lead)).status_code == 200

    r = client.post(f"/api/overtime/{rid}/cancel", headers=_h(tho))
    assert r.status_code == 400 and "Xin hủy" in r.json()["detail"], r.text
    truoc = _cho_duyet(client, lead, "/api/overtime")
    r = client.post(f"/api/overtime/{rid}/xin-huy", json={"ly_do": "Con ốm"}, headers=_h(tho))
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "approved" and r.json()["yeu_cau_huy"]["trang_thai"] == "cho"
    assert _cho_duyet(client, lead, "/api/overtime") == truoc + 1

    yc = next(x["yeu_cau"]["id"] for x in
              client.get("/api/overtime/xin-huy", headers=_h(lead)).json()["items"]
              if x["don"]["id"] == rid)
    r = client.post(f"/api/overtime/xin-huy/{yc}/quyet", json={"dong_y": True}, headers=_h(lead))
    assert r.status_code == 200 and r.json()["status"] == "cancelled", r.text
    assert _cho_duyet(client, lead, "/api/overtime") == truoc


def test_TANG_CA_da_cham_VAO_tang_ca_thi_chan_xin_huy(client):
    """Phiếu tổ trưởng TẠO HỘ (created_by = tổ trưởng) — thợ vẫn là chủ phiếu, xin hủy được; nhưng
    đã có lượt VÀO trong khung phiếu (kể cả 60' vào sớm) thì chặn luôn."""
    admin = _admin_token(client)
    tho, eid = _tho(client, admin, ten="Thợ đã vào TC")
    lead = _lead_token()
    hom_nay = hom_nay_vn()
    r = client.post("/api/overtime", json={"employee_id": eid, "work_date": hom_nay.isoformat(),
                                           "from_minute": 1020, "to_minute": 1200, "reason": "gấp"},
                    headers=_h(lead))
    assert r.status_code == 201 and r.json()["status"] == "approved", r.text
    rid = r.json()["id"]

    # Chưa chấm gì: xin hủy được (phiếu tạo hộ vẫn là của thợ) → rút lại để thử tiếp.
    r = client.post(f"/api/overtime/{rid}/xin-huy", json={"ly_do": "thử"}, headers=_h(tho))
    assert r.status_code == 200, r.text
    assert client.post(f"/api/overtime/xin-huy/{r.json()['yeu_cau_huy']['id']}/rut-lai",
                       headers=_h(tho)).status_code == 200

    # Chấm VÀO 16:30 (phiếu từ 17:00, được vào sớm 60') ⇒ tăng ca đã bắt đầu ⇒ chặn.
    db = SessionLocal()
    try:
        AttendanceRepository(db).create_log(
            employee_id=eid, check_type="in", within_range=True,
            checked_at=datetime(hom_nay.year, hom_nay.month, hom_nay.day, 16, 30, tzinfo=VN)
            .astimezone(timezone.utc))
        db.commit()
    finally:
        db.close()
    r = client.post(f"/api/overtime/{rid}/xin-huy", json={"ly_do": "về sớm"}, headers=_h(tho))
    assert r.status_code == 400 and "chấm vào tăng ca" in r.json()["detail"], r.text
