"""MỘT định nghĩa "biên chế" cho cả 5 phân hệ — bản rà liên thông (08/09/2026), nhóm gốc 1.

Trước đó chấm công/phép nhìn 2 cột `hire_date`/`resign_date` + phòng hiện tại, lương suy theo
`employee_events`. Các ca biên đã chứng minh bằng số ở bản rà: A1 A2 A4 A5 A8 C1 C2 D10.
"""
from __future__ import annotations

from datetime import date, timedelta

from app.db import SessionLocal
from app.repositories.leave_repo import LeaveRepository
from tests.test_cua_tu_ky_08_09 import _vai_rieng
from tests.test_lo_quyen_tang_ca import _noi_ho_so
from tests.test_ra_soat_nhan_su_luong_07_09 import (
    NAM, THANG, _bam_du_thang, _ca, _dept_id, _gen, _h, _khai_luong, _line, _nv,
)


def _chuyen(client, h, eid: int, kind: str, eff: str, **extra):
    return client.post(f"/api/employees/{eid}/transitions",
                       json={"kind": kind, "effective_date": eff, **extra}, headers=h)


def _le(client, h, ngay: str, ten="Lễ thử") -> None:
    r = client.post("/api/calendar/special-days",
                    json={"day": ngay, "kind": "off", "name": ten, "is_paid": True}, headers=h)
    assert r.status_code == 201, r.text


def _bang_cong(client, h, eid: int, thang: int) -> dict | None:
    ts = client.get(f"/api/attendance/timesheet?year={NAM}&month={thang}", headers=h).json()
    return next((r for r in ts["rows"] if r["employee_id"] == eid), None)


def _tai_khoan_cua(client, h, eid: int, username: str) -> str:
    uid, tok = _vai_rieng(username, "Kinh doanh", {
        "cham_cong": dict(can_read=True, can_create=True, scope="own"),
    })
    _noi_ho_so(client, h["Authorization"].split(" ", 1)[1], eid, uid)
    return tok


def _diem(client, h) -> None:
    client.post("/api/attendance/locations",
                json={"name": "Xưởng", "latitude": 10.0, "longitude": 106.0, "radius_m": 300}, headers=h)


# --- A1/A6: ngày hiệu lực tương lai ------------------------------------------------------------


def test_chuyen_trang_thai_ngay_tuong_lai_bi_chan(client):
    h = _h(client)
    e = _nv(client, h, "A1", "Kinh doanh")
    mai = (date.today() + timedelta(days=20)).isoformat()
    r = _chuyen(client, h, e, "resign", mai, resign_reason="x")
    assert r.status_code == 400 and "sau hôm nay" in r.json()["detail"], r.text
    r = _chuyen(client, h, e, "transfer", mai, new_department_id=_dept_id("Kho"))
    assert r.status_code == 400 and "sau hôm nay" in r.json()["detail"], r.text
    # Hồ sơ không đổi gì.
    hs = client.get(f"/api/employees/{e}", headers=h).json()
    assert hs["status"] == "active" and hs["resign_date"] is None
    # Hôm nay thì vẫn được như cũ.
    assert _chuyen(client, h, e, "resign", date.today().isoformat(), resign_reason="x").status_code == 200


# --- A2: tuyển lại — tháng trống giữa hai lần làm ---------------------------------------------


def test_tuyen_lai_thang_trong_khong_cong_le_khong_dong_luong(client):
    h = _h(client)
    e = _nv(client, h, "A2", "Kinh doanh")
    _khai_luong(client, h, e)
    _bam_du_thang(client, h, e, den=9)
    _le(client, h, f"{NAM}-07-15")
    assert _chuyen(client, h, e, "resign", f"{NAM}-06-10", resign_reason="x").status_code == 200
    assert _chuyen(client, h, e, "reinstate", f"{NAM}-08-03").status_code == 200
    # Tháng 7 nằm trọn trong khoảng trống: không hàng bảng công, không dòng lương (trước: 1 công lễ
    # + phụ cấp = 700.000).
    assert _bang_cong(client, h, e, 7) is None
    assert all(l["employee_id"] != e for l in _gen(client, h, month=7))
    # Tháng 6 vẫn có: 8 ngày làm (1–9/6 trừ CN 7/6), không thêm gì sau ngày nghỉ.
    row = _bang_cong(client, h, e, 6)
    assert row is not None and row["total_cong"] == 8.0
    assert _line(_gen(client, h), e)["actual_cong"] == 8.0


# --- A4: nghỉ dài hạn / đình chỉ = ngoài biên chế ---------------------------------------------


def test_nghi_dai_han_khong_cong_le_khong_bam_gio(client):
    h = _h(client)
    e = _nv(client, h, "A4", "Kinh doanh")
    _khai_luong(client, h, e)
    tok = _tai_khoan_cua(client, h, e, "nv-nghi-dai-han")
    _diem(client, h)
    sid = _ca(client, h)
    client.put(f"/api/employees/{e}/shift", json={"default_shift_id": sid, "effective_from": "2020-01-01"}, headers=h)
    _le(client, h, f"{NAM}-06-10")
    assert _chuyen(client, h, e, "leave_start", f"{NAM}-05-01").status_code == 200
    # Cả tháng 6 nghỉ dài hạn: không hàng, không dòng lương (trước: 1 công lễ = 416.000).
    assert _bang_cong(client, h, e, 6) is None
    assert all(l["employee_id"] != e for l in _gen(client, h))
    # Thẻ chấm công nói thẳng lý do; bấm giờ bị chặn.
    st = client.get("/api/attendance/me/status", headers={"Authorization": f"Bearer {tok}"}).json()
    assert st["can_check"] is False and "nghỉ dài hạn" in st["check_block_reason"]
    r = client.post("/api/attendance/check", json={"latitude": 10.0, "longitude": 106.0},
                    headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 400 and "nghỉ dài hạn" in r.json()["detail"], r.text
    # Đi làm lại hôm nay ⇒ hết lý do biên chế (còn lại chỉ là chuyện giờ ca).
    assert _chuyen(client, h, e, "leave_end", date.today().isoformat()).status_code == 200
    st = client.get("/api/attendance/me/status", headers={"Authorization": f"Bearer {tok}"}).json()
    assert "nghỉ dài hạn" not in (st["check_block_reason"] or "")


def test_dinh_chi_bam_gio_bi_chan(client):
    h = _h(client)
    e = _nv(client, h, "A4b", "Kinh doanh")
    tok = _tai_khoan_cua(client, h, e, "nv-dinh-chi")
    _diem(client, h)
    client.put(f"/api/employees/{e}/shift", json={"default_shift_id": _ca(client, h), "effective_from": "2020-01-01"}, headers=h)
    assert _chuyen(client, h, e, "suspend", date.today().isoformat()).status_code == 200
    r = client.post("/api/attendance/check", json={"latitude": 10.0, "longitude": 106.0},
                    headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 400 and "đình chỉ" in r.json()["detail"], r.text


# --- A5 / C1 / C2 / D10: ngày sau nghỉ việc ---------------------------------------------------


def test_cham_bu_don_phep_phieu_tang_ca_sau_ngay_nghi_viec_bi_chan(client):
    h = _h(client)
    e = _nv(client, h, "A5", "Kinh doanh")
    _khai_luong(client, h, e)
    _bam_du_thang(client, h, e, den=9)
    # Đơn phép treo (gửi TRƯỚC khi nghỉ) cho ngày 15/06.
    db = SessionLocal()
    try:
        lt = client.get("/api/leaves/types", headers=h).json()["items"]
        tid = lt[0]["id"] if lt else client.post("/api/leaves/types", json={
            "name": "Phép năm", "is_paid": True, "annual_quota": 12}, headers=h).json()["id"]
        treo = LeaveRepository(db).create_request(
            employee_id=e, leave_type_id=tid, start_date=date(NAM, 6, 15), end_date=date(NAM, 6, 15),
            days=1, reason="test", status="pending", created_by=None).id
    finally:
        db.close()
    assert _chuyen(client, h, e, "resign", f"{NAM}-06-10", resign_reason="x").status_code == 200
    # Chấm bù ngày 20/06 → 400 (trước: 200, thêm 1 công = 416.000).
    r = client.post("/api/attendance/adjust", json={"employee_id": e, "date": f"{NAM}-06-20",
                    "check_type": "in", "time": "08:00", "reason": "bù"}, headers=h)
    assert r.status_code == 400 and "đã nghỉ việc" in r.json()["detail"], r.text
    # Duyệt đơn phép 15/06 → 400 (trước: 200, trả 1 công).
    r = client.post(f"/api/leaves/{treo}/approve", json={}, headers=h)
    assert r.status_code == 400 and "đã nghỉ việc" in r.json()["detail"], r.text
    # Phiếu tăng ca tạo hộ ngày 15/06 → 400.
    r = client.post("/api/overtime", json={"employee_id": e, "work_date": f"{NAM}-06-15",
                    "from_minute": 1080, "to_minute": 1200, "reason": "x"}, headers=h)
    assert r.status_code == 400 and "đã nghỉ việc" in r.json()["detail"], r.text
    # Đơn treo của người đã nghỉ KHÔNG chặn chốt kỳ công (C2).
    st = client.get(f"/api/attendance/period?year={NAM}&month=6", headers=h).json()
    assert st.get("pending_leaves", 0) == 0
    assert client.post("/api/attendance/period/lock", json={"year": NAM, "month": 6}, headers=h).status_code == 200
    # Bảng công tháng 6 vẫn 8 công của những ngày đã làm.
    assert _bang_cong(client, h, e, 6)["total_cong"] == 8.0


# --- A8: nghỉ việc đúng ngày lễ ---------------------------------------------------------------


def test_nghi_viec_dung_ngay_le_khong_cong_le(client):
    h = _h(client)
    e = _nv(client, h, "A8", "Kinh doanh")
    _khai_luong(client, h, e)
    _le(client, h, f"{NAM}-06-26")
    _bam_du_thang(client, h, e, den=25)                     # 1–25/6 trừ 3 CN = 22 công
    assert _chuyen(client, h, e, "resign", f"{NAM}-06-26", resign_reason="x").status_code == 200
    row = _bang_cong(client, h, e, 6)
    assert row["total_cong"] == 22.0                        # trước: 23 (thêm 1 công lễ 416.000)
    assert _line(_gen(client, h), e)["actual_cong"] == 22.0


# --- A11: sửa ngày vào ------------------------------------------------------------------------


def test_hire_date_sua_duoc_qua_put(client):
    h = _h(client)
    e = _nv(client, h, "A11", "Kinh doanh")
    r = client.put(f"/api/employees/{e}", json={"full_name": "A11", "hire_date": "2021-05-05"}, headers=h)
    assert r.status_code == 200, r.text
    assert client.get(f"/api/employees/{e}", headers=h).json()["hire_date"] == "2021-05-05"
    r = client.put(f"/api/employees/{e}", json={"full_name": "A11", "hire_date": None}, headers=h)
    assert r.status_code in (400, 422)
