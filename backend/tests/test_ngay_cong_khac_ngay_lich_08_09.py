"""Ngày công ≠ ngày lịch — bản rà liên thông (08/09/2026), nhóm gốc 3: B7/D6 (đếm "phát sinh sau
chốt" theo ngày công), D7 (xoá lượt bù guard theo ngày công), A10 (ca qua đêm ở ngày biên vào làm).
"""
from __future__ import annotations

from datetime import datetime, timezone

from app.db import SessionLocal
from app.repositories.attendance_repo import AttendanceRepository
from app.services.attendance_service import VN_TZ
from tests.test_chan_ghi_khi_ky_cong_da_chot import _chot_cong
from tests.test_ra_soat_nhan_su_luong_07_09 import NAM, _bam_du_thang, _gen, _h, _khai_luong, _nv


def _bam(eid: int, y: int, m: int, d: int, hh: int, mm: int, kieu: str) -> None:
    db = SessionLocal()
    try:
        AttendanceRepository(db).create_log(
            employee_id=eid, check_type=kieu, within_range=True,
            checked_at=datetime(y, m, d, hh, mm, tzinfo=VN_TZ).astimezone(timezone.utc))
    finally:
        db.close()


def _ca_dem(client, h) -> int:
    items = client.get("/api/attendance/shifts", headers=h).json().get("items", [])
    sid = next((s["id"] for s in items if s["name"] == "Đêm 22-06 (rà)"), None)
    if sid is None:
        r = client.post("/api/attendance/shifts", json={"name": "Đêm 22-06 (rà)", "start_time": "22:00",
                                                        "end_time": "06:00", "is_overnight": True}, headers=h)
        assert r.status_code == 201, r.text
        sid = r.json()["id"]
    return sid


def test_bam_vao_sang_mung_1_thang_sau_khong_chan_chot_luong_thang_truoc(client):
    """B7/D6: chốt công 31/8 chiều, sáng 1/9 cả xưởng bấm VÀO ⇒ trước đây `phat_sinh_sau_chot` tháng 8
    = số người bấm, L8 chặn chốt lương tháng 8 với thông điệp sai."""
    h = _h(client)
    e = _nv(client, h, "B7", "Kinh doanh")
    _khai_luong(client, h, e)
    _bam_du_thang(client, h, e, thang=8, den=31)
    _chot_cong(client, h, nam=NAM, thang=8)
    _bam(e, NAM, 9, 1, 8, 0, "in")                       # ghi SAU chốt, ngày công 01/09
    st = client.get(f"/api/attendance/period?year={NAM}&month=8", headers=h).json()
    assert st["phat_sinh_sau_chot"] == 0, st
    _gen(client, h, month=8)
    assert client.post("/api/luong/lock", json={"year": NAM, "month": 8}, headers=h).status_code == 200
    # Đối chứng: lượt ghi sau chốt mà NGÀY CÔNG thuộc tháng 8 thì vẫn phải đếm.
    _bam(e, NAM, 8, 31, 8, 0, "in")
    st = client.get(f"/api/attendance/period?year={NAM}&month=8", headers=h).json()
    assert st["phat_sinh_sau_chot"] == 1, st


def test_xoa_luot_bu_rang_sang_thuoc_thang_da_chot_bi_chan(client):
    """D7: RA 06:00 ngày 1/7 của ca đêm 30/6 — tháng 6 đã chốt thì không xoá được (trước: 200 vì
    guard nhìn ngày lịch 1/7 còn mở)."""
    h = _h(client)
    e = _nv(client, h, "D7", "Kinh doanh")
    _khai_luong(client, h, e)
    sid = _ca_dem(client, h)
    r = client.put(f"/api/employees/{e}/shift", json={"default_shift_id": sid, "effective_from": "2020-01-01"}, headers=h)
    assert r.status_code == 200, r.text
    r = client.post("/api/attendance/adjust", json={"employee_id": e, "date": f"{NAM}-06-30", "check_type": "in",
                    "time": "22:00", "reason": "bù"}, headers=h)
    assert r.status_code == 200, r.text
    r = client.post("/api/attendance/adjust", json={"employee_id": e, "date": f"{NAM}-06-30", "check_type": "out",
                    "time": "06:00", "next_day": True, "reason": "bù"}, headers=h)
    assert r.status_code == 200, r.text
    ra = next(p for p in r.json()["punches"] if p["check_type"] == "out")
    _chot_cong(client, h, nam=NAM, thang=6)
    r = client.delete(f"/api/attendance/logs/{ra['id']}", params={"employee_id": e, "date": f"{NAM}-07-01"}, headers=h)
    assert r.status_code == 400 and "chốt" in r.json()["detail"].lower(), r.text


def test_ca_dem_ngay_dau_vao_lam_khong_gan_ve_hom_truoc(client):
    """A10: lượt rạng sáng ngày ĐẦU TIÊN đi làm không thể thuộc ca hôm trước (chưa vào làm)."""
    h = _h(client)
    e = _nv(client, h, "A10", "Kinh doanh", hire=f"{NAM}-06-15")
    _khai_luong(client, h, e)
    sid = _ca_dem(client, h)
    r = client.put(f"/api/employees/{e}/shift", json={"default_shift_id": sid, "effective_from": f"{NAM}-06-15"}, headers=h)
    assert r.status_code == 200, r.text
    _bam(e, NAM, 6, 15, 2, 0, "in")
    ts = client.get(f"/api/attendance/timesheet?year={NAM}&month=6", headers=h).json()
    row = next(r for r in ts["rows"] if r["employee_id"] == e)
    assert "14" not in row["days"] and row["days"].get("15", {}).get("first_in") == "02:00", row["days"].keys()
