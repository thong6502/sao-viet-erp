"""Bước 8 bản rà liên thông — theo 4 chốt của chủ 07/09/2026:
B1 công chuẩn LƯƠNG gồm ngày lễ hưởng lương (như bảng lương T05) · C5 chuyên cần + 14 ngày BHXH trên công
NGÀY THƯỜNG · D3 ngày lễ có đi làm giữ 1,0 công lễ · B2 bảng phạt trống = không phạt.
Lương vị trí 10.400.000; tháng 6/2026: 26 ngày làm việc (T2–T7), lễ thử 10/06 (T4).
"""
from __future__ import annotations

from datetime import datetime, timezone

from app.db import SessionLocal
from app.repositories.attendance_repo import AttendanceRepository
from app.services.attendance_service import VN_TZ
from tests.test_ra_soat_nhan_su_luong_07_09 import NAM, _bam_du_thang, _ca, _gen, _h, _khai_luong, _line, _nv


def _le(client, h, ngay: str) -> None:
    r = client.post("/api/calendar/special-days", json={"day": ngay, "kind": "off", "name": "Lễ thử", "is_paid": True},
                    headers=h)
    assert r.status_code == 201, r.text


def _bam(eid: int, y: int, m: int, d: int, hh: int, mm: int, kieu: str) -> None:
    db = SessionLocal()
    try:
        AttendanceRepository(db).create_log(
            employee_id=eid, check_type=kieu, within_range=True,
            checked_at=datetime(y, m, d, hh, mm, tzinfo=VN_TZ).astimezone(timezone.utc))
    finally:
        db.close()


def _bam_ngay(eid: int, y: int, m: int, d: int, ra: int = 16) -> None:
    _bam(eid, y, m, d, 8, 0, "in")
    _bam(eid, y, m, d, ra, 0, "out")


def test_B1_thang_co_le_nghi_1_ngay_khong_phep_ra_25_tren_26(client):
    h = _h(client)
    _le(client, h, f"{NAM}-06-10")
    e = _nv(client, h, "B1", "Kinh doanh")
    _khai_luong(client, h, e, chuyen_can=300_000)
    sid = _ca(client, h)
    client.put(f"/api/employees/{e}/shift", json={"default_shift_id": sid, "effective_from": "2020-01-01"}, headers=h)
    # Đi làm mọi ngày T2–T7 trừ 10/06 (lễ, nghỉ ở nhà) và 11/06 (nghỉ không phép).
    for d in range(1, 31):
        wd = datetime(NAM, 6, d).weekday()
        if wd == 6 or d in (10, 11):
            continue
        _bam_ngay(e, NAM, 6, d)
    ln = _line(_gen(client, h), e)
    # Công chuẩn GỒM lễ = 26; công = 24 làm + 1 công lễ = 25 ⇒ trừ 1 ngày lương, chuyên cần −50%.
    assert ln["standard_cong"] == 26 and ln["actual_cong"] == 25.0, ln
    assert ln["luong_cong"] == 25 * 400_000
    assert ln["chuyen_can"] == 150_000
    # Đối chứng: đi đủ (24 làm + lễ + 11/06) = 26/26 ⇒ đủ lương, đủ chuyên cần.
    _bam_ngay(e, NAM, 6, 11)
    ln = _line(_gen(client, h), e)
    assert ln["actual_cong"] == 26.0 and ln["luong_cong"] == 26 * 400_000 and ln["chuyen_can"] == 300_000


def test_C5_lam_chu_nhat_khong_bu_chuyen_can_va_14_ngay(client):
    h = _h(client)
    e = _nv(client, h, "C5", "Kinh doanh")
    _khai_luong(client, h, e, chuyen_can=300_000)
    sid = _ca(client, h)
    client.put(f"/api/employees/{e}/shift", json={"default_shift_id": sid, "effective_from": "2020-01-01"}, headers=h)
    # Tháng 8/2026: 26 ngày làm việc. Nghỉ 12/08 + 13/08 không phép, đi làm 2 CN (16/08, 23/08).
    for d in range(1, 32):
        wd = datetime(NAM, 8, d).weekday()
        if d in (12, 13):
            continue
        if wd == 6 and d not in (16, 23):
            continue
        _bam_ngay(e, NAM, 8, d)
    ln = _line(_gen(client, h, month=8), e)
    assert ln["actual_cong"] == 26.0, ln                # 24 thường + 2 CN
    assert ln["chuyen_can"] == 0, ln                    # nghỉ 2 ngày thường ⇒ mất hết (trước: 100%)
    assert ln["luong_cong"] == 26 * 400_000             # trần công chuẩn: CN vẫn lấp trần lương công
    # 14 ngày BHXH: nghỉ không lương 14 ngày thường, đi làm 1 CN ⇒ vẫn miễn BHXH (trước: 13 ⇒ bị trừ).
    e2 = _nv(client, h, "C5b", "Kinh doanh")
    _khai_luong(client, h, e2)
    client.put(f"/api/employees/{e2}/shift", json={"default_shift_id": sid, "effective_from": "2020-01-01"}, headers=h)
    lam = 0
    for d in range(1, 32):
        wd = datetime(NAM, 8, d).weekday()
        if wd == 6:
            if d == 16:
                _bam_ngay(e2, NAM, 8, d)
            continue
        if lam < 12:
            _bam_ngay(e2, NAM, 8, d)
            lam += 1
    ln2 = _line(_gen(client, h, month=8), e2)
    assert ln2["actual_cong"] == 13.0 and ln2["bhxh"] == 0, ln2


def test_D3_lam_nua_ngay_le_van_du_1_cong_le(client):
    h = _h(client)
    _le(client, h, f"{NAM}-06-10")
    e = _nv(client, h, "D3", "Kinh doanh")
    _khai_luong(client, h, e)
    sid = _ca(client, h)
    client.put(f"/api/employees/{e}/shift", json={"default_shift_id": sid, "effective_from": "2020-01-01"}, headers=h)
    for d in range(1, 31):
        if datetime(NAM, 6, d).weekday() == 6:
            continue
        if d == 10:
            _bam_ngay(e, NAM, 6, d, ra=12)              # lễ: làm nửa ngày
        else:
            _bam_ngay(e, NAM, 6, d)
    ln = _line(_gen(client, h), e)
    # 25 ngày làm + 1,0 công lễ (không phải 0,5) = 26/26; giờ thực nửa ngày chỉ là nền hệ số lễ 300%.
    assert ln["actual_cong"] == 26.0, ln
    assert ln["luong_cong"] == 26 * 400_000
    assert ln["ot_pay"] == 0.5 * 3 * 400_000            # premium lễ = 0,5 công × 300% × đơn giá ngày


def test_B2_bang_phat_trong_khong_phat(client):
    h = _h(client)
    e = _nv(client, h, "B2", "Kinh doanh")
    _khai_luong(client, h, e)
    sid = _ca(client, h)
    client.put(f"/api/employees/{e}/shift", json={"default_shift_id": sid, "effective_from": "2020-01-01"}, headers=h)
    _bam(e, NAM, 6, 15, 8, 30, "in")                     # trễ 25′
    _bam(e, NAM, 6, 15, 16, 0, "out")
    assert client.get("/api/luong/late-penalty-brackets", headers=h).json()["items"] == []
    assert _line(_gen(client, h), e)["di_tre"] == 0
    r = client.post("/api/luong/late-penalty-brackets", json={"seq": 1, "up_to_minute": None, "amount": 40_000}, headers=h)
    assert r.status_code in (200, 201), r.text
    assert _line(_gen(client, h), e)["di_tre"] == 40_000
