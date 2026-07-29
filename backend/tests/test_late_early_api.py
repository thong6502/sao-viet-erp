"""Phiếu ĐI MUỘN / VỀ SỚM / NGHỈ NỬA BUỔI (module `di_muon`).

Cùng hình dạng với phiếu tăng ca (1 ngày, từ giờ → đến giờ, 1 phiếu/ngày, TỔ TRƯỞNG duyệt):
NV tự gửi → tổ trưởng duyệt; HOẶC tổ trưởng khai hộ (khai hộ = duyệt luôn).

Khác tăng ca ở NHÁNH TIỀN — người tạo tự tick "trừ vào phép năm":
  - tick     → tiêu `leave_cong` ngày phép (làm tròn LÊN 0,5) và phần vắng VẪN được trả lương;
  - không    → quỹ phép không đụng, mất công phần vắng.
Hết phép mà vẫn tick ⇒ chặn ngay, báo rõ còn bao nhiêu ngày.
"""
from __future__ import annotations

from app.db import SessionLocal
from app.repositories.employee_repo import EmployeeRepository
from app.repositories.rbac_repo import DepartmentRepository, RoleRepository
from app.repositories.user_repo import UserRepository
from app.security import create_access_token, hash_password

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


def _make_emp(client, token, *, name, dept="Sản xuất") -> int:
    body = {"full_name": name, "department_id": _dept_id(dept),
            "hire_date": "2020-01-01", "gender": "male", "status": "active"}
    return client.post("/api/employees", json=body, headers=_h(token)).json()["employee"]["id"]


def _lead_token() -> str:
    """Tài khoản vai 'Tổ trưởng SX' — có `di_muon:approve` với scope `department`."""
    db = SessionLocal()
    try:
        users = UserRepository(db)
        existing = users.get_by_username("to-truong-dm")
        if existing is not None:
            return create_access_token(str(existing.id))
        sx = DepartmentRepository(db).get_by_name("Sản xuất")
        role = RoleRepository(db).get_by_name_and_department("Tổ trưởng SX", sx.id)
        u = users.create(username="to-truong-dm", name="Tổ trưởng",
                         password_hash=hash_password("x"))
        users.set_assignment(u, department_id=sx.id, role_id=role.id, is_active=True)
        return create_access_token(str(u.id))
    finally:
        db.close()


def _mk(client, token, eid, *, work_date="2026-07-16", frm=480, to=600,
        leave_type_id=None, expect=201):
    """Khai HỘ (tổ trưởng/HCNS) qua POST /api/late-early → duyệt luôn.
    frm/to = phút từ 00:00 NGÀY CÔNG → 480 = 08:00, 600 = 10:00, 840 = 14:00."""
    body = {"employee_id": eid, "work_date": work_date, "from_minute": frm,
            "to_minute": to, "reason": "kẹt xe"}
    if leave_type_id is not None:
        body["leave_type_id"] = leave_type_id
    r = client.post("/api/late-early", json=body, headers=_h(token))
    assert r.status_code == expect, r.text
    return r.json() if r.status_code < 400 else None


def _me(client, token, *, work_date, frm=480, to=540, reason=None, expect=201):
    """NV TỰ gửi phiếu cho CHÍNH MÌNH (POST /api/late-early/me) — luôn tạo cho hồ sơ của
    người đăng nhập, không đặt hộ NV khác được."""
    body = {"work_date": work_date, "from_minute": frm, "to_minute": to, "reason": reason}
    r = client.post("/api/late-early/me", json=body, headers=_h(token))
    assert r.status_code == expect, r.text
    return r.json() if r.status_code < 400 else None


def _mk_leave_type(client, token, name, *, quota) -> int:
    r = client.post("/api/leaves/types",
                    json={"name": name, "is_paid": True, "annual_quota": quota},
                    headers=_h(token))
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _assign_hc_shift(client, token, eid, *, name) -> int:
    """Gán ca HÀNH CHÍNH 08:00–17:00 → khung ca 540', là MẪU SỐ quy phút vắng ra ngày phép.
    `effective_from` KHÔNG được trước `hire_date` của NV (`_make_emp` để 2020-01-01)."""
    shift = client.post("/api/attendance/shifts",
                        json={"name": name, "start_time": "08:00", "end_time": "17:00"},
                        headers=_h(token))
    assert shift.status_code == 201, shift.text
    sid = shift.json()["id"]
    r = client.put(f"/api/employees/{eid}/shift",
                   json={"default_shift_id": sid, "effective_from": "2026-01-01"},
                   headers=_h(token))
    assert r.status_code == 200, r.text
    return sid


# --- luồng duyệt ------------------------------------------------------------


def test_lead_tao_ho_thi_duyet_luon(client):
    """Tổ trưởng khai thẳng cho thợ TỔ MÌNH → APPROVED ngay, không bắt thợ gửi rồi duyệt lại.
    Chỉ cần `di_muon:approve` (scope `department`), không cần quyền HCNS."""
    token = _admin_token(client)
    eid = _make_emp(client, token, name="Thợ ĐM 1")     # phòng Sản xuất = tổ của lead
    r = _mk(client, _lead_token(), eid, frm=480, to=600)
    assert r["status"] == "approved"
    assert r["minutes"] == 120                  # 08:00 → 10:00
    assert r["employee_name"] == "Thợ ĐM 1"
    assert r["decided_by"] is not None and r["decided_at"] is not None
    # Không tick trừ phép → quỹ phép không đụng.
    assert r["leave_type_id"] is None and r["leave_cong"] == 0


def test_nv_tu_gui_roi_duoc_duyet(client):
    """NV tự gửi → chờ duyệt → người có quyền duyệt bấm duyệt. Duyệt 2 lần thì chặn."""
    token = _admin_token(client)
    r = _me(client, token, work_date="2026-07-16", frm=480, to=540, reason="kẹt xe")
    rid = r["id"]
    assert r["status"] == "pending"
    assert r["decided_by"] is None

    mine = client.get("/api/late-early/me", headers=_h(token)).json()
    assert mine["has_employee"] is True and any(x["id"] == rid for x in mine["items"])

    ok = client.post(f"/api/late-early/{rid}/approve", json={}, headers=_h(token))
    assert ok.status_code == 200 and ok.json()["status"] == "approved"
    # Duyệt rồi thì không duyệt lại được nữa.
    again = client.post(f"/api/late-early/{rid}/approve", json={}, headers=_h(token))
    assert again.status_code == 400
    assert "đang chờ" in again.json()["detail"].lower()


def test_validate_gio_va_toi_da_1_phieu_ngay(client):
    """Biên giờ + luật 1 phiếu/ngày (chốt của chủ 27/07/2026)."""
    token = _admin_token(client)
    eid = _make_emp(client, token, name="Thợ ĐM 2")
    _mk(client, token, eid, frm=600, to=600, expect=400)     # kết thúc == bắt đầu
    _mk(client, token, eid, frm=600, to=540, expect=400)     # kết thúc trước bắt đầu
    _mk(client, token, eid, frm=0, to=1441, expect=400)      # vắng > 1 ngày → dùng đơn nghỉ phép
    _mk(client, token, eid, frm=480, to=600)                 # phiếu 1 hợp lệ
    _mk(client, token, eid, frm=1000, to=1100, expect=400)   # phiếu 2 KHÔNG trùng giờ vẫn bị chặn
    _mk(client, token, eid, work_date="2026-07-17")          # ngày khác → OK


def test_tu_choi_roi_thi_tao_lai_cung_ngay_duoc(client):
    """Phiếu bị TỪ CHỐI không còn 'giữ chỗ' → cùng NV, cùng ngày vẫn tạo lại được."""
    token = _admin_token(client)
    first = _me(client, token, work_date="2026-07-16", frm=480, to=540)
    bad = _me(client, token, work_date="2026-07-16", frm=600, to=660, expect=400)
    assert bad is None                                       # còn phiếu live → chặn

    rej = client.post(f"/api/late-early/{first['id']}/reject",
                      json={"note": "chưa hợp lý"}, headers=_h(token))
    assert rej.status_code == 200 and rej.json()["status"] == "rejected"

    again = _me(client, token, work_date="2026-07-16", frm=600, to=660)
    assert again["status"] == "pending" and again["id"] != first["id"]


def test_sua_phieu_cho_duyet(client):
    """Sửa phiếu đang chờ: đổi giờ OK; người KHÁC sửa → 403; duyệt rồi thì khóa."""
    token = _admin_token(client)
    rid = _me(client, token, work_date="2026-07-18", frm=480, to=540, reason="cũ")["id"]

    upd = client.put(f"/api/late-early/{rid}",
                     json={"work_date": "2026-07-18", "from_minute": 480, "to_minute": 600,
                           "reason": "mới"}, headers=_h(token))
    assert upd.status_code == 200, upd.text
    assert upd.json()["to_minute"] == 600 and upd.json()["minutes"] == 120
    assert upd.json()["reason"] == "mới"

    # Người KHÁC (tổ trưởng, không phải người tạo) → KHÔNG sửa được phiếu của admin.
    lead = _lead_token()
    other = client.put(f"/api/late-early/{rid}",
                       json={"work_date": "2026-07-18", "from_minute": 480, "to_minute": 660},
                       headers=_h(lead))
    assert other.status_code == 403, other.text

    # Duyệt rồi thì khóa, không sửa được nữa.
    client.post(f"/api/late-early/{rid}/approve", json={}, headers=_h(token))
    locked = client.put(f"/api/late-early/{rid}",
                        json={"work_date": "2026-07-18", "from_minute": 480, "to_minute": 660},
                        headers=_h(token))
    assert locked.status_code == 400 and "chờ duyệt" in locked.json()["detail"].lower()


def test_tu_choi_bat_buoc_ly_do(client):
    token = _admin_token(client)
    rid = _me(client, token, work_date="2026-07-20", frm=480, to=540)["id"]
    # schema chặn note rỗng / thiếu note
    assert client.post(f"/api/late-early/{rid}/reject", json={"note": ""},
                       headers=_h(token)).status_code == 422
    assert client.post(f"/api/late-early/{rid}/reject", json={},
                       headers=_h(token)).status_code == 422
    ok = client.post(f"/api/late-early/{rid}/reject", json={"note": "không hợp lý"},
                     headers=_h(token))
    assert ok.status_code == 200 and ok.json()["status"] == "rejected"
    assert ok.json()["decision_note"] == "không hợp lý"


# --- scope + quyền ----------------------------------------------------------


def test_to_truong_chi_thay_phieu_trong_to_minh(client):
    """Scope `department`: tổ trưởng KHÔNG thấy (⇒ không duyệt được) phiếu của phòng khác."""
    token = _admin_token(client)
    kd_emp = _make_emp(client, token, name="NV Kinh doanh ĐM", dept="Kinh doanh")
    sx_emp = _make_emp(client, token, name="Thợ Sản xuất ĐM", dept="Sản xuất")
    _mk(client, token, kd_emp, work_date="2026-07-17")
    _mk(client, token, sx_emp, work_date="2026-07-17")

    lead = _lead_token()
    seen = {x["employee_id"]
            for x in client.get("/api/late-early", headers=_h(lead)).json()["items"]}
    assert kd_emp not in seen        # ngoài tổ → không lộ
    assert sx_emp in seen            # trong tổ → thấy

    # Admin scope `all` thì thấy cả hai.
    all_seen = {x["employee_id"]
                for x in client.get("/api/late-early", headers=_h(token)).json()["items"]}
    assert {kd_emp, sx_emp} <= all_seen


def test_roster_cho_to_truong_khong_can_quyen_nhan_su(client):
    """Tổ trưởng SX có `di_muon:approve` nhưng KHÔNG có module `nhan_su` ⇒ `/api/employees` và
    `/api/attendance/shifts` đều 403 với họ. Không có roster riêng thì nút "Khai hộ thợ" hỏng
    với đúng người được giao dùng nó, và không suy được kiểu vắng (thiếu khung ca)."""
    token = _admin_token(client)
    kd_emp = _make_emp(client, token, name="NV KD Roster", dept="Kinh doanh")
    sx_emp = _make_emp(client, token, name="Thợ SX Roster", dept="Sản xuất")
    lead = _lead_token()

    # Tiền đề: 2 endpoint cũ thật sự đóng với tổ trưởng.
    assert client.get("/api/employees", headers=_h(lead)).status_code == 403
    assert client.get("/api/attendance/shifts", headers=_h(lead)).status_code == 403

    r = client.get("/api/late-early/roster", headers=_h(lead))
    assert r.status_code == 200, r.text
    ids = {e["id"] for e in r.json()["employees"]}
    assert sx_emp in ids and kd_emp not in ids       # roster BÁM scope di_muon
    assert "shifts" in r.json()                       # đủ khung ca để suy kiểu vắng

    # Không có quyền duyệt ⇒ không có roster (đây là danh sách người khác).
    assert client.get("/api/late-early/roster",
                      headers=_h(_plain_token_with_emp(client, token))).status_code == 403


def _pending_for(eid: int, *, work_date: str, frm=480, to=600) -> dict:
    """Phiếu CHỜ DUYỆT cho NV bất kỳ — ghi thẳng qua repo (không endpoint nào làm được việc này:
    `/me` tạo cho người đăng nhập, khai hộ thì duyệt luôn)."""
    from datetime import date as _date

    from app.repositories.late_early_repo import LateEarlyRepository
    db = SessionLocal()
    try:
        r = LateEarlyRepository(db).create_request(
            employee_id=eid, work_date=_date.fromisoformat(work_date), from_minute=frm,
            to_minute=to, reason="test", status="pending", created_by=None,
        )
        return {"id": r.id}
    finally:
        db.close()


def test_to_truong_khong_ghi_duoc_vao_to_khac(client):
    """⭐ Scope phải chặn cả đường GHI, không chỉ đường ĐỌC.

    Ô quyền `approve` chỉ nói "được duyệt", scope mới nói "được duyệt CHO AI". Thiếu chốt này
    thì tổ trưởng tổ A khai hộ + duyệt + hủy được phiếu của người tổ B — mà chính họ KHÔNG thấy
    phiếu đó trên màn của mình. Phiếu duyệt là dữ liệu RA TIỀN: miễn phạt, hoàn công, trừ quỹ
    phép năm."""
    token = _admin_token(client)
    kd_emp = _make_emp(client, token, name="NV KD Ngoài Tổ", dept="Kinh doanh")
    lead = _lead_token()

    # 1. Khai hộ người NGOÀI tổ → 403 (trước đây ra 201 + approved luôn).
    _mk(client, lead, kd_emp, work_date="2026-07-18", expect=403)

    # 2. Duyệt / từ chối phiếu NGOÀI tổ → 403. Phiếu CHỜ DUYỆT cho NV bất kỳ phải ghi thẳng qua
    #    repo: `/me` chỉ tạo cho người đăng nhập, còn khai hộ thì duyệt luôn.
    pend = _pending_for(kd_emp, work_date="2026-07-19")
    assert client.post(f"/api/late-early/{pend['id']}/approve", json={"note": None},
                       headers=_h(lead)).status_code == 403
    assert client.post(f"/api/late-early/{pend['id']}/reject", json={"note": "không"},
                       headers=_h(lead)).status_code == 403

    # 3. Duyệt cả mẻ: phiếu ngoài tổ rơi vào `skipped`, KHÔNG bị duyệt lén.
    bulk = client.post("/api/late-early/bulk-approve", json={"ids": [pend["id"]]},
                       headers=_h(lead))
    assert bulk.status_code == 200 and bulk.json()["done"] == []
    assert client.get("/api/late-early", headers=_h(token)).json()["items"]

    # 4. Hủy hộ phiếu ngoài tổ → 403.
    assert client.post(f"/api/late-early/{pend['id']}/cancel",
                       headers=_h(lead)).status_code == 403

    # Phiếu vẫn nguyên trạng thái chờ duyệt sau cả 4 phép thử.
    still = next(x for x in client.get("/api/late-early", headers=_h(token)).json()["items"]
                 if x["id"] == pend["id"])
    assert still["status"] == "pending"

    # Đối chứng: cùng thao tác trong tổ mình thì CHẠY.
    sx_emp = _make_emp(client, token, name="Thợ SX Trong Tổ", dept="Sản xuất")
    assert _mk(client, lead, sx_emp, work_date="2026-07-18")["status"] == "approved"


def _plain_token_with_emp(client, admin_token) -> str:
    """Tài khoản vai 'NV Sales' — KHÔNG có ô quyền `di_muon` nào, đã gắn hồ sơ nhân viên."""
    eid = _make_emp(client, admin_token, name="NV thường ĐM", dept="Kinh doanh")
    db = SessionLocal()
    try:
        users = UserRepository(db)
        u = users.get_by_username("nv-thuong-dm")
        if u is None:
            kd = DepartmentRepository(db).get_by_name("Kinh doanh")
            role = RoleRepository(db).get_by_name_and_department("NV Sales", kd.id)
            u = users.create(username="nv-thuong-dm", name="NV thường",
                             password_hash=hash_password("x"))
            users.set_assignment(u, department_id=kd.id, role_id=role.id, is_active=True)
        emps = EmployeeRepository(db)
        emps.update(emps.get_by_id(eid), user_id=u.id)
        return create_access_token(str(u.id))
    finally:
        db.close()


def test_tu_phuc_vu_khong_can_o_quyen(client):
    """Mọi NLĐ đều phải XIN / SỬA / HỦY được phiếu của CHÍNH MÌNH mà không cần ô quyền
    `di_muon` nào. Nhưng DUYỆT thì vẫn phải có `approve`, và màn danh sách vẫn cần `read`."""
    admin = _admin_token(client)
    t = _plain_token_with_emp(client, admin)

    r = _me(client, t, work_date="2026-07-23", frm=480, to=540)
    rid = r["id"]
    assert r["status"] == "pending"

    mine = client.get("/api/late-early/me", headers=_h(t)).json()
    assert mine["has_employee"] is True and any(x["id"] == rid for x in mine["items"])

    # Tự SỬA phiếu chưa duyệt của mình.
    upd = client.put(f"/api/late-early/{rid}",
                     json={"work_date": "2026-07-23", "from_minute": 480, "to_minute": 600},
                     headers=_h(t))
    assert upd.status_code == 200, upd.text
    # Tự HỦY phiếu chưa duyệt của mình.
    ok = client.post(f"/api/late-early/{rid}/cancel", headers=_h(t))
    assert ok.status_code == 200 and ok.json()["status"] == "cancelled"

    # Nhưng KHÔNG tự duyệt được, và KHÔNG thấy màn danh sách toàn phòng.
    r2 = _me(client, t, work_date="2026-07-24", frm=480, to=540)
    assert client.post(f"/api/late-early/{r2['id']}/approve", json={},
                       headers=_h(t)).status_code == 403
    assert client.get("/api/late-early", headers=_h(t)).status_code == 403
    # Badge người duyệt cũng không lộ số cho người không phận sự.
    assert client.get("/api/late-early/summary",
                      headers=_h(t)).json()["pending_in_scope"] is None


# --- nhánh TRỪ PHÉP ---------------------------------------------------------


def test_tru_phep_lam_tron_nua_ngay(client):
    """⭐ Tick 'trừ vào phép năm' → quy phút vắng ra ngày phép, làm tròn LÊN 0,5.

    Ca HC 08:00–17:00 (khung 540'): vắng ≤ NỬA ca → 0,5 ngày; vượt nửa ca → 1,0 ngày.
    Không tick thì quỹ phép không đụng (`leave_cong` = 0)."""
    token = _admin_token(client)
    tid = _mk_leave_type(client, token, "Phép năm ĐM", quota=12)
    eid = _make_emp(client, token, name="NV Trừ Phép ĐM")
    _assign_hc_shift(client, token, eid, name="HC trừ phép")

    # Vắng 2 tiếng (120' / 540' = 0,22 ≤ nửa ca) → 0,5 ngày phép.
    half = _mk(client, token, eid, work_date="2026-07-06", frm=480, to=600, leave_type_id=tid)
    assert half["leave_type_id"] == tid and half["leave_type_name"] == "Phép năm ĐM"
    assert half["leave_cong"] == 0.5

    # Vắng 6 tiếng (360' / 540' = 0,67 > nửa ca) → 1,0 ngày phép.
    full = _mk(client, token, eid, work_date="2026-07-07", frm=480, to=840, leave_type_id=tid)
    assert full["leave_cong"] == 1.0

    # Không tick → không đụng quỹ phép.
    none = _mk(client, token, eid, work_date="2026-07-08", frm=480, to=600)
    assert none["leave_type_id"] is None and none["leave_cong"] == 0


def test_het_phep_ma_van_tick_thi_chan(client):
    """⭐ Hết phép mà vẫn tick 'trừ vào phép năm' → 400, thông điệp nói rõ còn mấy ngày.

    Bỏ tick thì vẫn xin được (nhánh không lương) — người ta không bị kẹt cứng."""
    token = _admin_token(client)
    tid = _mk_leave_type(client, token, "Phép năm cạn", quota=1)
    eid = _make_emp(client, token, name="NV Hết Phép ĐM")
    _assign_hc_shift(client, token, eid, name="HC hết phép")

    # Tiêu trọn 1 ngày phép của cả năm.
    used = _mk(client, token, eid, work_date="2026-07-06", frm=480, to=840, leave_type_id=tid)
    assert used["leave_cong"] == 1.0

    blocked = client.post("/api/late-early",
                          json={"employee_id": eid, "work_date": "2026-07-07",
                                "from_minute": 480, "to_minute": 600, "leave_type_id": tid},
                          headers=_h(token))
    assert blocked.status_code == 400, blocked.text
    detail = blocked.json()["detail"]
    assert "Không đủ phép năm" in detail
    assert "còn lại 0 ngày" in detail          # nói rõ số ngày còn lại

    # Bỏ tick → vẫn xin được, chỉ là mất công phần vắng.
    ok = _mk(client, token, eid, work_date="2026-07-07", frm=480, to=600)
    assert ok["leave_cong"] == 0 and ok["status"] == "approved"


# --- badge + chuông ---------------------------------------------------------


def test_summary_badge_va_chuong(client):
    """`pending_in_scope` nuôi badge người duyệt; `my_decided_unseen` nuôi chuông người nộp,
    tắt sau khi bấm 'mark-seen'."""
    token = _admin_token(client)
    rid = _me(client, token, work_date="2026-07-22", frm=480, to=540)["id"]
    assert client.get("/api/late-early/summary",
                      headers=_h(token)).json()["pending_in_scope"] >= 1

    client.post(f"/api/late-early/{rid}/approve", json={}, headers=_h(token))
    s = client.get("/api/late-early/summary", headers=_h(token)).json()
    assert s["pending_in_scope"] == 0 and s["my_decided_unseen"] >= 1

    assert client.post("/api/late-early/mark-seen", headers=_h(token)).status_code == 204
    assert client.get("/api/late-early/summary",
                      headers=_h(token)).json()["my_decided_unseen"] == 0
