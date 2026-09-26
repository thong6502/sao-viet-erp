"""Điều kiện CÔNG để tạm ứng / lương đợt 1 + lập hàng loạt (chủ chốt 25/09/2026).

* Phải có ≥ `payroll_params.tam_ung_cong_toi_thieu` (mặc định 13) CÔNG TÍNH LƯƠNG từ ngày 1 của
  kỳ tới hết ngày lập phiếu. Chặn CỨNG. (Bộ test tắt mặc định qua conftest — bài này bật lại.)
* "Chọn tất cả người đủ điều kiện": `GET /api/luong/advances/ung-vien` + `POST /advances/bulk`
  — bulk kiểm HẾT trước, còn một người chưa đủ là không ghi phiếu nào.
* Công đếm tới ngày N dựng từ lưới ngày của CHÍNH `monthly_timesheet`: Σ cả tháng phải bằng đúng
  `total_cong` — không có đường tính công thứ hai.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from app.db import SessionLocal
from app.models.attendance import AttendanceLog
from app.models.employee import Employee
from app.models.payroll import SalaryAdvance
from app.services.attendance_service import AttendanceService

from .test_bang_cong_so_truy_van import _svc
from .test_work_shifts_api import _admin_token, _mk_shift

VN = timezone(timedelta(hours=7))
NAM, THANG = 2026, 8          # tháng đã qua trọn: mọi ngày đều là ngày thật, không "ngày tới"


def _h(tok: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {tok}"}


def _nguoi(ten: str, ma: str, shift_id: int, lam_toi_ngay: int) -> int:
    """Một người ca hành chính, bấm vào/ra đủ mọi ngày làm việc (trừ Chủ nhật) tới `lam_toi_ngay`."""
    db = SessionLocal()
    try:
        e = Employee(code=ma, full_name=ten, status="active", hire_date=date(2024, 1, 1),
                     default_shift_id=shift_id)
        db.add(e)
        db.flush()
        for d in range(1, lam_toi_ngay + 1):
            if date(NAM, THANG, d).weekday() == 6:
                continue
            for gio, loai in ((8, "in"), (17, "out")):
                db.add(AttendanceLog(employee_id=e.id, check_type=loai,
                                     checked_at=datetime(NAM, THANG, d, gio, tzinfo=VN)
                                     .astimezone(timezone.utc)))
        db.commit()
        return e.id
    finally:
        db.close()


def _dung(client):
    tok = _admin_token(client)
    ca = _mk_shift(client, tok, "HC tam ung", "08:00", "17:00")
    a = _nguoi("Tạm Ứng Đủ", "TU-DU", ca["id"], 20)
    b = _nguoi("Tạm Ứng Thiếu", "TU-THIEU", ca["id"], 10)
    r = client.put("/api/luong/params", json={"tam_ung_cong_toi_thieu": 13}, headers=_h(tok))
    assert r.status_code == 200, r.text
    assert float(r.json()["tam_ung_cong_toi_thieu"]) == 13
    return tok, a, b


def _phieu(client, tok, eid, *, ngay="2026-08-15", kind="tam_ung"):
    return client.post("/api/luong/advances", headers=_h(tok), json={
        "employee_id": eid, "period_year": NAM, "period_month": THANG, "advance_date": ngay,
        "amount": 1_000_000, "kind": kind})


def test_du_cong_thi_lap_duoc_thieu_cong_thi_chan_ro_so(client):
    tok, a, b = _dung(client)
    assert _phieu(client, tok, a).status_code == 201
    r = _phieu(client, tok, b, kind="luong_dot_1")
    assert r.status_code == 400, r.text
    loi = r.json()["detail"]
    assert "Tạm Ứng Thiếu mới có" in loi and "/13 công" in loi and "lương đợt 1" in loi
    # Lập phiếu TRƯỚC khi kỳ bắt đầu ⇒ 0 công ⇒ chặn.
    assert _phieu(client, tok, a, ngay="2026-07-31").status_code == 400


def test_danh_sach_ung_vien_va_lap_hang_loat(client):
    tok, a, b = _dung(client)
    r = client.get("/api/luong/advances/ung-vien", headers=_h(tok), params={
        "year": NAM, "month": THANG, "advance_date": "2026-08-15", "kind": "tam_ung"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["nguong"] == 13 and body["den_ngay"] == 15
    theo = {x["employee_id"]: x for x in body["items"]}
    assert theo[a]["du_dieu_kien"] and not theo[b]["du_dieu_kien"]
    assert theo[a]["cong"] >= 13 > theo[b]["cong"]

    bulk = {"period_year": NAM, "period_month": THANG, "advance_date": "2026-08-15",
            "kind": "tam_ung", "reason": "Ứng giữa tháng"}
    r = client.post("/api/luong/advances/bulk", headers=_h(tok),
                    json={**bulk, "items": [{"employee_id": a, "amount": 500_000},
                                            {"employee_id": b, "amount": 500_000}]})
    assert r.status_code == 400, r.text
    d = r.json()["detail"]
    assert "Chưa lập phiếu nào" in d["message"] and "Tạm Ứng Thiếu" in d["message"]
    assert d["vuong_ids"] == [b]     # id NHÂN VIÊN vướng — màn Lập phiếu bỏ tick đúng người đó
    db = SessionLocal()
    try:
        assert db.query(SalaryAdvance).filter(SalaryAdvance.employee_id.in_([a, b])).count() == 0
    finally:
        db.close()

    r = client.post("/api/luong/advances/bulk", headers=_h(tok),
                    json={**bulk, "items": [{"employee_id": a, "amount": 500_000}]})
    assert r.status_code == 201, r.text
    assert [x["employee_id"] for x in r.json()["items"]] == [a]

    # Đã có phiếu cùng loại trong kỳ ⇒ danh sách báo để khỏi lập trùng.
    r = client.get("/api/luong/advances/ung-vien", headers=_h(tok), params={
        "year": NAM, "month": THANG, "advance_date": "2026-08-15", "kind": "tam_ung"})
    assert {x["employee_id"]: x for x in r.json()["items"]}[a]["so_phieu_da_co"] == 1


def test_cong_den_ngay_khop_tong_cong(client):
    """Σ công từng ngày của cả tháng == `total_cong` của bảng công — cùng một nguồn số."""
    _dung(client)
    db = SessionLocal()
    try:
        svc = _svc(db)
        tk = svc.monthly_timesheet(year=NAM, month=THANG)
        ca_thang = svc.cong_tinh_luong_den_ngay(year=NAM, month=THANG, den_ngay=31)
        for row in tk["rows"]:
            assert ca_thang[row["employee_id"]]["cong"] == round(float(row["total_cong"] or 0), 2), row
    finally:
        db.close()


def test_luat_cong_tung_o_ngay():
    """Từng nhánh cộng `total_cong` của vòng ngày, viết thành luật cho MỘT ô."""
    f = AttendanceService.cong_ngay
    assert f({"cong": 1.0}) == 1.0                                   # ngày làm thường
    assert f({"cong": 0.5, "plain": True}) == 0                      # off1x: loại khỏi base
    assert f({"cong": 0.5, "cong_le": 1.0}) == 1.0                   # lễ làm nửa ngày vẫn 1 công lễ
    assert f({"cong": 1.0, "cong_le": 1.0, "le_nghi_tuan": True}) == 2.0   # lễ trùng CN
    assert f({"cong": 1.0, "leave": "Phép năm", "leave_paid": True}) == 1.0  # phép có lương
    assert f({"cong": None}) == 0                                    # ngày chưa tới / trống


def test_nhan_vien_xem_cong_cua_chinh_minh(client):
    """Màn "Đề nghị tạm ứng" hỏi trước: công của MÌNH tới ngày ứng + ngưỡng."""
    from app.repositories.user_repo import UserRepository
    from app.security import create_access_token, hash_password

    tok, a, _b = _dung(client)
    db = SessionLocal()
    try:
        u = UserRepository(db).create(username="tu-tu-xin", name="Tự xin", password_hash=hash_password("x"))
        db.get(Employee, a).user_id = u.id
        db.commit()
        tok_nv = create_access_token(str(u.id))
    finally:
        db.close()
    r = client.get("/api/luong/advances/me/dieu-kien", headers=_h(tok_nv),
                   params={"year": NAM, "month": THANG, "advance_date": "2026-08-05"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["nguong"] == 13 and body["den_ngay"] == 5
    assert body["cong"] < 13 and body["du_dieu_kien"] is False
    r = client.get("/api/luong/advances/me/dieu-kien", headers=_h(tok_nv),
                   params={"year": NAM, "month": THANG, "advance_date": "2026-08-20"})
    assert r.json()["du_dieu_kien"] is True
