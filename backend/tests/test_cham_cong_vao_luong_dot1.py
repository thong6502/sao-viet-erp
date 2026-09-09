"""ĐẦU-CUỐI Đợt 1 (07/09/2026): chấm công (ca có nghỉ giữa ca) + phép có lương + tăng ca (từng phiên,
vắt nửa đêm, xác nhận theo phiếu) → `/api/luong/generate` ra đúng số.

Chủ hỏi: *"kiểm tra cho tôi chấm công, phép, tăng ca nó đã đi vào lương đúng chưa"*. Test này đi đúng
đường thật: lượt bấm → Bảng công tháng → metrics → engine Lương, không bơm số vào engine.
"""
from __future__ import annotations

from datetime import date, datetime, timezone

from app.db import SessionLocal
from app.repositories.attendance_repo import AttendanceRepository
from app.repositories.leave_repo import LeaveRepository
from app.repositories.rbac_repo import DepartmentRepository
from app.services.attendance_service import VN_TZ

ADMIN = {"username": "admin", "password": "admin123"}
NAM, THANG = 2026, 6          # tháng 6/2026: T2–T7 = 26 ngày làm việc ⇒ công chuẩn 26 (số tròn)


def _h(client) -> dict[str, str]:
    tok = client.post("/api/auth/login", json=ADMIN).json()["access_token"]
    return {"Authorization": f"Bearer {tok}"}


def _dept_id(name: str) -> int:
    db = SessionLocal()
    try:
        return DepartmentRepository(db).get_by_name(name).id
    finally:
        db.close()


def _ngay(d: int) -> str:
    return f"{NAM}-{THANG:02d}-{d:02d}"


def _bam(eid: int, ngay: int, hh: int, mm: int, kieu: str) -> None:
    db = SessionLocal()
    try:
        AttendanceRepository(db).create_log(
            employee_id=eid, check_type=kieu, within_range=True,
            checked_at=datetime(NAM, THANG, ngay, hh, mm, tzinfo=VN_TZ).astimezone(timezone.utc))
    finally:
        db.close()


def _dung_nv(client, h) -> int:
    """NV chính thức, lương vị trí 10.400.000 ⇒ 400.000/công, đơn giá giờ tăng ca 50.000 (÷26÷8)."""
    r = client.post("/api/employees",
                    json={"full_name": "NV Đầu cuối", "department_id": _dept_id("Hành chính nhân sự"),
                          "hire_date": "2020-01-01", "gender": "male", "status": "active",
                          "probation_end_date": "2020-03-01"},
                    headers=h)
    assert r.status_code == 201, r.text
    eid = r.json()["employee"]["id"]
    r = client.post(f"/api/luong/salaries/{eid}",
                    json={"effective_from": "2026-01-01", "luong_vi_tri": 10_400_000}, headers=h)
    assert r.status_code in (200, 201), r.text
    ca = client.post("/api/attendance/shifts",
                     json={"name": "Ca 7h30 nghỉ trưa", "start_time": "07:30", "end_time": "16:30",
                           "break_start_time": "11:30", "break_end_time": "12:30"}, headers=h)
    assert ca.status_code == 201, ca.text
    assert client.put(f"/api/employees/{eid}/shift",
                      json={"default_shift_id": ca.json()["id"], "effective_from": "2020-01-01"},
                      headers=h).status_code == 200
    return eid


def _phieu(client, h, eid: int, ngay: int, tu: int, den: int) -> None:
    r = client.post("/api/overtime",
                    json={"employee_id": eid, "work_date": _ngay(ngay), "from_minute": tu,
                          "to_minute": den, "reason": "đầu cuối"}, headers=h)
    assert r.status_code == 201, r.text


def _phep_co_luong(client, h, eid: int, ngay: int) -> None:
    tid = client.post("/api/leaves/types",
                      json={"name": "Phép năm", "is_paid": True, "annual_quota": 12},
                      headers=h).json()["id"]
    db = SessionLocal()
    try:
        r = LeaveRepository(db).create_request(
            employee_id=eid, leave_type_id=tid, start_date=date(NAM, THANG, ngay),
            end_date=date(NAM, THANG, ngay), days=1, reason="đầu cuối", status="pending",
            created_by=None)
        rid = r.id
    finally:
        db.close()
    assert client.post(f"/api/leaves/{rid}/approve", json={}, headers=h).status_code == 200


def test_cham_cong_phep_tang_ca_vao_luong(client):
    h = _h(client)
    eid = _dung_nv(client, h)

    # 01/06 (T2): chỉ làm sáng 07:30–11:30 ⇒ 0,5 công (mẫu số 8h).
    _bam(eid, 1, 7, 30, "in"); _bam(eid, 1, 11, 30, "out")
    # 02/06 (T3): đủ ca + phiếu 17:00–21:30, HAI phiên tăng ca 17:00–18:00 và 18:30–21:30 ⇒ 240'
    # (khe 30' không trả; gộp dải cũ sẽ ra 270').
    _bam(eid, 2, 7, 30, "in"); _bam(eid, 2, 16, 30, "out")
    _bam(eid, 2, 17, 0, "in"); _bam(eid, 2, 18, 0, "out")
    _bam(eid, 2, 18, 30, "in"); _bam(eid, 2, 21, 30, "out")
    _phieu(client, h, eid, 2, 1020, 1290)
    # 03/06 (T4): đủ ca, phiếu 17:30 → 02:00 hôm sau nhưng QUÊN cặp bấm ⇒ xác nhận theo phiếu ⇒ 510'.
    _bam(eid, 3, 7, 30, "in"); _bam(eid, 3, 16, 30, "out")
    _phieu(client, h, eid, 3, 1050, 1560)
    r = client.post("/api/attendance/ot-confirm", json={"date": _ngay(3), "employee_ids": [eid]}, headers=h)
    assert r.status_code == 200 and len(r.json()["done"]) == 1, r.text
    # 04/06 (T5): nghỉ phép có lương.
    _phep_co_luong(client, h, eid, 4)

    # --- Bảng công tháng: số công/tăng ca từng ngày đúng trước khi sang Lương ---
    ts = client.get("/api/attendance/timesheet", params={"year": NAM, "month": THANG}, headers=h).json()
    row = next(x for x in ts["rows"] if x["employee_id"] == eid)
    assert row["days"]["1"]["cong"] == 0.5 and row["days"]["1"]["hours"] == 4.0
    assert row["days"]["2"]["cong"] == 1.0 and row["days"]["2"]["ot_minutes"] == 240
    assert row["days"]["3"]["cong"] == 1.0 and row["days"]["3"]["ot_minutes"] == 510
    assert row["days"]["4"]["leave"] == "Phép năm" and row["days"]["4"]["leave_paid"] is True
    assert row["total_cong"] == 3.5 and row["paid_leave_days"] == 1
    assert ts["standard_cong"] == 26

    # --- Lương: đúng đường metrics ⇒ engine ---
    gen = client.post("/api/luong/generate", json={"year": NAM, "month": THANG}, headers=h)
    assert gen.status_code == 200, gen.text
    line = next(x for x in gen.json()["lines"] if x["employee_id"] == eid)
    assert line["standard_cong"] == 26
    assert line["actual_cong"] == 3.5                       # 0,5 + 1 + 1 (làm) + 1 (phép có lương)
    assert line["paid_leave_cong"] == 1.0
    assert line["luong_cong"] == 3.5 * 400_000              # 1.400.000 — ngày phép cùng đơn giá công
    assert line["ot_minutes"] == 750                        # 240 + 510
    assert line["ot_pay"] == 50_000 * 1.5 * 750 / 60        # 937.500 — 12,5 giờ × 150% (ngày thường)
    # Phiếu 03/06 có 22:00–02:00 là 4 giờ TĂNG CA ĐÊM ⇒ (30% + 20%×1,0) × đơn giá giờ.
    assert line["night_premium_pay"] == 50_000 * 4 * 0.5    # 100.000


def test_ca_khong_khai_nghi_van_ra_luong_nhu_cu(client):
    """Đối chứng: ca 08:00–17:00 KHÔNG khai nghỉ (khung 9h, luật khớp giờ chuẩn tắt trong test) —
    làm sáng 08:00–12:00 = 240/540 = 0,44 công như trước 07/09, để chắc engine không đổi số của ai."""
    h = _h(client)
    r = client.post("/api/employees",
                    json={"full_name": "NV Cũ", "department_id": _dept_id("Hành chính nhân sự"),
                          "hire_date": "2020-01-01", "gender": "male", "status": "active",
                          "probation_end_date": "2020-03-01"}, headers=h)
    eid = r.json()["employee"]["id"]
    client.post(f"/api/luong/salaries/{eid}",
                json={"effective_from": "2026-01-01", "luong_vi_tri": 10_400_000}, headers=h)
    ca = client.post("/api/attendance/shifts",
                     json={"name": "HC 9h", "start_time": "08:00", "end_time": "17:00"}, headers=h).json()
    client.put(f"/api/employees/{eid}/shift",
               json={"default_shift_id": ca["id"], "effective_from": "2020-01-01"}, headers=h)
    _bam(eid, 1, 8, 0, "in"); _bam(eid, 1, 12, 0, "out")
    gen = client.post("/api/luong/generate", json={"year": NAM, "month": THANG}, headers=h).json()
    line = next(x for x in gen["lines"] if x["employee_id"] == eid)
    assert line["actual_cong"] == 0.44 and line["luong_cong"] == 0.44 * 400_000
