"""Bản rà 07/09/2026 (`docs/RA_SOAT_NHAN_SU_LUONG.md`) — Đợt 1: khoá lại từng lỗ hổng bằng test đúng
kịch bản thăm dò đã chạy hôm đó. Mỗi test ghi mã phát hiện (C1…, A3…, L12…) ở tên để tra ngược.

Tháng thử = 6/2026 (T2–T7 = 26 công; nằm TRƯỚC mốc `AP_DUNG_CHOT_CONG_TRUOC_TU` nên chốt lương không
vướng kỳ công — đúng cái cần để soi các lý do chặn chốt khác).
"""
from __future__ import annotations

from datetime import date, datetime, timezone

from app.db import SessionLocal
from app.repositories.attendance_repo import AttendanceRepository
from app.repositories.employee_repo import EmployeeRepository
from app.repositories.rbac_repo import DepartmentRepository, RoleRepository
from app.repositories.user_repo import UserRepository
from app.security import create_access_token, hash_password
from app.services.attendance_service import VN_TZ

ADMIN = {"username": "admin", "password": "admin123"}
NAM, THANG = 2026, 6


def _h(client) -> dict[str, str]:
    tok = client.post("/api/auth/login", json=ADMIN).json()["access_token"]
    return {"Authorization": f"Bearer {tok}"}


def _dept_id(name: str) -> int:
    db = SessionLocal()
    try:
        return DepartmentRepository(db).get_by_name(name).id
    finally:
        db.close()


def _token_luong(username: str, *, scope: str, phong: str, **perms) -> str:
    """Tài khoản có ô `luong` (+ `nhan_su` read) với PHẠM VI `scope`, thuộc phòng `phong`."""
    db = SessionLocal()
    try:
        users, depts, roles = UserRepository(db), DepartmentRepository(db), RoleRepository(db)
        dept = depts.get_by_name(phong)
        role = roles.get_by_name_and_department(f"role-{username}", dept.id)
        if role is None:
            role = roles.create(name=f"role-{username}", department_id=dept.id)
        roles.set_permission(role_id=role.id, module_key="luong", scope=scope, **perms)
        roles.set_permission(role_id=role.id, module_key="nhan_su", scope=scope,
                             can_read=True, can_update=perms.get("can_update", False))
        user = users.get_by_username(username)
        if user is None:
            user = users.create(username=username, name=username, password_hash=hash_password("x"))
        users.set_assignment(user, department_id=dept.id, role_id=role.id, is_active=True)
        return create_access_token(str(user.id))
    finally:
        db.close()


def _nv(client, h, ten: str, phong: str, *, hire="2020-01-01", status="active",
        prob_end="2020-03-01") -> int:
    r = client.post("/api/employees", json={
        "full_name": ten, "department_id": _dept_id(phong), "hire_date": hire, "gender": "male",
        "status": status, "probation_end_date": prob_end}, headers=h)
    assert r.status_code == 201, r.text
    return r.json()["employee"]["id"]


def _khai_luong(client, h, eid: int, **kw):
    body = {"effective_from": "2026-01-01", "luong_vi_tri": 10_400_000}
    body.update(kw)
    r = client.post(f"/api/luong/salaries/{eid}", json=body, headers=h)
    assert r.status_code in (200, 201), r.text
    return r.json()


def _ca(client, h) -> int:
    r = client.get("/api/attendance/shifts", headers=h).json()
    for s in r.get("items", []):
        if s["name"] == "HC 8-16 (rà)":
            return s["id"]
    # 8 tiếng tròn (08:00–16:00) để không vướng luật "ca khớp giờ công chuẩn" dù tham số lương đã tạo.
    r = client.post("/api/attendance/shifts", json={"name": "HC 8-16 (rà)", "start_time": "08:00",
                                                    "end_time": "16:00"}, headers=h)
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _bam_du_thang(client, h, eid: int, *, tu=1, den=30, eff="2020-01-01", thang=THANG) -> None:
    ca = _ca(client, h)
    r = client.put(f"/api/employees/{eid}/shift", json={"default_shift_id": ca, "effective_from": eff},
                   headers=h)
    assert r.status_code == 200, r.text
    db = SessionLocal()
    try:
        repo = AttendanceRepository(db)
        for d in range(tu, den + 1):
            if date(NAM, thang, d).weekday() == 6:
                continue
            for hh, k in ((8, "in"), (16, "out")):
                repo.create_log(employee_id=eid, check_type=k, within_range=True,
                                checked_at=datetime(NAM, thang, d, hh, 0, tzinfo=VN_TZ).astimezone(timezone.utc))
    finally:
        db.close()


def _gen(client, h, year=NAM, month=THANG) -> list[dict]:
    r = client.post("/api/luong/generate", json={"year": year, "month": month}, headers=h)
    assert r.status_code == 200, r.text
    return r.json()["lines"]


def _line(lines, eid) -> dict:
    return next(l for l in lines if l["employee_id"] == eid)


# =============================================================================================
# C — phân quyền / phạm vi
# =============================================================================================

def test_C1_tinh_lai_doi_o_sua_va_pham_vi_toan_cong_ty(client):
    """Trước 07/09: `POST /generate` chỉ đòi `luong:create` (ô mọi vai seed đều có để xin tạm ứng)
    và trả bảng lương CẢ CÔNG TY. Nay: đòi ô Sửa + phạm vi toàn công ty như Chốt."""
    h = _h(client)
    a = _nv(client, h, "C1 A", "Kinh doanh")
    _khai_luong(client, h, a)
    _gen(client, h)
    # vai chỉ có create (như công nhân) → 403
    t = _token_luong("c1-create", scope="own", phong="Kinh doanh", can_read=True, can_create=True)
    r = client.post("/api/luong/generate", json={"year": NAM, "month": THANG},
                    headers={"Authorization": f"Bearer {t}"})
    assert r.status_code == 403, r.text
    # có Sửa nhưng phạm vi phòng → vẫn 403 (Tính lại ghi đè dòng của mọi người)
    t2 = _token_luong("c1-dept", scope="department", phong="Kinh doanh", can_read=True,
                      can_update=True, can_view_payroll_table=True)
    r = client.post("/api/luong/generate", json={"year": NAM, "month": THANG},
                    headers={"Authorization": f"Bearer {t2}"})
    assert r.status_code == 403, r.text


def _hai_nguoi_hai_phong(client, h) -> tuple[int, int]:
    a = _nv(client, h, "Phòng KD", "Kinh doanh")
    b = _nv(client, h, "Phòng SX", "Sản xuất")
    _khai_luong(client, h, a)
    _khai_luong(client, h, b)
    return a, b


def test_C2_sua_dong_luong_ngoai_pham_vi_bi_chan(client):
    """`update_line` từng nhận `scope` rồi bỏ quên ⇒ vai phạm vi tổ sửa được dòng của bất kỳ ai."""
    h = _h(client)
    a, b = _hai_nguoi_hai_phong(client, h)
    lines = _gen(client, h)
    t = _token_luong("c2-kd", scope="department", phong="Kinh doanh", can_read=True,
                     can_update=True, can_view_payroll_table=True)
    ht = {"Authorization": f"Bearer {t}"}
    r = client.put(f"/api/luong/lines/{_line(lines, b)['id']}", json={"vi_pham": 1_000}, headers=ht)
    assert r.status_code == 403, r.text
    r = client.put(f"/api/luong/lines/{_line(lines, a)['id']}", json={"vi_pham": 1_000}, headers=ht)
    assert r.status_code == 200, r.text


def test_C3_ho_so_luong_theo_pham_vi(client):
    """Đọc/ghi hồ sơ lương (`/salaries/*`, `/preview`) và khoản danh mục của NV phải hỏi phạm vi."""
    h = _h(client)
    a, b = _hai_nguoi_hai_phong(client, h)
    t = _token_luong("c3-kd", scope="department", phong="Kinh doanh", can_read=True,
                     can_update=True, can_view_salary=True, can_manage_salary_profiles=True)
    ht = {"Authorization": f"Bearer {t}"}
    assert client.get(f"/api/luong/salaries/{b}", headers=ht).status_code == 403
    assert client.get(f"/api/luong/salaries/{b}/preview", headers=ht).status_code == 403
    assert client.post(f"/api/luong/salaries/{b}", json={"effective_from": "2026-02-01",
                       "luong_vi_tri": 99_000_000}, headers=ht).status_code == 403
    assert client.get(f"/api/luong/components/employee/{b}", headers=ht).status_code == 403
    assert client.get(f"/api/luong/salaries/{a}", headers=ht).status_code == 200
    assert client.get(f"/api/luong/salaries/{a}/preview", headers=ht).status_code == 200
    # Lương của B KHÔNG bị đổi bởi cú POST 403 ở trên.
    assert client.get(f"/api/luong/salaries/{b}/preview", headers=h).json()["luong_vi_tri"] == 10_400_000


def test_C4_tam_ung_theo_pham_vi(client):
    """`GET /advances` lọc theo phạm vi; `POST /advances` không lập được phiếu đứng tên người ngoài
    phạm vi; `cancel` cũng vậy."""
    h = _h(client)
    a, b = _hai_nguoi_hai_phong(client, h)
    adv_b = client.post("/api/luong/advances", json={"employee_id": b, "period_year": NAM,
                        "period_month": THANG, "advance_date": f"{NAM}-06-10", "amount": 1_000_000},
                        headers=h).json()
    t = _token_luong("c4-kd", scope="department", phong="Kinh doanh", can_read=True,
                     can_create=True, can_approve=True)
    ht = {"Authorization": f"Bearer {t}"}
    ds = client.get("/api/luong/advances", params={"year": NAM, "month": THANG}, headers=ht).json()["items"]
    assert all(x["employee_id"] != b for x in ds), "tạm ứng của phòng khác vẫn lộ"
    r = client.post("/api/luong/advances", json={"employee_id": b, "period_year": NAM,
                    "period_month": THANG, "advance_date": f"{NAM}-06-11", "amount": 500_000}, headers=ht)
    assert r.status_code == 403, r.text
    assert client.post(f"/api/luong/advances/{adv_b['id']}/cancel", headers=ht).status_code == 403
    r = client.post("/api/luong/advances", json={"employee_id": a, "period_year": NAM,
                    "period_month": THANG, "advance_date": f"{NAM}-06-11", "amount": 500_000}, headers=ht)
    assert r.status_code == 201, r.text


def test_C5_yeu_cau_cap_nhat_ho_so_theo_pham_vi(client):
    """`GET /employees/update-requests` kèm "giá trị hiện tại" của CCCD/số tài khoản — phải lọc phạm vi."""
    h = _h(client)
    a, b = _hai_nguoi_hai_phong(client, h)
    assert client.post(f"/api/employees/{b}/account", json={"username": "nv_b_c5", "password": "Matkhau123!"},
                       headers=h).status_code == 200
    hb = {"Authorization": f"Bearer {client.post('/api/auth/login', json={'username': 'nv_b_c5', 'password': 'Matkhau123!'}).json()['access_token']}"}
    r = client.post("/api/employees/me/update-requests",
                    json={"changes": {"bank_account": "0123456789"}, "reason": "đổi ngân hàng"}, headers=hb)
    assert r.status_code in (200, 201), r.text
    t = _token_luong("c5-kd", scope="department", phong="Kinh doanh", can_read=True)
    ds = client.get("/api/employees/update-requests", headers={"Authorization": f"Bearer {t}"})
    assert ds.status_code == 200, ds.text
    assert all(x["employee_id"] != b for x in ds.json()["items"]), "yêu cầu của phòng khác vẫn lộ"
    assert any(x["employee_id"] == b for x in client.get("/api/employees/update-requests", headers=h).json()["items"])


def test_C6_gan_vai_tro_khi_tao_tai_khoan_phai_dung_quyen_va_dung_phong(client):
    """Trước 07/09 `POST /employees/{id}/account` nhận `role_id` tuỳ ý chỉ với `nhan_su:update`."""
    h = _h(client)
    a = _nv(client, h, "C6 A", "Kinh doanh")
    db = SessionLocal()
    try:
        roles, depts = RoleRepository(db), DepartmentRepository(db)
        kd, sx = depts.get_by_name("Kinh doanh"), depts.get_by_name("Sản xuất")
        role_kd = roles.create(name="role-c6-kd", department_id=kd.id)
        role_sx = roles.create(name="role-c6-sx", department_id=sx.id)
        role_kd_id, role_sx_id = role_kd.id, role_sx.id
    finally:
        db.close()
    # Vai có nhan_su:update nhưng KHÔNG có nguoi_dung:assign_role → 403
    t = _token_luong("c6-hcns", scope="all", phong="Kinh doanh", can_read=True, can_update=True)
    r = client.post(f"/api/employees/{a}/account", json={"username": "nv_c6", "password": "Matkhau123!",
                    "role_id": role_kd_id}, headers={"Authorization": f"Bearer {t}"})
    assert r.status_code == 403, r.text
    # Admin: vai của phòng khác → 400; đúng phòng → 200
    r = client.post(f"/api/employees/{a}/account", json={"username": "nv_c6", "password": "Matkhau123!",
                    "role_id": role_sx_id}, headers=h)
    assert r.status_code == 400, r.text
    r = client.post(f"/api/employees/{a}/account", json={"username": "nv_c6", "password": "Matkhau123!",
                    "role_id": role_kd_id}, headers=h)
    assert r.status_code == 200, r.text


def test_C7_nghi_viec_thi_refresh_khong_cap_token_moi(client):
    """Nghỉ việc chỉ bump token_version; `/refresh` chỉ hỏi `is_active` rồi cấp token MỚI ⇒ người vừa
    nghỉ vẫn vào tiếp. Nay: nghỉ việc khoá tài khoản, tuyển lại mở."""
    h = _h(client)
    q = _nv(client, h, "C7 Q", "Kinh doanh")
    assert client.post(f"/api/employees/{q}/account", json={"username": "nv_c7", "password": "Matkhau123!"},
                       headers=h).status_code == 200
    lg = client.post("/api/auth/login", json={"username": "nv_c7", "password": "Matkhau123!"})
    assert lg.status_code == 200
    assert client.post(f"/api/employees/{q}/transitions", json={"kind": "resign",
                       "effective_date": f"{NAM}-06-20", "resign_reason": "test"}, headers=h).status_code == 200
    rf = client.post("/api/auth/refresh")
    assert rf.status_code == 401, rf.text
    assert client.post("/api/auth/login", json={"username": "nv_c7", "password": "Matkhau123!"}).status_code == 401
    assert client.post(f"/api/employees/{q}/transitions", json={"kind": "reinstate",
                       "effective_date": f"{NAM}-06-25"}, headers=h).status_code == 200
    assert client.post("/api/auth/login", json={"username": "nv_c7", "password": "Matkhau123!"}).status_code == 200


def test_C13_set_is_kcs_luu_that(client):
    """`rbac_repo.set_is_kcs` từng quên commit + return ⇒ bấm "Tổ KCS" không lưu."""
    db = SessionLocal()
    try:
        depts = DepartmentRepository(db)
        d = depts.create(name="Tổ KCS rà")
        out = depts.set_is_kcs(d, True)
        assert out is not None and out.is_kcs is True
    finally:
        db.close()
    db = SessionLocal()
    try:
        assert DepartmentRepository(db).get_by_name("Tổ KCS rà").is_kcs is True
    finally:
        db.close()


# =============================================================================================
# A/D — hai đường tính và ca biên hồ sơ
# =============================================================================================

def test_A3_thu_viec_nghi_giua_thang_van_an_80pct(client):
    """P13: thử việc nghỉ 15/06 (12 công) từng được trả 100% vì tháng đó `effective_status` = resigned."""
    h = _h(client)
    p = _nv(client, h, "A3 TV", "Kinh doanh", hire=f"{NAM}-05-01", status="probation",
            prob_end=f"{NAM}-07-31")
    _khai_luong(client, h, p)
    _bam_du_thang(client, h, p, tu=1, den=13, eff=f"{NAM}-05-01")
    assert client.post(f"/api/employees/{p}/transitions", json={"kind": "resign",
                       "effective_date": f"{NAM}-06-15", "resign_reason": "test"}, headers=h).status_code == 200
    ln = _line(_gen(client, h), p)
    assert ln["actual_cong"] == 12 and ln["is_probation"] is True
    assert ln["luong_cong"] == 12 * 400_000 * 0.8


def test_A5_sua_1_o_doc_ho_so_luong_tai_cuoi_ky(client):
    """Khai mốc lương mới (đoàn viên) hiệu lực 01/07 rồi sửa một ô ở kỳ 6: đoàn phí kỳ 6 KHÔNG được
    nhảy theo hồ sơ hôm nay."""
    h = _h(client)
    assert client.put("/api/luong/params", json={"cong_doan_rate": 0.005}, headers=h).status_code == 200
    e = _nv(client, h, "A5", "Kinh doanh")
    _khai_luong(client, h, e, union_member=False)
    _bam_du_thang(client, h, e)
    ln = _line(_gen(client, h), e)
    assert ln["cong_doan"] == 0
    _khai_luong(client, h, e, effective_from=f"{NAM}-07-01", union_member=True)
    r = client.put(f"/api/luong/lines/{ln['id']}", json={"vi_pham": 0}, headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["cong_doan"] == 0, "Sửa 1 ô đọc cờ đoàn viên của mốc tương lai"
    assert _line(_gen(client, h), e)["cong_doan"] == 0
    client.put("/api/luong/params", json={"cong_doan_rate": 0}, headers=h)


def test_D3_thue_ghi_tay_vao_tran_30pct_hai_duong_cung_gross(client):
    """Trần 30% (Đ102) tính trên thuế THỰC TRỪ: `pit_manual` + phạt chạm trần → "Sửa 1 ô" và "Tính lại"
    phải ra cùng một gross."""
    h = _h(client)
    e = _nv(client, h, "D3", "Kinh doanh")
    _khai_luong(client, h, e, luong_vi_tri=30_000_000)
    _bam_du_thang(client, h, e)
    ln = _line(_gen(client, h), e)
    r = client.put(f"/api/luong/lines/{ln['id']}", json={"vi_pham": 10_000_000, "pit": 2_000_000,
                   "pit_manual": True}, headers=h)
    assert r.status_code == 200, r.text
    sua = r.json()
    assert sua["pit"] == 2_000_000 and sua["pit_manual"] is True
    lai = _line(_gen(client, h), e)
    assert lai["pit"] == 2_000_000
    assert lai["gross"] == sua["gross"], f"Tính lại {lai['gross']} ≠ Sửa 1 ô {sua['gross']}"
    assert lai["net_pay"] == sua["net_pay"]


def test_D4_monthly_override_da_go(client):
    from app.schemas.payroll import LineUpdateIn
    assert "monthly_override" not in LineUpdateIn.model_fields


# =============================================================================================
# Chặn chốt & xuất file
# =============================================================================================

def _chi(client, h, aid: int) -> dict:
    """Kế toán lập phiếu chi cho phiếu tạm ứng đã duyệt — 07/09/2026: CHỈ phiếu đã chi mới trừ."""
    r = client.post("/api/accounting/payment-vouchers", json={
        "salary_advance_id": aid, "source_type": "salary_advance", "voucher_type": "cash",
        "payment_stage": "other", "voucher_date": f"{NAM}-06-05", "amount": 1, "currency": "VND",
        "exchange_rate": 1, "content": "Chi tạm ứng", "cash_recipient_name": "x"}, headers=h)
    assert r.status_code == 201, r.text
    return r.json()


def _ung(client, h, eid: int, amount: float, *, thang=THANG, kind="tam_ung") -> int:
    r = client.post("/api/luong/advances", json={"employee_id": eid, "period_year": NAM, "period_month": thang,
                    "advance_date": f"{NAM}-{thang:02d}-10", "amount": amount, "kind": kind}, headers=h)
    assert r.status_code == 201, r.text
    aid = r.json()["id"]
    assert client.post(f"/api/luong/advances/{aid}/approve", json={}, headers=h).status_code == 200
    return aid


def test_L12_chi_tam_ung_sau_tinh_lai_thi_chua_chot_duoc(client):
    """P12: Tính lại → phiếu đổi trạng thái (duyệt/chi) → Chốt luôn từng khoá kỳ với tạm ứng = 0."""
    h = _h(client)
    e = _nv(client, h, "L12", "Kinh doanh")
    _khai_luong(client, h, e)
    _bam_du_thang(client, h, e)
    assert _line(_gen(client, h), e)["advance_total"] == 0
    aid = _ung(client, h, e, 5_000_000)
    r = client.post("/api/luong/lock", json={"year": NAM, "month": THANG}, headers=h)
    assert r.status_code == 400 and "CHƯA LẬP PHIẾU CHI" in r.json()["detail"], r.text   # L11b
    _chi(client, h, aid)
    r = client.post("/api/luong/lock", json={"year": NAM, "month": THANG}, headers=h)
    assert r.status_code == 400 and "SAU lần" in r.json()["detail"], r.text                # L12
    assert _line(_gen(client, h), e)["advance_total"] == 5_000_000
    assert client.post("/api/luong/lock", json={"year": NAM, "month": THANG}, headers=h).status_code == 200


def test_B4_duyet_chua_chi_thi_chua_tru__chi_roi_moi_tru(client):
    """Chủ chốt 07/09/2026: kế toán phải lập phiếu chi thì mới trừ vào lương."""
    h = _h(client)
    e = _nv(client, h, "B4", "Kinh doanh")
    _khai_luong(client, h, e)
    _bam_du_thang(client, h, e)
    aid = _ung(client, h, e, 2_000_000)
    ln = _line(_gen(client, h), e)
    assert ln["advance_total"] == 0, "đã duyệt nhưng chưa chi mà đã trừ"
    _chi(client, h, aid)
    ln2 = _line(_gen(client, h), e)
    assert ln2["advance_total"] == 2_000_000 and ln2["net_pay"] == ln["net_pay"] - 2_000_000


def test_B2_tam_ung_vuot_luong_don_no_sang_ky_sau_tru_sau_cung(client):
    """P4: ứng 30tr, lương ~10tr: thực lĩnh 0 và phần dư CHUYỂN SANG THÁNG SAU, tháng sau trừ tiếp."""
    h = _h(client)
    e = _nv(client, h, "B2", "Kinh doanh")
    _khai_luong(client, h, e)
    _bam_du_thang(client, h, e)
    _bam_du_thang(client, h, e, thang=7, den=31)
    _chi(client, h, _ung(client, h, e, 30_000_000))
    l6 = _line(_gen(client, h), e)
    net_pre6 = l6["gross"] - l6["bhxh"] - l6["cong_doan"] - l6["pit"]
    assert l6["advance_total"] == 30_000_000 and l6["net_pay"] == 0
    assert l6["no_ung_ky_truoc"] == 0
    assert abs(l6["no_ung_chuyen_ky_sau"] - (30_000_000 - net_pre6)) < 1
    assert client.post("/api/luong/lock", json={"year": NAM, "month": THANG}, headers=h).status_code == 200
    l7 = _line(_gen(client, h, month=7), e)
    net_pre7 = l7["gross"] - l7["bhxh"] - l7["cong_doan"] - l7["pit"]
    assert l7["advance_total"] == 0 and l7["no_ung_ky_truoc"] == l6["no_ung_chuyen_ky_sau"]
    assert l7["net_pay"] == max(0, round(net_pre7 - l7["no_ung_ky_truoc"]))
    assert abs(l7["no_ung_chuyen_ky_sau"] - max(0, l7["no_ung_ky_truoc"] - net_pre7)) < 1
    # "Sửa 1 ô" ra cùng số với "Tính lại".
    r = client.put(f"/api/luong/lines/{l7['id']}", json={"vi_pham": 0}, headers=h)
    assert r.status_code == 200 and r.json()["net_pay"] == l7["net_pay"]
    assert r.json()["no_ung_chuyen_ky_sau"] == l7["no_ung_chuyen_ky_sau"]


def test_B5_huy_phieu_chi_tra_phieu_ve_da_duyet_va_chan_khi_ky_da_chot(client):
    h = _h(client)
    e = _nv(client, h, "B5", "Kinh doanh")
    _khai_luong(client, h, e)
    _bam_du_thang(client, h, e)
    aid = _ung(client, h, e, 2_000_000)
    pc = _chi(client, h, aid)
    assert _line(_gen(client, h), e)["advance_total"] == 2_000_000
    r = client.post(f"/api/accounting/payment-vouchers/{pc['id']}/cancel", json={"reason": "ghi nhầm"}, headers=h)
    assert r.status_code == 200, r.text
    ds = client.get("/api/luong/advances", params={"year": NAM, "month": THANG}, headers=h).json()["items"]
    assert next(a for a in ds if a["id"] == aid)["status"] == "approved"
    r = client.post("/api/luong/lock", json={"year": NAM, "month": THANG}, headers=h)
    assert r.status_code == 400 and "CHƯA LẬP PHIẾU CHI" in r.json()["detail"]
    pc2 = _chi(client, h, aid)
    _gen(client, h)
    assert client.post("/api/luong/lock", json={"year": NAM, "month": THANG}, headers=h).status_code == 200
    r = client.post(f"/api/accounting/payment-vouchers/{pc2['id']}/cancel", json={"reason": "ghi nhầm"}, headers=h)
    assert r.status_code == 409, r.text


def test_L13_co_cong_ma_chua_khai_luong_thi_chua_chot_duoc(client):
    """P2: chưa khai lương → dòng 0đ lặng lẽ, vẫn chốt/chi/phát phiếu. Nay: cờ trên dòng + chặn chốt.
    L13 chỉ áp từ mốc `AP_DUNG_CHOT_CONG_TRUOC_TU` (08/2026) — C9, 08/09/2026 — nên thử ở tháng 8."""
    from tests.test_chan_ghi_khi_ky_cong_da_chot import _chot_cong
    h = _h(client)
    e = _nv(client, h, "L13", "Kinh doanh")
    _bam_du_thang(client, h, e, thang=8, den=31)
    ln = _line(_gen(client, h, month=8), e)
    assert ln["chua_khai_luong"] is True and ln["luong_cong"] == 0
    r = client.post("/api/luong/lock", json={"year": NAM, "month": 8}, headers=h)
    assert r.status_code == 400 and "CHƯA KHAI MỨC LƯƠNG" in r.json()["detail"], r.text
    _khai_luong(client, h, e)
    _chot_cong(client, h, nam=NAM, thang=8)
    ln = _line(_gen(client, h, month=8), e)
    assert ln["chua_khai_luong"] is False and ln["luong_cong"] == 26 * 400_000
    assert client.post("/api/luong/lock", json={"year": NAM, "month": 8}, headers=h).status_code == 200


def test_B9_file_chuyen_khoan_ky_nhap_bi_chan(client):
    h = _h(client)
    e = _nv(client, h, "B9", "Kinh doanh")
    _khai_luong(client, h, e)
    _bam_du_thang(client, h, e)
    _gen(client, h)
    r = client.get("/api/luong/bank.xlsx", params={"year": NAM, "month": THANG}, headers=h)
    assert r.status_code == 409, r.text
    assert client.post("/api/luong/lock", json={"year": NAM, "month": THANG}, headers=h).status_code == 200
    assert client.get("/api/luong/bank.xlsx", params={"year": NAM, "month": THANG}, headers=h).status_code == 200
