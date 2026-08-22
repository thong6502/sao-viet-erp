"""Lịch sử thay đổi ca (`employee_shift_change_logs`) — chủ 28/07/2026.

Ca của một người đến từ HAI lớp và có **5 đường** ghi. Quên móc một đường là màn lịch sử báo
"không có thay đổi nào" trong khi ca vừa bị đổi — sai kiểu đó tệ hơn là không có màn lịch sử.
File này có một test cho TỪNG đường, cố ý không gộp.
"""
from __future__ import annotations

from app.db import SessionLocal
from app.models.employee import EmployeeShiftChangeLog

from .test_work_shifts_api import (
    _admin_token,
    _dept_id,
    _h,
    _mk_emp,
    _mk_shift,
    _save_plan,
)


def _logs(employee_id: int | None = None, *, kind: str | None = None,
          origin: str | None = None) -> list:
    """Dòng lịch sử của một NV. LỌC ĐƯỢC theo lớp: dựng ca nền trong phần setup cũng sinh log
    (đúng thiết kế), nên test về lưới phải lọc `kind='day'` chứ không đếm tổng."""
    db = SessionLocal()
    try:
        rows = db.query(EmployeeShiftChangeLog).order_by(EmployeeShiftChangeLog.id).all()
        if employee_id is not None:
            rows = [r for r in rows if r.employee_id == employee_id]
        if kind is not None:
            rows = [r for r in rows if r.kind == kind]
        if origin is not None:
            rows = [r for r in rows if r.origin == origin]
        # Ngắt khỏi session để test đọc thoải mái sau khi đóng.
        return [
            type("Row", (), {c.name: getattr(r, c.name)
                             for c in EmployeeShiftChangeLog.__table__.columns})()
            for r in rows
        ]
    finally:
        db.close()


def _set_base(client, token, eid, shift_id, effective_from="2026-01-01", expect=200):
    r = client.put(f"/api/employees/{eid}/shift",
                   json={"default_shift_id": shift_id, "effective_from": effective_from},
                   headers=_h(token))
    assert r.status_code == expect, r.text
    return r


# --- Lớp 1: ô lưới phân ca --------------------------------------------------


def test_luoi_ghi_dung_truoc_sau_va_co_co_ke_thua(client):
    """⭐ Tô ô lên ngày đang KẾ THỪA ca nền: log phải nhớ ca nền là ca trước đó."""
    token = _admin_token(client)
    base = _mk_shift(client, token, "Nền log", "08:00", "17:00")
    night = _mk_shift(client, token, "Khuya log", "22:00", "06:00", overnight=True)
    emp = _mk_emp(client, token, "NV Log Lưới")
    _set_base(client, token, emp["id"], base["id"])

    _save_plan(client, token, [{"employee_id": emp["id"], "work_date": "2026-06-10",
                                "action": "set", "shift_id": night["id"]}])

    rows = _logs(emp["id"], kind="day")
    assert len(rows) == 1, f"phải có đúng 1 dòng lịch sử lưới, có {len(rows)}"
    r = rows[0]
    assert r.kind == "day" and r.origin == "grid" and r.action == "set"
    assert r.inherited_before is True, "trước đó ô đang kế thừa ca nền"
    assert r.shift_id_before == base["id"], "ca trước phải là CA NỀN, không phải None"
    assert r.shift_id_after == night["id"]
    assert str(r.apply_date) == "2026-06-10"


def test_luoi_khong_ghi_khi_luu_lai_y_nguyen(client):
    """⭐ Lưu lại đúng giá trị cũ ⇒ KHÔNG đẻ dòng lịch sử.

    Lưới hay được bấm Lưu cả tháng một lần; không lọc là mỗi lần lưu đẻ vài chục dòng rỗng và
    bắn ngần ấy thông báo rác — chuông mất giá trị sau đúng một ngày."""
    token = _admin_token(client)
    night = _mk_shift(client, token, "Khuya lặp", "22:00", "06:00", overnight=True)
    emp = _mk_emp(client, token, "NV Lưu Lặp")
    cell = [{"employee_id": emp["id"], "work_date": "2026-06-11",
             "action": "set", "shift_id": night["id"]}]

    _save_plan(client, token, cell)
    n1 = len(_logs(emp["id"]))
    _save_plan(client, token, cell)       # lưu lại y nguyên
    _save_plan(client, token, cell)       # và lần nữa
    assert len(_logs(emp["id"])) == n1, "lưu lại y nguyên vẫn đẻ thêm dòng lịch sử"


def test_luoi_off_va_inherit(client):
    """`off` (nghỉ theo lịch) và `inherit` (về ca nền) đều phải có dấu vết."""
    token = _admin_token(client)
    base = _mk_shift(client, token, "Nền off", "08:00", "17:00")
    day = _mk_shift(client, token, "Ngày off", "09:00", "18:00")
    emp = _mk_emp(client, token, "NV Off Inherit")
    _set_base(client, token, emp["id"], base["id"])

    _save_plan(client, token, [{"employee_id": emp["id"], "work_date": "2026-06-12",
                                "action": "set", "shift_id": day["id"]}])
    _save_plan(client, token, [{"employee_id": emp["id"], "work_date": "2026-06-12",
                                "action": "off"}])
    _save_plan(client, token, [{"employee_id": emp["id"], "work_date": "2026-06-12",
                                "action": "inherit"}])

    rows = _logs(emp["id"], kind="day")
    assert [r.action for r in rows] == ["set", "off", "inherit"]
    off = rows[1]
    assert off.shift_id_before == day["id"] and off.is_off_after is True
    inh = rows[2]
    assert inh.is_off_before is True
    # Về kế thừa ⇒ ca SAU là ca NỀN, không phải None (đây là chỗ `shift_id_on` trả sai vì nó
    # ưu tiên đúng cái ô sắp bị xoá — phải dùng `base_shift_id_on`).
    assert inh.shift_id_after == base["id"], "gỡ ô phải rơi về ca nền, không phải 'không ca'"


# --- Lớp 2: ca nền — 4 đường ghi -------------------------------------------


def test_ca_nen_panel_gan_ca_mot_nguoi(client):
    """Đường `base_panel`: panel Gán ca cho một người."""
    token = _admin_token(client)
    a = _mk_shift(client, token, "Nền A panel", "08:00", "17:00")
    b = _mk_shift(client, token, "Nền B panel", "14:00", "22:00")
    emp = _mk_emp(client, token, "NV Ca Nền Panel")

    _set_base(client, token, emp["id"], a["id"], "2026-01-01")
    _set_base(client, token, emp["id"], b["id"], "2026-08-01")

    rows = _logs(emp["id"])
    assert [r.kind for r in rows] == ["base", "base"]
    assert [r.origin for r in rows] == ["base_panel", "base_panel"]
    doi = rows[-1]
    assert doi.shift_id_before == a["id"] and doi.shift_id_after == b["id"]
    assert str(doi.apply_date) == "2026-08-01", "ca nền lưu NGÀY HIỆU LỰC, không phải ngày bấm"


def test_ca_nen_gan_hang_loat_ghi_tung_nguoi(client):
    """⭐ Đường `base_bulk`: 3 NV ⇒ 3 dòng lịch sử, KHÔNG phải 1 dòng gộp.

    Gộp thì không tra được ai bị đổi từ ca gì — đúng thứ màn lịch sử sinh ra để trả lời."""
    token = _admin_token(client)
    old = _mk_shift(client, token, "Nền cũ bulk", "08:00", "17:00")
    new = _mk_shift(client, token, "Nền mới bulk", "22:00", "06:00", overnight=True)
    emps = [_mk_emp(client, token, f"NV Bulk Nền {i}") for i in range(3)]
    for e in emps:
        _set_base(client, token, e["id"], old["id"], "2026-01-01")

    r = client.put("/api/employees/shift/bulk", headers=_h(token), json={
        "employee_ids": [e["id"] for e in emps],
        "default_shift_id": new["id"], "effective_from": "2026-09-01"})
    assert r.status_code == 200, r.text
    assert r.json()["updated"] == 3

    for e in emps:
        rows = [x for x in _logs(e["id"]) if x.origin == "base_bulk"]
        assert len(rows) == 1, f"NV {e['id']} phải có đúng 1 dòng bulk, có {len(rows)}"
        assert rows[0].shift_id_before == old["id"] and rows[0].shift_id_after == new["id"]


def test_ca_nen_sua_ho_so_nhan_vien(client):
    """Đường `profile`: đổi ô ca ngay trong hồ sơ NV cũng phải để lại dấu vết."""
    token = _admin_token(client)
    a = _mk_shift(client, token, "Nền hồ sơ A", "08:00", "17:00")
    b = _mk_shift(client, token, "Nền hồ sơ B", "14:00", "22:00")
    emp = _mk_emp(client, token, "NV Sửa Hồ Sơ")
    _set_base(client, token, emp["id"], a["id"], "2026-01-01")

    r = client.put(f"/api/employees/{emp['id']}", headers=_h(token),
                   json={"full_name": "NV Sửa Hồ Sơ", "default_shift_id": b["id"],
                         "probation_end_date": "2025-12-31"})
    assert r.status_code == 200, r.text

    rows = [x for x in _logs(emp["id"]) if x.origin == "profile"]
    assert len(rows) == 1, "đổi ca trong hồ sơ NV không được lọt khỏi lịch sử"
    assert rows[0].shift_id_before == a["id"] and rows[0].shift_id_after == b["id"]


def test_ca_nen_go_moc_gan_nham(client):
    """Đường `base_remove`: gỡ mốc ⇒ ca rơi về mốc CÒN LẠI, và điều đó phải ghi rõ."""
    token = _admin_token(client)
    a = _mk_shift(client, token, "Nền gỡ A", "08:00", "17:00")
    b = _mk_shift(client, token, "Nền gỡ B", "14:00", "22:00")
    emp = _mk_emp(client, token, "NV Gỡ Mốc")
    _set_base(client, token, emp["id"], a["id"], "2026-01-01")
    _set_base(client, token, emp["id"], b["id"], "2026-10-01")

    moc = client.get(f"/api/employees/{emp['id']}/shift-history",
                     headers=_h(token)).json()["items"]
    nham = next(m for m in moc if m["effective_from"] == "2026-10-01")
    r = client.delete(f"/api/employees/{emp['id']}/shift-history/{nham['id']}",
                      headers=_h(token))
    assert r.status_code in (200, 204), r.text

    rows = _logs(emp["id"], origin="base_remove")
    assert len(rows) == 1
    assert rows[0].action == "remove"
    assert rows[0].shift_id_before == b["id"], "phải nhớ mốc vừa gỡ vốn là ca gì"
    assert rows[0].shift_id_after == a["id"], "gỡ xong rơi về mốc còn lại"


def test_tao_ho_so_moi_khong_sinh_dong_lich_su(client):
    """⭐ Chốt của chủ: gán ca LẦN ĐẦU lúc lập hồ sơ KHÔNG phải "đổi ca" ⇒ không ghi.

    Ghi vào chỉ làm lịch sử lẫn dòng rác; ca đầu tiên vẫn tra được ở bảng mốc ca nền."""
    token = _admin_token(client)
    sh = _mk_shift(client, token, "Ca lúc tạo", "08:00", "17:00")
    r = client.post("/api/employees", headers=_h(token), json={
        "probation_end_date": "2025-12-31",
        "full_name": "NV Mới Tinh", "department_id": _dept_id("Hành chính nhân sự"),
        "hire_date": "2026-01-01", "default_shift_id": sh["id"]})
    assert r.status_code == 201, r.text
    eid = r.json()["employee"]["id"]
    assert _logs(eid) == [], "tạo hồ sơ mới không được đẻ dòng lịch sử"


# --- API lịch sử + hộp thư --------------------------------------------------


def test_api_lich_su_hien_ca_hai_lop_va_loc_duoc(client):
    """⭐ Màn lịch sử phải hiện CẢ ô lưới lẫn ca nền, và lọc tách được hai lớp."""
    token = _admin_token(client)
    a = _mk_shift(client, token, "API nền A", "08:00", "17:00")
    b = _mk_shift(client, token, "API đè B", "14:00", "22:00")
    emp = _mk_emp(client, token, "NV API Lịch Sử")
    _set_base(client, token, emp["id"], a["id"], "2026-01-01")
    _save_plan(client, token, [{"employee_id": emp["id"], "work_date": "2026-06-20",
                                "action": "set", "shift_id": b["id"]}])

    def get(**kw):
        q = "&".join(f"{k}={v}" for k, v in kw.items())
        r = client.get(f"/api/attendance/shift-changes?employee_id={emp['id']}&{q}",
                       headers=_h(token))
        assert r.status_code == 200, r.text
        return r.json()["items"]

    tat_ca = get()
    assert {x["kind"] for x in tat_ca} == {"day", "base"}, "thiếu một lớp trong lịch sử"

    # Dòng phải đọc được NGAY, không bắt người xem đi tra id ca.
    o_luoi = next(x for x in tat_ca if x["kind"] == "day")
    assert o_luoi["shift_name_before"] == "API nền A"
    assert o_luoi["shift_name_after"] == "API đè B"
    assert o_luoi["employee_name"] == "NV API Lịch Sử"
    assert o_luoi["actor_name"] is not None, "phải biết AI sửa"

    assert all(x["kind"] == "base" for x in get(kind="base"))
    assert all(x["kind"] == "day" for x in get(kind="day"))


def test_api_loc_thang_theo_NGAY_SUA_khong_theo_ngay_ap_dung(client):
    """⭐ Lọc tháng phải theo LÚC SỬA, không theo ngày áp dụng.

    Bẫy thật gặp phải: hôm nay đổi ca nền áp dụng từ THÁNG SAU. Lọc theo `apply_date` thì dòng
    đó biến mất khỏi màn tháng này — vừa bấm xong đã không thấy đâu, đúng lúc người ta cần đối
    chiếu nhất. `apply_date` chỉ là dữ liệu HIỂN THỊ trên dòng."""
    from datetime import date

    token = _admin_token(client)
    a = _mk_shift(client, token, "Nền lọc A", "08:00", "17:00")
    b = _mk_shift(client, token, "Nền lọc B", "14:00", "22:00")
    emp = _mk_emp(client, token, "NV Lọc Theo Ngày Sửa")
    _set_base(client, token, emp["id"], a["id"], "2026-01-01")
    # Hiệu lực TƯƠNG LAI xa (mốc đặt hôm nay nhưng áp dụng sang năm sau).
    _set_base(client, token, emp["id"], b["id"], "2027-03-01")

    hom_nay = date.today()
    r = client.get(
        f"/api/attendance/shift-changes?employee_id={emp['id']}"
        f"&year={hom_nay.year}&month={hom_nay.month}&kind=base",
        headers=_h(token))
    assert r.status_code == 200, r.text
    items = r.json()["items"]
    assert any(x["apply_date"] == "2027-03-01" for x in items), \
        "mốc vừa đặt hôm nay bị biến mất khỏi màn tháng này chỉ vì hiệu lực ở tương lai"


def test_hop_thu_va_badge_cua_nhan_vien(client):
    """NV có tài khoản: badge đếm chưa đọc, bấm đã đọc thì về 0."""
    token = _admin_token(client)
    sh = _mk_shift(client, token, "Ca hộp thư", "08:00", "17:00")
    other = _mk_shift(client, token, "Ca hộp thư 2", "14:00", "22:00")
    # Hồ sơ gắn với chính tài khoản admin ⇒ có `user_id` để nhận thông báo.
    me = client.get("/api/employees/me", headers=_h(token)).json()
    eid = me["employee"]["id"] if "employee" in me else me["id"]

    # Ngày hiệu lực phải SAU ngày vào làm của hồ sơ admin (không được lùi trước ngày vào làm).
    _set_base(client, token, eid, sh["id"], "2026-11-01")
    _set_base(client, token, eid, other["id"], "2026-12-01")

    n = client.get("/api/attendance/notify-summary", headers=_h(token)).json()
    assert n["unseen_shift_changes"] >= 1, "đổi ca của chính mình phải nhảy badge"

    hop = client.get("/api/attendance/my-shift-changes", headers=_h(token)).json()["items"]
    assert hop and hop[0]["notified"] is True

    # ⭐ `unseen=true` = khối báo ở màn "Công của tôi". Đọc xong PHẢI rỗng, nếu không khối đó
    # bám đầu màn vĩnh viễn (lỗi đã gặp: hiện cả tin đã đọc nên không bao giờ tắt).
    chua_doc = client.get("/api/attendance/my-shift-changes?unseen=true",
                          headers=_h(token)).json()["items"]
    assert len(chua_doc) >= 1

    client.post("/api/attendance/my-shift-changes/seen", headers=_h(token))
    n2 = client.get("/api/attendance/notify-summary", headers=_h(token)).json()
    assert n2["unseen_shift_changes"] == 0, "đọc rồi mà badge chưa về 0"

    sau_doc = client.get("/api/attendance/my-shift-changes?unseen=true",
                         headers=_h(token)).json()["items"]
    assert sau_doc == [], "đọc rồi mà khối báo vẫn còn tin để hiện"
    # Nhưng tra cứu đầy đủ thì vẫn còn — đọc rồi không phải là xoá.
    tat_ca = client.get("/api/attendance/my-shift-changes", headers=_h(token)).json()["items"]
    assert len(tat_ca) >= 1


def test_luoi_tra_ve_so_da_bao_va_chua_bao_duoc(client):
    """NV không có tài khoản đăng nhập (công nhân xưởng) ⇒ đếm vào 'chưa báo được'."""
    token = _admin_token(client)
    sh = _mk_shift(client, token, "Ca đếm báo", "08:00", "17:00")
    emp = _mk_emp(client, token, "NV Không Tài Khoản")

    res = _save_plan(client, token, [{"employee_id": emp["id"], "work_date": "2026-06-13",
                                      "action": "set", "shift_id": sh["id"]}])
    assert res["changed"] == 1
    assert res["notified"] == 0
    assert res["not_notified"] == 1, "NV chưa có tài khoản phải được đếm ra, không im lặng bỏ qua"

    rows = _logs(emp["id"])
    assert rows[0].notified_user_id is None
