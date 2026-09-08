"""NGHỈ GIỮA CA (chủ chốt 07/09/2026 — Đợt 1, mục 1.1).

Chủ hỏi: *"tôi cấu hình 8h trên 1 ca thì lúc tạo ca trừ cả nghỉ giữa ca thì nó bằng 8h, hiện tại
không có đúng không?"* — đúng: ca 7:30–16:30 máy coi là khung 9 giờ, còn bảng lương tay chia cho 8.

Luật: khung tính công = (ra − vào) − nghỉ giữa ca; phút rơi vào khoảng nghỉ không là LÀM, cũng
không là TRỄ/SỚM. Ca không khai nghỉ thì y như cũ — ca đối chứng quan trọng nhất ở đây.
"""
from __future__ import annotations

from datetime import datetime, timezone

from app.db import SessionLocal
from app.repositories.attendance_repo import AttendanceRepository
from app.repositories.rbac_repo import DepartmentRepository
from app.services.attendance_service import VN_TZ, _khung_nghi, compute_day_cong

ADMIN = {"username": "admin", "password": "admin123"}
NAM, THANG = 2026, 6          # 01/06/2026 = Thứ Hai, đã qua so với hôm nay ⇒ không dính "ngày chưa tới"

# Ca 7:30–16:30 (450 → 990), nghỉ trưa 11:30–12:30 (690 → 750) — đúng nội quy SVN.
CA = dict(start_min=450, end_min=990, is_overnight=False, grace_min=5)
NGHI = dict(break_start_min=690, break_end_min=750)


# ══════════════════════════════════════════════ công thức thuần


def test_khung_nghi_ca_ngay_va_ca_dem():
    assert _khung_nghi(450, False, 690, 750) == (690, 750)
    assert _khung_nghi(450, False, None, None) is None
    assert _khung_nghi(450, False, 750, 690) is None          # kết thúc trước bắt đầu ⇒ bỏ
    # Ca đêm 22:00–06:00: mốc nhỏ hơn giờ vào ca là rơi sang hôm sau.
    assert _khung_nghi(1320, True, 120, 150) == (1560, 1590)  # 02:00–02:30
    assert _khung_nghi(1320, True, 1410, 0) == (1410, 1440)   # 23:30–00:00


def test_khong_khai_nghi_thi_y_nhu_cu():
    """Ca đối chứng: không khai nghỉ ⇒ mẫu số 540' như trước (8:00–17:00 vào 8:30 = 0,94)."""
    v = compute_day_cong(start_min=480, end_min=1020, is_overnight=False, grace_min=5,
                         first_in_min=510, main_out_min=1020)
    assert v["cong"] == 0.94 and v["window_minutes"] == 540


def test_du_ca_bang_1_va_mau_so_480():
    v = compute_day_cong(**CA, **NGHI, first_in_min=450, main_out_min=990)
    assert v["cong"] == 1.0 and v["window_minutes"] == 480
    assert v["late_minutes"] == 0 and v["early_minutes"] == 0 and v["missing_minutes"] == 0


def test_lam_nua_buoi_sang_bang_0_5():
    """⭐ Ca gốc chủ nêu: sáng 7:30–11:30 = 240' làm trên 480' ⇒ 0,5 (trước đây 240/540 = 0,44)."""
    v = compute_day_cong(**CA, **NGHI, first_in_min=450, main_out_min=690)
    assert v["cong"] == 0.5
    assert v["early_minutes"] == 240        # 16:30 − 11:30 = 300' nhưng 60' rơi vào nghỉ trưa


def test_lam_nua_buoi_chieu_bang_0_5_va_tre_khong_tinh_gio_nghi():
    v = compute_day_cong(**CA, **NGHI, first_in_min=750, main_out_min=990)
    assert v["cong"] == 0.5 and v["late"] is True
    # Trễ = 12:30 − 7:35 = 295' nhưng 60' là giờ nghỉ trưa ⇒ 235' làm bị thiếu.
    assert v["late_minutes"] == 235


def test_ve_som_1h_bang_0_875_va_tre_1h():
    v = compute_day_cong(**CA, **NGHI, first_in_min=450, main_out_min=930)
    assert v["cong"] == 0.88 and v["early_minutes"] == 60        # round(420/480, 2)
    v2 = compute_day_cong(**CA, **NGHI, first_in_min=510, main_out_min=990)
    assert v2["cong"] == 0.88 and v2["late_minutes"] == 55       # trừ dung sai 5'


def test_ve_giua_gio_nghi_khong_bi_tinh_them():
    """Ra lúc 12:00 (giữa giờ nghỉ) = ra 11:30 về số công; phần 11:30–12:00 không phải giờ làm."""
    v = compute_day_cong(**CA, **NGHI, first_in_min=450, main_out_min=720)
    assert v["cong"] == 0.5 and v["early_minutes"] == 240


def test_ca_dem_co_nghi_vat_dem_tru_gio_dem():
    """Ca 22:00–06:00 nghỉ 02:00–02:30: khung 450', làm đủ = 1,0 và giờ đêm 480 − 30 = 450."""
    v = compute_day_cong(start_min=1320, end_min=360, is_overnight=True, grace_min=5,
                         break_start_min=120, break_end_min=150,
                         first_in_min=1320, main_out_min=360)
    assert v["cong"] == 1.0 and v["window_minutes"] == 450 and v["night_minutes"] == 450


def test_nghi_khai_lech_ngoai_khung_chi_tinh_phan_trong():
    """Khai nghỉ 16:00–17:30 cho ca 7:30–16:30 ⇒ chỉ 16:00–16:30 nằm trong ca ⇒ khung 510'."""
    v = compute_day_cong(**CA, break_start_min=960, break_end_min=1050,
                         first_in_min=450, main_out_min=990)
    assert v["window_minutes"] == 510 and v["cong"] == 1.0


# ══════════════════════════════════════════════ API + bảng công


def _h(client) -> dict[str, str]:
    tok = client.post("/api/auth/login", json=ADMIN).json()["access_token"]
    return {"Authorization": f"Bearer {tok}"}


def _dept_id(name: str) -> int:
    db = SessionLocal()
    try:
        return DepartmentRepository(db).get_by_name(name).id
    finally:
        db.close()


def _ca(client, h, **extra) -> dict:
    body = {"name": extra.pop("name", "Ca 7h30 nghỉ trưa"), "start_time": "07:30",
            "end_time": "16:30", **extra}
    r = client.post("/api/attendance/shifts", json=body, headers=h)
    assert r.status_code == 201, r.text
    return r.json()


def _nv(client, h, shift_id: int, *, ten="NV Nghỉ trưa") -> int:
    r = client.post("/api/employees",
                    json={"full_name": ten, "department_id": _dept_id("Hành chính nhân sự"),
                          "hire_date": "2020-01-01", "gender": "male", "status": "active"},
                    headers=h)
    assert r.status_code == 201, r.text
    eid = r.json()["employee"]["id"]
    assert client.put(f"/api/employees/{eid}/shift",
                      json={"default_shift_id": shift_id, "effective_from": "2020-01-01"},
                      headers=h).status_code == 200
    return eid


def _bam(eid: int, ngay: int, hh: int, mm: int, kieu: str) -> None:
    db = SessionLocal()
    try:
        AttendanceRepository(db).create_log(
            employee_id=eid, check_type=kieu, within_range=True,
            checked_at=datetime(NAM, THANG, ngay, hh, mm, tzinfo=VN_TZ).astimezone(timezone.utc))
    finally:
        db.close()


def _row(client, h, eid: int) -> dict:
    ts = client.get("/api/attendance/timesheet", params={"year": NAM, "month": THANG}, headers=h).json()
    return next(r for r in ts["rows"] if r["employee_id"] == eid)


def test_khai_ca_co_nghi_giua_ca_va_validate(client):
    h = _h(client)
    ca = _ca(client, h, break_start_time="11:30", break_end_time="12:30")
    assert ca["break_start_time"] == "11:30" and ca["break_end_time"] == "12:30"
    # Đọc lại danh sách vẫn có.
    items = client.get("/api/attendance/shifts", headers=h).json()["items"]
    assert next(s for s in items if s["id"] == ca["id"])["break_end_time"] == "12:30"
    # Sửa: bỏ nghỉ ⇒ None cả hai.
    r = client.put(f"/api/attendance/shifts/{ca['id']}",
                   json={"name": ca["name"], "start_time": "07:30", "end_time": "16:30"}, headers=h)
    assert r.status_code == 200 and r.json()["break_start_time"] is None
    # Chỉ khai một mốc ⇒ 400.
    r = client.post("/api/attendance/shifts",
                    json={"name": "Lệch", "start_time": "07:30", "end_time": "16:30",
                          "break_start_time": "11:30"}, headers=h)
    assert r.status_code == 400 and "đủ" in r.json()["detail"]
    # Nghỉ nằm ngoài khung ca ⇒ 400.
    r = client.post("/api/attendance/shifts",
                    json={"name": "Ngoài", "start_time": "07:30", "end_time": "16:30",
                          "break_start_time": "17:00", "break_end_time": "17:30"}, headers=h)
    assert r.status_code == 400 and "trong khung ca" in r.json()["detail"]
    # Ca đêm: nghỉ 02:00–02:30 hợp lệ (rơi sang hôm sau).
    r = client.post("/api/attendance/shifts",
                    json={"name": "Đêm", "start_time": "22:00", "end_time": "06:00",
                          "is_overnight": True, "break_start_time": "02:00",
                          "break_end_time": "02:30"}, headers=h)
    assert r.status_code == 201, r.text


def test_bang_cong_nua_buoi_0_5_va_gio_lam_tru_nghi(client):
    """Bảng công: sáng 7:30–11:30 ⇒ công 0,5 · giờ làm 4h; đủ ngày ⇒ 1,0 · giờ làm 8h (không 9h)."""
    h = _h(client)
    ca = _ca(client, h, break_start_time="11:30", break_end_time="12:30")
    e1 = _nv(client, h, ca["id"], ten="NV Sáng")
    e2 = _nv(client, h, ca["id"], ten="NV Đủ")
    _bam(e1, 1, 7, 30, "in"); _bam(e1, 1, 11, 30, "out")
    _bam(e2, 1, 7, 30, "in"); _bam(e2, 1, 16, 30, "out")
    r1, r2 = _row(client, h, e1), _row(client, h, e2)
    assert r1["days"]["1"]["cong"] == 0.5 and r1["days"]["1"]["hours"] == 4.0
    assert r2["days"]["1"]["cong"] == 1.0 and r2["days"]["1"]["hours"] == 8.0
    assert r1["total_cong"] == 0.5 and r2["total_hours"] == 8.0


def test_ca_khong_khai_nghi_bang_cong_y_nhu_cu(client):
    """Đối chứng ở tầng API: ca cùng giờ nhưng KHÔNG khai nghỉ ⇒ sáng = 240/540 = 0,44, giờ làm 4h."""
    h = _h(client)
    ca = _ca(client, h, name="Ca 7h30 không nghỉ")
    e1 = _nv(client, h, ca["id"])
    _bam(e1, 1, 7, 30, "in"); _bam(e1, 1, 11, 30, "out")
    d = _row(client, h, e1)["days"]["1"]
    assert d["cong"] == 0.44 and d["hours"] == 4.0


def test_o_biet_noi_cung_mau_so(client):
    """Chi tiết ngày (ô biết nói) đọc cùng công thức với bảng công."""
    h = _h(client)
    ca = _ca(client, h, break_start_time="11:30", break_end_time="12:30")
    e1 = _nv(client, h, ca["id"])
    _bam(e1, 1, 7, 30, "in"); _bam(e1, 1, 15, 30, "out")
    d = client.get("/api/attendance/day", params={"employee_id": e1, "date": f"{NAM}-{THANG:02d}-01"},
                   headers=h).json()
    assert d["cong"] == 0.88 and d["reason"] == "Về sớm"


def test_phieu_nua_buoi_quy_theo_khung_480(client):
    """Phiếu đi muộn/về sớm (module riêng) cũng chia cho 480': xin vắng 240' = đúng nửa ca ⇒ 0,5 ngày
    phép nếu tick trừ phép (nhánh này SVN không dùng, nhưng mẫu số phải chung một luật)."""
    from app.repositories.audit_repo import AuditLogRepository
    from app.repositories.employee_repo import EmployeeRepository
    from app.repositories.late_early_repo import LateEarlyRepository
    from app.services.late_early_service import LateEarlyService
    from datetime import date
    h = _h(client)
    ca = _ca(client, h, break_start_time="11:30", break_end_time="12:30")
    e1 = _nv(client, h, ca["id"])
    db = SessionLocal()
    try:
        svc = LateEarlyService(LateEarlyRepository(db), EmployeeRepository(db), AuditLogRepository(db),
                               attendance=AttendanceRepository(db))
        emp = EmployeeRepository(db).get_by_id(e1)
        assert svc._shift_window(emp, date(NAM, THANG, 1)) == 480
        assert svc._leave_cong_for(emp, date(NAM, THANG, 1), 240) == 0.5
    finally:
        db.close()


# ══════════════════════════════════════════════ ca phải khớp giờ công chuẩn (chủ chốt 07/09)


def _luat(client, h, *, bat: bool, gio: float = 8) -> None:
    r = client.put("/api/luong/params", json={"ca_khop_gio_chuan": bat, "standard_hours_per_day": gio},
                   headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["ca_khop_gio_chuan"] is bat


def _tao(client, h, **body):
    return client.post("/api/attendance/shifts",
                       json={"name": body.pop("name", "Ca thử"), **body}, headers=h)


def test_ca_phai_khop_gio_cong_chuan_khi_bat_luat(client):
    """*"Tôi cấu hình 8h/ca thì lúc tạo ca trừ nghỉ giữa ca phải bằng 8h."* — ca 9h không nghỉ bị chặn,
    khai nghỉ trưa 1h thì được; ca đêm 22–06 (8h) được; ca 5h bị chặn."""
    h = _h(client)
    _luat(client, h, bat=True, gio=8)
    r = _tao(client, h, start_time="08:00", end_time="17:00")
    assert r.status_code == 400, r.text
    assert "9 giờ" in r.json()["detail"] and "8 giờ" in r.json()["detail"]
    r = _tao(client, h, start_time="08:00", end_time="17:00",
             break_start_time="12:00", break_end_time="13:00")
    assert r.status_code == 201, r.text
    ca_id = r.json()["id"]
    r = _tao(client, h, name="Đêm", start_time="22:00", end_time="06:00", is_overnight=True)
    assert r.status_code == 201, r.text
    r = _tao(client, h, name="Nửa ngày", start_time="07:00", end_time="12:00")
    assert r.status_code == 400 and "5 giờ" in r.json()["detail"]
    # Sửa ca cũng qua cùng hàng rào: bỏ nghỉ trưa đi là 9h ⇒ chặn.
    r = client.put(f"/api/attendance/shifts/{ca_id}",
                   json={"name": "Ca thử", "start_time": "08:00", "end_time": "17:00"}, headers=h)
    assert r.status_code == 400
    # Danh sách ca báo mẫu số đang áp cho màn Khai ca.
    lst = client.get("/api/attendance/shifts", headers=h).json()
    assert lst["gio_cong_chuan"] == 8 and lst["ca_khop_gio_chuan"] is True


def test_tat_luat_thi_ca_le_gio_van_luu_duoc(client):
    h = _h(client)
    _luat(client, h, bat=False)
    r = _tao(client, h, start_time="08:00", end_time="17:00")
    assert r.status_code == 201, r.text
    assert client.get("/api/attendance/shifts", headers=h).json()["ca_khop_gio_chuan"] is False


def test_gio_chuan_khac_8_thi_so_theo_so_do(client):
    """Xưởng khai giờ công chuẩn 7,5h: ca 7:30–16:00 nghỉ 1h = 7,5h được; 8h thì không."""
    h = _h(client)
    _luat(client, h, bat=True, gio=7.5)
    r = _tao(client, h, start_time="07:30", end_time="16:00",
             break_start_time="11:30", break_end_time="12:30")
    assert r.status_code == 201, r.text
    r = _tao(client, h, name="8 tiếng", start_time="07:30", end_time="16:30",
             break_start_time="11:30", break_end_time="12:30")
    assert r.status_code == 400 and "7 giờ 30" in r.json()["detail"]
