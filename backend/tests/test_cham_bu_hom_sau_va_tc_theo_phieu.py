"""Đợt 1 (07/09/2026) — chấm bù SANG HÔM SAU (1.2) · cảnh báo phiếu TC thiếu cặp bấm (1.3) ·
gợi ý chấm bù cả phiếu vắt nửa đêm (1.4) · XÁC NHẬN TĂNG CA THEO PHIẾU hàng loạt (1.5) ·
khe giữa các phiên tăng ca không trả (1.6).

Chủ giữ luật 4 lượt bấm ("tăng ca vẫn bấm 4 lượt"); các mục này là đường BÙ cho thợ quên bấm và
đường CẢNH BÁO để tiền tăng ca không mất lặng lẽ lúc chốt kỳ.
"""
from __future__ import annotations

from datetime import date, datetime, timezone

from app.db import SessionLocal
from app.repositories.attendance_repo import AttendanceRepository
from app.repositories.employee_repo import EmployeeRepository
from app.repositories.rbac_repo import DepartmentRepository, RoleRepository
from app.repositories.user_repo import UserRepository
from app.security import create_access_token, hash_password
from app.services.attendance_service import VN_TZ, compute_day_cong

ADMIN = {"username": "admin", "password": "admin123"}
NAM, THANG = 2026, 6                     # 01/06/2026 = Thứ Hai, đã qua
D1 = f"{NAM}-{THANG:02d}-01"


def _h(client) -> dict[str, str]:
    tok = client.post("/api/auth/login", json=ADMIN).json()["access_token"]
    return {"Authorization": f"Bearer {tok}"}


def _hh(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _dept_id(name: str) -> int:
    db = SessionLocal()
    try:
        return DepartmentRepository(db).get_by_name(name).id
    finally:
        db.close()


def _ca(client, h, *, name, start, end, overnight=False) -> int:
    items = client.get("/api/attendance/shifts", headers=h).json()["items"]
    co = next((s for s in items if s["name"] == name), None)
    if co is not None:
        return co["id"]
    r = client.post("/api/attendance/shifts",
                    json={"name": name, "start_time": start, "end_time": end,
                          "is_overnight": overnight}, headers=h)
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _ca_ngay(client, h) -> int:
    return _ca(client, h, name="HC test 8-17", start="08:00", end="17:00")


def _ca_dem(client, h) -> int:
    return _ca(client, h, name="Đêm test 22-06", start="22:00", end="06:00", overnight=True)


def _nv(client, h, shift_id: int, *, ten, dept="Hành chính nhân sự") -> int:
    r = client.post("/api/employees",
                    json={"full_name": ten, "department_id": _dept_id(dept),
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


def _phieu(client, h, eid: int, *, tu: int, den: int, ngay: str = D1) -> int:
    """Tổ trưởng/HCNS tạo hộ ⇒ DUYỆT LUÔN. `tu/den` = phút từ 00:00 ngày công (≥1440 = hôm sau)."""
    r = client.post("/api/overtime",
                    json={"employee_id": eid, "work_date": ngay, "from_minute": tu, "to_minute": den,
                          "reason": "chạy đơn gấp"}, headers=h)
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _row(client, h, eid: int) -> dict:
    ts = client.get("/api/attendance/timesheet", params={"year": NAM, "month": THANG}, headers=h).json()
    return next(r for r in ts["rows"] if r["employee_id"] == eid)


def _day(client, h, eid: int, ngay: str = D1) -> dict:
    return client.get("/api/attendance/day", params={"employee_id": eid, "date": ngay}, headers=h).json()


def _period(client, h) -> dict:
    return client.get("/api/attendance/period", params={"year": NAM, "month": THANG}, headers=h).json()


# ══════════════════════════════════════════════ 1.2 chấm bù sang hôm sau


def test_ca_dem_cham_bu_RA_06h_hom_sau_moi_dung_ngay(client):
    """⭐ Ca 22:00–06:00, quên bấm RA. Chấm bù 06:00 KHÔNG tick hôm sau ⇒ vẫn treo (lượt rơi về hôm
    trước); tick "sang hôm sau" ⇒ đủ công, hết treo."""
    h = _h(client)
    ca = _ca_dem(client, h)
    a = _nv(client, h, ca, ten="Đêm A")
    b = _nv(client, h, ca, ten="Đêm B")
    for e in (a, b):
        _bam(e, 1, 22, 0, "in")
    assert _period(client, h)["hanging_days"] == 2       # cả A lẫn B đang treo

    # B: chấm bù kiểu cũ (không hôm sau) ⇒ lượt 06:00 ngày 1 bị gom về ngày 31/5 ⇒ ngày 1 vẫn treo.
    r = client.post("/api/attendance/adjust",
                    json={"employee_id": b, "date": D1, "check_type": "out", "time": "06:00",
                          "reason": "quên bấm", "fault_party": "nv_quen"}, headers=h)
    assert r.status_code == 200, r.text
    assert _period(client, h)["hanging_days"] == 2
    assert _row(client, h, b)["days"]["1"]["cong"] == 0.0

    # A: tick sang hôm sau ⇒ RA 06:00 ngày 2 ghép về ngày công 1.
    r = client.post("/api/attendance/adjust",
                    json={"employee_id": a, "date": D1, "check_type": "out", "time": "06:00",
                          "next_day": True, "reason": "quên bấm", "fault_party": "nv_quen"}, headers=h)
    assert r.status_code == 200, r.text
    d = r.json()
    assert [p["check_type"] for p in d["punches"]] == ["in", "out"] and d["cong"] == 1.0
    row = _row(client, h, a)
    assert _period(client, h)["hanging_days"] == 1       # chỉ còn B
    assert row["days"]["1"]["cong"] == 1.0 and row["days"]["1"]["hours"] == 8.0
    assert "2" not in row["days"] or not row["days"]["2"].get("present")


def test_yeu_cau_chinh_cong_mang_co_hom_sau_va_duyet_dung(client):
    """NV ca đêm gửi yêu cầu chỉnh công 06:00 (sang hôm sau) → HCNS duyệt ⇒ punch đúng ngày."""
    h = _h(client)
    ca = _ca_dem(client, h)
    eid = _nv(client, h, ca, ten="Đêm C")
    _bam(eid, 1, 22, 0, "in")
    # Tài khoản thợ: vai có ô cham_cong (xem + thao tác, phạm vi của tôi), nối hồ sơ.
    db = SessionLocal()
    try:
        users, roles = UserRepository(db), RoleRepository(db)
        dept = DepartmentRepository(db).get_by_name("Hành chính nhân sự")
        vai = roles.get_by_name_and_department("Thợ đêm", dept.id) or roles.create(
            name="Thợ đêm", department_id=dept.id)
        roles.set_permission(role_id=vai.id, module_key="cham_cong", scope="own",
                             can_read=True, can_create=True)
        u = users.get_by_username("tho-dem") or users.create(
            username="tho-dem", name="Thợ đêm", password_hash=hash_password("x"))
        users.set_assignment(u, department_id=dept.id, role_id=vai.id, is_active=True)
        db.commit()
        uid = u.id
    finally:
        db.close()
    assert client.post(f"/api/employees/{eid}/account", json={"user_id": uid},
                       headers=h).status_code in (200, 201)
    tho = create_access_token(str(uid))
    r = client.post("/api/attendance/me/adjust-request",
                    json={"date": D1, "check_type": "out", "suggested_time": "06:00",
                          "suggested_next_day": True, "reason": "quên bấm ra sáng"}, headers=_hh(tho))
    assert r.status_code == 200, r.text
    assert r.json()["suggested_next_day"] is True
    rid = r.json()["id"]
    mine = client.get("/api/attendance/me/adjust-requests", headers=_hh(tho)).json()["items"]
    assert next(x for x in mine if x["id"] == rid)["suggested_next_day"] is True
    ok = client.post(f"/api/attendance/adjust-requests/{rid}/approve", json={}, headers=h)
    assert ok.status_code == 200, ok.text
    assert _day(client, h, eid)["cong"] == 1.0
    assert _period(client, h)["hanging_days"] == 0


# ══════════════════════════════════════════════ 1.4 ghép cặp TC vắt nửa đêm


def test_ca_ngay_tang_ca_toi_2h_sang_van_ghep_dung_ngay(client):
    """Ca 08–17 có phiếu 17:30 → 02:00. Trước đây hết 01:00 (17h+8h) lượt RA 02:00 bị coi là VÀO ca
    mới ⇒ cặp TC vỡ. Nay hạn ghép RA = max(hết ca, hết phiếu) + 8h ⇒ TC = 510'."""
    h = _h(client)
    ca = _ca_ngay(client, h)
    eid = _nv(client, h, ca, ten="TC đêm D")
    _phieu(client, h, eid, tu=1050, den=1560)         # 17:30 → 02:00 hôm sau
    _bam(eid, 1, 8, 0, "in"); _bam(eid, 1, 17, 0, "out")
    _bam(eid, 1, 17, 30, "in"); _bam(eid, 2, 2, 0, "out")
    row = _row(client, h, eid)
    assert row["days"]["1"]["cong"] == 1.0 and row["days"]["1"]["ot_minutes"] == 510
    assert _period(client, h)["hanging_days"] == 0
    assert "2" not in row["days"] or not row["days"]["2"].get("present")
    # Ô biết nói cũng thấy đủ 4 lượt ở ngày 1.
    d = _day(client, h, eid)
    assert [p["check_type"] for p in d["punches"]] == ["in", "out", "in", "out"]
    assert d["ot_suggestion"] is None


def test_goi_y_cham_bu_cap_TC_ca_phieu_vat_nua_dem(client):
    h = _h(client)
    ca = _ca_ngay(client, h)
    eid = _nv(client, h, ca, ten="TC đêm E")
    _phieu(client, h, eid, tu=1050, den=1560)
    _bam(eid, 1, 8, 0, "in"); _bam(eid, 1, 17, 0, "out")
    s = _day(client, h, eid)["ot_suggestion"]
    assert s == {"from_time": "17:30", "to_time": "02:00", "from_next_day": False,
                 "to_next_day": True, "kieu": "bu_cap"}
    # Xác nhận ⇒ RA 02:00 ghi sang hôm sau, TC = 510'.
    r = client.post("/api/attendance/ot-confirm", json={"date": D1, "employee_ids": [eid]}, headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["done"][0]["punches"][1] == {"time": "02:00", "check_type": "out", "next_day": True}
    assert _row(client, h, eid)["days"]["1"]["ot_minutes"] == 510


# ══════════════════════════════════════════════ 1.3 cảnh báo thiếu cặp bấm


def test_period_canh_bao_phieu_da_duyet_ma_thieu_cap_bam_khong_chan_chot(client):
    h = _h(client)
    ca = _ca_ngay(client, h)
    e_thieu = _nv(client, h, ca, ten="Thiếu cặp")
    e_khong = _nv(client, h, ca, ten="Không bấm")
    e_du = _nv(client, h, ca, ten="Đủ cặp")
    for e in (e_thieu, e_khong, e_du):
        _phieu(client, h, e, tu=1050, den=1230)          # 17:30 → 20:30
    _bam(e_thieu, 1, 8, 0, "in"); _bam(e_thieu, 1, 17, 0, "out")
    _bam(e_du, 1, 8, 0, "in"); _bam(e_du, 1, 17, 0, "out")
    _bam(e_du, 1, 17, 30, "in"); _bam(e_du, 1, 20, 30, "out")

    p = _period(client, h)
    assert p["ot_thieu_cap"] == 2
    ly_do = {x["employee_id"]: x for x in p["ot_thieu_cap_list"]}
    assert ly_do[e_thieu]["ly_do"] == "thiếu cặp bấm tăng ca" and ly_do[e_thieu]["date"] == D1
    assert ly_do[e_thieu]["from_time"] == "17:30" and ly_do[e_thieu]["to_time"] == "20:30"
    assert ly_do[e_khong]["ly_do"] == "không có lượt bấm nào trong ngày"
    assert e_du not in ly_do
    # Ô ngày mang cờ để lưới tô.
    assert _row(client, h, e_thieu)["days"]["1"]["ot_thieu_cap"] is True
    assert _row(client, h, e_khong)["days"]["1"]["ot_thieu_cap"] is True
    assert _row(client, h, e_du)["days"]["1"]["ot_thieu_cap"] is False
    # CHỈ cảnh báo — chốt kỳ vẫn được (không có ngày treo/đơn chờ).
    r = client.post("/api/attendance/period/lock", json={"year": NAM, "month": THANG}, headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "locked" and r.json()["ot_thieu_cap"] == 2
    # Kỳ đã chốt ⇒ không xác nhận TC được nữa.
    r = client.post("/api/attendance/ot-confirm", json={"date": D1, "employee_ids": [e_thieu]}, headers=h)
    assert r.status_code == 400 and "đã chốt" in r.json()["detail"]


def test_phieu_ngay_tuong_lai_khong_bi_coi_la_thieu_cap(client):
    """Phiếu duyệt trước cho ngày CHƯA TỚI thì đương nhiên chưa có cặp bấm — không được báo."""
    from datetime import timedelta
    h = _h(client)
    ca = _ca_ngay(client, h)
    eid = _nv(client, h, ca, ten="Tương lai")
    mai = date.today() + timedelta(days=1)
    _phieu(client, h, eid, tu=1050, den=1230, ngay=mai.isoformat())
    p = client.get("/api/attendance/period", params={"year": mai.year, "month": mai.month}, headers=h).json()
    assert all(x["employee_id"] != eid for x in p["ot_thieu_cap_list"])


# ══════════════════════════════════════════════ 1.5 xác nhận TC theo phiếu hàng loạt


def test_xac_nhan_hang_loat_bu_cap_va_bo_qua_co_ly_do(client):
    h = _h(client)
    ca = _ca_ngay(client, h)
    e_thieu = _nv(client, h, ca, ten="Thiếu cặp")
    e_khong = _nv(client, h, ca, ten="Không bấm")
    e_treo = _nv(client, h, ca, ten="Treo")
    e_du = _nv(client, h, ca, ten="Đủ cặp")
    e_khong_phieu = _nv(client, h, ca, ten="Không phiếu")
    for e in (e_thieu, e_khong, e_treo, e_du):
        _phieu(client, h, e, tu=1050, den=1230)
    _bam(e_thieu, 1, 8, 0, "in"); _bam(e_thieu, 1, 17, 0, "out")
    _bam(e_treo, 1, 8, 0, "in")
    _bam(e_du, 1, 8, 0, "in"); _bam(e_du, 1, 17, 0, "out")
    _bam(e_du, 1, 17, 30, "in"); _bam(e_du, 1, 20, 30, "out")

    ung = client.get("/api/attendance/ot-confirm", params={"date": D1}, headers=h).json()
    assert ung["date"] == D1
    tt = {x["employee_id"]: x for x in ung["items"]}
    assert tt[e_thieu]["tinh_trang"] == "thieu_cap" and tt[e_thieu]["kieu"] == "bu_cap"
    assert tt[e_khong]["tinh_trang"] == "khong_cham"
    assert tt[e_treo]["tinh_trang"] == "treo"
    assert tt[e_du]["tinh_trang"] == "da_co"
    assert e_khong_phieu not in tt

    r = client.post("/api/attendance/ot-confirm",
                    json={"date": D1, "employee_ids": [e_thieu, e_khong, e_treo, e_du, e_khong_phieu],
                          "reason": "cả tổ làm tới 20h30"}, headers=h)
    assert r.status_code == 200, r.text
    out = r.json()
    assert [d["employee_id"] for d in out["done"]] == [e_thieu]
    assert out["done"][0]["kieu"] == "bu_cap"
    assert out["done"][0]["punches"] == [{"time": "17:30", "check_type": "in", "next_day": False},
                                         {"time": "20:30", "check_type": "out", "next_day": False}]
    skipped = {s["employee_id"]: s["reason"] for s in out["skipped"]}
    assert "không có lượt bấm" in skipped[e_khong]
    assert "treo" in skipped[e_treo]
    assert "đã có" in skipped[e_du]
    assert "phạm vi" in skipped[e_khong_phieu]
    # Kết quả: TC = 180', hết cảnh báo cho người này, lượt sinh ra là chấm bù có lý do + fault `duyet`.
    row = _row(client, h, e_thieu)
    assert row["days"]["1"]["ot_minutes"] == 180 and row["days"]["1"]["ot_thieu_cap"] is False
    assert row["days"]["1"]["cong"] == 1.0
    d = _day(client, h, e_thieu)
    bu = [p for p in d["punches"] if p["is_manual"]]
    assert len(bu) == 2 and all(p["fault_party"] == "duyet" for p in bu)
    assert all("Xác nhận TC theo phiếu" in p["adjust_reason"] for p in bu)
    assert d["ot_suggestion"] is None
    assert _period(client, h)["ot_thieu_cap"] == 2       # còn "không bấm" + "treo"


def test_tach_phien_khi_tho_chi_bam_2_luot(client):
    """⭐ Đời thường nhất: thợ bấm VÀO 08:00, RA 20:30 (một phiên phủ luôn tăng ca). Xác nhận theo
    phiếu 17:30–20:30 ⇒ máy thêm RA ca chính 17:00 + VÀO TC 17:30; lượt RA 20:30 thật thành RA TC.
    Kết quả: công 1,0 + TC 180'. Nếu thêm cặp VÀO/RA theo phiếu như cũ thì phiên ca chính bị đè."""
    h = _h(client)
    ca = _ca_ngay(client, h)
    eid = _nv(client, h, ca, ten="Bấm 2 lượt")
    _phieu(client, h, eid, tu=1050, den=1230)
    _bam(eid, 1, 8, 0, "in"); _bam(eid, 1, 20, 30, "out")
    d0 = _day(client, h, eid)
    assert d0["cong"] == 1.0 and d0["ot_suggestion"]["kieu"] == "tach_phien"
    assert _row(client, h, eid)["days"]["1"]["ot_minutes"] == 0

    r = client.post("/api/attendance/ot-confirm", json={"date": D1, "employee_ids": [eid]}, headers=h)
    assert r.status_code == 200, r.text
    done = r.json()["done"][0]
    assert done["kieu"] == "tach_phien"
    assert done["punches"] == [{"time": "17:00", "check_type": "out", "next_day": False},
                               {"time": "17:30", "check_type": "in", "next_day": False}]
    row = _row(client, h, eid)
    assert row["days"]["1"]["cong"] == 1.0 and row["days"]["1"]["ot_minutes"] == 180
    assert [p["check_type"] for p in _day(client, h, eid)["punches"]] == ["in", "out", "in", "out"]


def test_gio_ra_thuc_te_som_hon_phieu_thi_tra_theo_that(client):
    h = _h(client)
    ca = _ca_ngay(client, h)
    eid = _nv(client, h, ca, ten="Về sớm TC")
    _phieu(client, h, eid, tu=1050, den=1230)
    _bam(eid, 1, 8, 0, "in"); _bam(eid, 1, 17, 0, "out")
    r = client.post("/api/attendance/ot-confirm",
                    json={"date": D1, "employee_ids": [eid], "to_time": "19:30"}, headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["done"][0]["punches"][1]["time"] == "19:30"
    assert _row(client, h, eid)["days"]["1"]["ot_minutes"] == 120
    # Giờ ra trước đầu phiếu ⇒ bỏ qua có lý do.
    e2 = _nv(client, h, ca, ten="Ra sai")
    _phieu(client, h, e2, tu=1050, den=1230)
    _bam(e2, 1, 8, 0, "in"); _bam(e2, 1, 17, 0, "out")
    r = client.post("/api/attendance/ot-confirm",
                    json={"date": D1, "employee_ids": [e2], "to_time": "17:00"}, headers=h)
    assert r.json()["done"] == [] and "sau giờ bắt đầu phiếu" in r.json()["skipped"][0]["reason"]


def test_ngay_chua_toi_khong_xac_nhan_duoc(client):
    from datetime import timedelta
    h = _h(client)
    mai = (date.today() + timedelta(days=1)).isoformat()
    r = client.post("/api/attendance/ot-confirm", json={"date": mai, "employee_ids": [1]}, headers=h)
    assert r.status_code == 400 and "chưa tới" in r.json()["detail"]


def _vai_cham_bu_to_sx() -> str:
    """Vai CÓ ô Chấm bù nhưng phạm vi TỔ (Sản xuất) — kiểm hàng rào phạm vi của xác nhận hàng loạt."""
    db = SessionLocal()
    try:
        depts, roles, users = DepartmentRepository(db), RoleRepository(db), UserRepository(db)
        dept = depts.get_by_name("Sản xuất")
        role = roles.get_by_name_and_department("Chấm bù tổ SX", dept.id) or roles.create(
            name="Chấm bù tổ SX", department_id=dept.id)
        roles.set_permission(role_id=role.id, module_key="cham_cong", scope="department",
                             can_read=True, can_adjust=True)
        u = users.get_by_username("cham-bu-sx") or users.create(
            username="cham-bu-sx", name="Chấm bù SX", password_hash=hash_password("x"))
        users.set_assignment(u, department_id=dept.id, role_id=role.id, is_active=True)
        db.commit()
        return create_access_token(str(u.id))
    finally:
        db.close()


def test_xac_nhan_chi_trong_pham_vi_to(client):
    h = _h(client)
    ca = _ca_ngay(client, h)
    e_sx = _nv(client, h, ca, ten="Thợ SX", dept="Sản xuất")
    e_kd = _nv(client, h, ca, ten="NV KD", dept="Kinh doanh")
    for e in (e_sx, e_kd):
        _phieu(client, h, e, tu=1050, den=1230)
        _bam(e, 1, 8, 0, "in"); _bam(e, 1, 17, 0, "out")
    t = _vai_cham_bu_to_sx()
    ung = client.get("/api/attendance/ot-confirm", params={"date": D1}, headers=_hh(t)).json()
    assert {x["employee_id"] for x in ung["items"]} == {e_sx}
    r = client.post("/api/attendance/ot-confirm", json={"date": D1, "employee_ids": [e_sx, e_kd]},
                    headers=_hh(t))
    assert r.status_code == 200, r.text
    assert [d["employee_id"] for d in r.json()["done"]] == [e_sx]
    assert r.json()["skipped"][0]["employee_id"] == e_kd and "phạm vi" in r.json()["skipped"][0]["reason"]
    # Không có ô Chấm bù thì không gọi được.
    db = SessionLocal()
    try:
        users = UserRepository(db)
        u = users.get_by_username("cham-bu-sx")
        roles = RoleRepository(db)
        role = roles.get_by_name_and_department("Chấm bù tổ SX", _dept_id("Sản xuất"))
        roles.set_permission(role_id=role.id, module_key="cham_cong", scope="department", can_read=True)
        db.commit()
    finally:
        db.close()
    assert client.get("/api/attendance/ot-confirm", params={"date": D1}, headers=_hh(t)).status_code == 403


# ══════════════════════════════════════════════ 1.6 khe giữa các phiên TC


def test_khe_giua_hai_phien_tang_ca_khong_tra():
    """Ca 08–17, phiếu 17:30–21:30. Hai phiên TC 17:30–18:30 và 19:00–21:30 (nghỉ ăn 30').
    Trước: một dải 17:30→21:30 = 240'. Nay: 60 + 150 = 210'."""
    kw = dict(start_min=480, end_min=1020, is_overnight=False, grace_min=5,
              first_in_min=480, main_out_min=1020, ot_window=(1050, 1290))
    v = compute_day_cong(**kw, ot_sessions=[(1050, 1110, 0, 0), (1140, 1290, 0, 0)])
    assert v["ot_minutes"] == 210 and v["ot_minutes_raw"] == 210
    # Phiên vượt phiếu vẫn bị kẹp trần từng phiên.
    v2 = compute_day_cong(**kw, ot_sessions=[(1050, 1110, 0, 0), (1140, 1400, 0, 0)])
    assert v2["ot_minutes"] == 210 and v2["ot_minutes_raw"] == 320
    # Đường cũ (một cặp ot_in/ot_out) vẫn chạy y nguyên cho caller cũ.
    v3 = compute_day_cong(**kw, ot_in_min=1050, ot_out_min=1290)
    assert v3["ot_minutes"] == 240


def test_khe_giua_phien_tren_bang_cong(client):
    h = _h(client)
    ca = _ca_ngay(client, h)
    eid = _nv(client, h, ca, ten="Hai phiên TC")
    _phieu(client, h, eid, tu=1050, den=1290)
    _bam(eid, 1, 8, 0, "in"); _bam(eid, 1, 17, 0, "out")
    _bam(eid, 1, 17, 30, "in"); _bam(eid, 1, 18, 30, "out")
    _bam(eid, 1, 19, 0, "in"); _bam(eid, 1, 21, 30, "out")
    assert _row(client, h, eid)["days"]["1"]["ot_minutes"] == 210
    assert _day(client, h, eid)["ot_suggestion"] is None
