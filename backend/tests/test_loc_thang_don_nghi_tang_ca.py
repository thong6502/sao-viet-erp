"""Danh sách đơn nghỉ / phiếu tăng ca: MỚI TẠO NHẤT lên đầu + lọc theo THÁNG của NGÀY TẠO
(chủ 23/09/2026: *"lọc theo tháng là lọc theo ngày tạo nha"*).

Tháng tính theo GIỜ VIỆT NAM: đơn tạo lúc 06:00 sáng 01/10 giờ VN (= 23:00 30/09 UTC) phải thuộc
tháng 10 — cắt theo UTC là rơi nhầm sang tháng 9.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.db import SessionLocal
from app.models.leave import LeaveRequest
from app.models.overtime import OvertimeRequest
from app.services.khoang_thang import khoang_tao_theo_thang
from tests.test_duyet_dung_pham_vi_api import _emp
from tests.test_luong_api import _admin_token, _h

VN = timezone(timedelta(hours=7))


def _dat_ngay_tao(model, rid: int, luc_vn: datetime) -> None:
    db = SessionLocal()
    try:
        db.get(model, rid).created_at = luc_vn.astimezone(timezone.utc)
        db.commit()
    finally:
        db.close()


def test_khoang_thang_tinh_theo_gio_viet_nam():
    tu, den = khoang_tao_theo_thang("2026-12")
    assert tu == datetime(2026, 11, 30, 17, 0, tzinfo=timezone.utc)
    assert den == datetime(2026, 12, 31, 17, 0, tzinfo=timezone.utc)
    assert khoang_tao_theo_thang(None) is None and khoang_tao_theo_thang("") is None
    for sai in ("2026-13", "09-2026", "2026/09"):
        try:
            khoang_tao_theo_thang(sai)
            raise AssertionError(sai)
        except ValueError:
            pass


def test_DON_NGHI_moi_tao_len_dau_va_loc_theo_thang_tao(client):
    h = _h(_admin_token(client))
    # `POST /api/leaves` luôn tạo cho CHÍNH người gửi (Admin) ⇒ lọc theo hồ sơ của Admin.
    loai = client.post("/api/leaves/types", json={"name": "KL lọc tháng", "is_paid": False,
                                                  "annual_quota": 0}, headers=h).json()["id"]
    ids = []
    for ngay in ("2026-11-02", "2026-11-03", "2026-11-04"):
        r = client.post("/api/leaves", json={"leave_type_id": loai,
                                             "start_date": ngay, "end_date": ngay}, headers=h)
        assert r.status_code == 201, r.text
        ids.append(r.json()["id"])
        eid = r.json()["employee_id"]
    # Ngày NGHỈ tăng dần theo id, ngày TẠO thì ngược lại — thứ tự phải theo ngày TẠO.
    _dat_ngay_tao(LeaveRequest, ids[0], datetime(2026, 10, 1, 6, 0, tzinfo=VN))   # 30/09 UTC!
    _dat_ngay_tao(LeaveRequest, ids[1], datetime(2026, 9, 20, 9, 0, tzinfo=VN))
    _dat_ngay_tao(LeaveRequest, ids[2], datetime(2026, 9, 5, 9, 0, tzinfo=VN))

    items = client.get(f"/api/leaves?employee_id={eid}", headers=h).json()["items"]
    assert [x["id"] for x in items] == ids, "mới TẠO nhất phải lên đầu"

    r = client.get(f"/api/leaves?employee_id={eid}&thang=2026-09", headers=h).json()
    assert [x["id"] for x in r["items"]] == [ids[1], ids[2]] and r["total"] == 2
    r = client.get(f"/api/leaves?employee_id={eid}&thang=2026-10", headers=h).json()
    assert [x["id"] for x in r["items"]] == [ids[0]], "06:00 01/10 giờ VN là tháng 10"
    # Lọc trạng thái Đã hủy chạy chung với lọc tháng.
    client.post(f"/api/leaves/{ids[1]}/cancel", headers=h)
    r = client.get(f"/api/leaves?employee_id={eid}&thang=2026-09&status=cancelled", headers=h).json()
    assert [x["id"] for x in r["items"]] == [ids[1]]
    assert client.get("/api/leaves?thang=2026-9", headers=h).status_code == 400


def test_PHIEU_TANG_CA_moi_tao_len_dau_va_loc_theo_thang_tao(client):
    admin = _admin_token(client)
    h = _h(admin)
    eid = _emp(client, admin, name="NV lọc tháng TC", dept="Kinh doanh")
    ids = []
    for ngay in ("2026-11-02", "2026-11-03"):
        r = client.post("/api/overtime", json={"employee_id": eid, "work_date": ngay,
                                               "from_minute": 1080, "to_minute": 1200,
                                               "reason": "x"}, headers=h)
        assert r.status_code == 201, r.text
        ids.append(r.json()["id"])
    _dat_ngay_tao(OvertimeRequest, ids[0], datetime(2026, 10, 3, 9, 0, tzinfo=VN))
    _dat_ngay_tao(OvertimeRequest, ids[1], datetime(2026, 9, 15, 9, 0, tzinfo=VN))

    items = client.get(f"/api/overtime?employee_id={eid}", headers=h).json()["items"]
    assert [x["id"] for x in items] == ids
    r = client.get(f"/api/overtime?employee_id={eid}&thang=2026-09&status_filter=approved",
                   headers=h).json()
    assert [x["id"] for x in r["items"]] == [ids[1]] and r["total"] == 1
