"""ĐỢT C (12/08/2026) — SUẤT CƠM TĂNG CA.

Chủ chốt: *"Tăng ca 3 tiếng sẽ được thưởng tiền cơm, cái này setup động nha; riêng tăng ca ngày
chủ nhật thì cứ tăng ca là được tiền cơm cho dù nó là 1 tiếng hay 2 tiếng."*

Chốt tiếp 12/08/2026: **"chủ nhật" = NGÀY NGHỈ THEO LỊCH CHUNG**, không cứng ngày Chủ nhật. Nhà máy
đổi ngày nghỉ thì luật đi theo, và **ngày lễ / ngày `off1x` cũng vào nhánh dễ** — `is_working_day`
trả `False` cho cả ba loại.

VÌ SAO MỤC NÀY TỐN NHẤT
-----------------------
Ảnh chụp kỳ công chỉ giữ **TỔNG phút tăng ca cả tháng** (`ot_minutes`), mà luật hỏi *"ngày nào tăng
ca ≥ 3 giờ"* — câu hỏi theo NGÀY. Nên phải thêm `attendance_period_lines.ot_days_json` và khớp CẢ
HAI nhánh của `metrics_map`. Đây đúng lớp lỗi đã dính ba lần với `excused_cong` · `paid_leave_days`
· `ca_lam`: thiếu một khoá ở nhánh ảnh chụp là **số nhảy đúng lúc chốt công**.
"""

from __future__ import annotations

from datetime import datetime, timezone

from app.db import SessionLocal
from app.repositories.attendance_repo import AttendanceRepository
from app.repositories.employee_repo import EmployeeRepository
from app.repositories.rbac_repo import DepartmentRepository

ADMIN = {"username": "admin", "password": "admin123"}
NAM, THANG = 2026, 6
MUC = 30_000          # tiền một suất, khai ở Cấu hình lương
NGUONG = 180          # 3 giờ


def _h(client) -> dict[str, str]:
    tok = client.post("/api/auth/login", json=ADMIN).json()["access_token"]
    return {"Authorization": f"Bearer {tok}"}


def _dept_id(name: str) -> int:
    db = SessionLocal()
    try:
        return DepartmentRepository(db).get_by_name(name).id
    finally:
        db.close()


def _nv(client, h, ten="NV Com Tang Ca") -> int:
    r = client.post("/api/employees",
                    json={"probation_end_date": "2025-12-31", "full_name": ten, "department_id": _dept_id("Hành chính nhân sự"),
                          "hire_date": "2020-01-01"}, headers=h)
    assert r.status_code in (200, 201), r.text
    eid = r.json()["employee"]["id"]
    client.post(f"/api/luong/salaries/{eid}",
                json={"effective_from": "2026-01-01", "luong_vi_tri": 10_000_000}, headers=h)
    return eid


def _ca_hanh_chinh(client, h, eid: int) -> int:
    """Ca 08:00–17:00 hiệu lực từ 2020 — chấm ngoài khung ca mới sinh phút tăng ca."""
    items = client.get("/api/attendance/shifts", headers=h).json()["items"]
    ca = next((s for s in items if s["name"] == "Ca thử cơm TC"), None)
    if ca is None:
        ca = client.post("/api/attendance/shifts",
                         json={"name": "Ca thử cơm TC", "start_time": "08:00",
                               "end_time": "17:00"}, headers=h).json()
    r = client.put(f"/api/employees/{eid}/shift",
                   json={"default_shift_id": ca["id"], "effective_from": "2020-01-01"}, headers=h)
    assert r.status_code == 200, r.text
    return ca["id"]


def _lam_ngay(client, h, eid: int, ngay: int, *, ot_gio: float = 0) -> None:
    """Ca chính 08:00–17:00 VN, rồi MỘT PHIÊN TĂNG CA riêng 17:00 → 17:00+`ot_gio`.

    ⚠️ Phải là HAI CẶP chấm. `compute_day_cong` đòi phiên tăng ca có ĐỦ CẶP vào–ra riêng; bấm một
    lèo 08:00 → 22:00 thì `ot_minutes = 0` và ca đo hỏng trước khi chạm tới luật đang thử.
    (Giờ UTC = giờ VN − 7.)"""
    db = SessionLocal()
    try:
        repo = AttendanceRepository(db)

        def bam(kieu: str, gio_vn: float) -> None:
            tong = int(round(gio_vn * 60)) - 7 * 60
            repo.create_log(employee_id=eid, check_type=kieu, within_range=True,
                            checked_at=datetime(NAM, THANG, ngay, tong // 60, tong % 60,
                                                tzinfo=timezone.utc))

        bam("in", 8)
        bam("out", 17)
        if ot_gio > 0:
            bam("in", 17)
            bam("out", 17 + ot_gio)
    finally:
        db.close()


def _phieu_tang_ca(client, h, eid: int, ngay: int, *, tu=1020, den=1320) -> None:
    """Phiếu tăng ca ĐÃ DUYỆT — engine chỉ trả tiền phần giờ vượt ca NẰM TRONG phiếu."""
    r = client.post("/api/overtime",
                    json={"employee_id": eid, "work_date": f"{NAM}-{THANG:02d}-{ngay:02d}",
                          "from_minute": tu, "to_minute": den, "reason": "chạy đơn"},
                    headers=h)
    assert r.status_code in (200, 201), r.text


def _khai_com_tc(client, h, *, muc=MUC, nguong=NGUONG) -> None:
    r = client.put("/api/luong/params",
                   json={"com_tang_ca_muc": muc, "com_tang_ca_nguong_phut": nguong}, headers=h)
    assert r.status_code == 200, r.text


def _dong(client, h, eid: int) -> dict:
    gen = client.post("/api/luong/generate", json={"year": NAM, "month": THANG},
                      headers=h).json()
    return next(l for l in gen["lines"] if l["employee_id"] == eid)


def _ngay_lam_viec(client, h) -> list[int]:
    """Danh sách ngày LÀM VIỆC của tháng theo Lịch chung — lấy từ chính bảng công."""
    ts = client.get("/api/attendance/timesheet", params={"year": NAM, "month": THANG},
                    headers=h).json()
    hol = {int(x) for x in (ts.get("holidays") or {}).get("days", [])}
    import calendar as _cal
    return [d for d in range(1, _cal.monthrange(NAM, THANG)[1] + 1)
            if _cal.weekday(NAM, THANG, d) < 6 and d not in hol]


def _ngay_nghi(client, h) -> list[int]:
    import calendar as _cal
    return [d for d in range(1, _cal.monthrange(NAM, THANG)[1] + 1)
            if _cal.weekday(NAM, THANG, d) == 6]


# ══════════════════════════════════════════════ luật


def test_ngay_lam_viec_du_nguong_thi_co_suat(client):
    """Ngày thường phải ĐỦ NGƯỠNG. 17:00 → 22:00 = 5 giờ tăng ca ⇒ vượt 3 giờ."""
    h = _h(client)
    eid = _nv(client, h)
    _ca_hanh_chinh(client, h, eid)
    _khai_com_tc(client, h)
    d = _ngay_lam_viec(client, h)[0]
    _phieu_tang_ca(client, h, eid, d)
    _lam_ngay(client, h, eid, d, ot_gio=5)      # 17:00 → 22:00

    ts = client.get("/api/attendance/timesheet", params={"year": NAM, "month": THANG},
                    headers=h).json()
    row = next(r for r in ts["rows"] if r["employee_id"] == eid)
    ln = _dong(client, h, eid)
    assert ln["ot_pay"] > 0, (
        f"ca đo hỏng: chưa sinh được phút tăng ca nào. "
        f"ot_minutes={row.get('ot_minutes')} total_cong={row.get('total_cong')} "
        f"ot_days={row.get('ot_days')}"
    )
    assert ln["com_tang_ca_pay"] == MUC


def test_ngay_lam_viec_CHUA_du_nguong_thi_khong_co(client):
    """17:00 → 19:00 = 2 giờ, dưới ngưỡng 3 giờ ⇒ KHÔNG có suất. Vế đối chứng bắt buộc:
    thiếu nó thì chỉ cần trả suất cho mọi ngày có tăng ca là test vẫn xanh."""
    h = _h(client)
    eid = _nv(client, h)
    _ca_hanh_chinh(client, h, eid)
    _khai_com_tc(client, h)
    d = _ngay_lam_viec(client, h)[0]
    _phieu_tang_ca(client, h, eid, d, tu=1020, den=1140)
    _lam_ngay(client, h, eid, d, ot_gio=2)      # 17:00 → 19:00, dưới ngưỡng

    ln = _dong(client, h, eid)
    assert ln["ot_pay"] > 0
    assert ln["com_tang_ca_pay"] == 0


def test_ngay_NGHI_thi_mot_gio_cung_co_suat(client):
    """⭐ Vế chính chủ chốt nêu: "chủ nhật cứ tăng ca là được tiền cơm dù 1 hay 2 tiếng".

    Ngày nghỉ KHÔNG có khung ca nên mọi giờ làm đều là tăng ca — chỉ cần > 0 phút."""
    h = _h(client)
    eid = _nv(client, h)
    _ca_hanh_chinh(client, h, eid)
    _khai_com_tc(client, h)
    cn = _ngay_nghi(client, h)[0]
    # Cửa sổ phiếu PHẢI phủ đúng phiên tăng ca (17:00–19:00), nếu không `ot_minutes = 0`:
    # phiếu là GIẤY PHÉP + TRẦN, phần nằm ngoài phiếu không ra tiền.
    _phieu_tang_ca(client, h, eid, cn, tu=1020, den=1140)
    _lam_ngay(client, h, eid, cn, ot_gio=2)      # ngày nghỉ, chỉ 2 tiếng — dưới ngưỡng 3h

    ln = _dong(client, h, eid)
    assert ln["com_tang_ca_pay"] == MUC, (
        "ngày nghỉ mà vẫn bắt đủ ngưỡng — luật ngày nghỉ chưa chạy"
    )


def test_muc_bang_0_thi_TAT_han(client):
    """Mặc định 0 = tắt. Bật sẵn một khoản ra tiền cho cả nhà máy mà chưa ai duyệt số là tự ý
    tăng quỹ lương."""
    h = _h(client)
    eid = _nv(client, h)
    _ca_hanh_chinh(client, h, eid)
    _khai_com_tc(client, h, muc=0)
    d = _ngay_lam_viec(client, h)[0]
    _phieu_tang_ca(client, h, eid, d)
    _lam_ngay(client, h, eid, d, ot_gio=5)

    assert _dong(client, h, eid)["com_tang_ca_pay"] == 0


def test_com_tang_ca_MIEN_THUE(client):
    """Chủ chốt 12/08/2026: "Có" — đi chung nhóm cơm ca.

    ⚠️ Đo bằng CHÊNH LỆCH giữa hai lần tính, không so `thu_nhap_mien_thue` với một hằng số: cơm ca
    của chính ngày đó cũng nằm trong phần miễn nên `>= MUC` luôn đúng kể cả khi cơm tăng ca KHÔNG
    được miễn. Bản đầu tiên của ca này xanh giả đúng vì vậy — đột biến "thôi miễn thuế" không cắn.

    Cách đo đúng: bật khoản lên thì GROSS tăng đúng một suất, còn THU NHẬP CHỊU THUẾ phải ĐỨNG YÊN."""
    h = _h(client)
    eid = _nv(client, h)
    _ca_hanh_chinh(client, h, eid)
    d = _ngay_lam_viec(client, h)[0]
    _phieu_tang_ca(client, h, eid, d)
    _lam_ngay(client, h, eid, d, ot_gio=5)

    _khai_com_tc(client, h, muc=0)
    tat = _dong(client, h, eid)
    _khai_com_tc(client, h, muc=MUC)
    bat = _dong(client, h, eid)

    assert bat["com_tang_ca_pay"] == MUC and tat["com_tang_ca_pay"] == 0
    assert float(bat["gross"]) - float(tat["gross"]) == MUC, "khoản này chưa cộng vào gross"
    assert float(bat["thu_nhap_chiu_thue"]) == float(tat["thu_nhap_chiu_thue"]), (
        "bật cơm tăng ca mà thu nhập CHỊU THUẾ tăng theo — khoản này chưa được miễn"
    )
    assert float(bat["pit"]) == float(tat["pit"])


def test_hai_o_cau_hinh_luu_that(client):
    """`update_params` có DANH SÁCH TRẮNG — tên nào không khai thì PUT chạy ngon lành mà số không
    đổi. `phu_cap_ca_min_cong` đã dính đúng lỗi đó một lần."""
    h = _h(client)
    _khai_com_tc(client, h, muc=45_000, nguong=240)
    p = client.get("/api/luong/params", headers=h).json()
    assert p["com_tang_ca_muc"] == 45_000 and p["com_tang_ca_nguong_phut"] == 240


# ══════════════════════════════════════════════ ảnh chụp — chỗ dễ vỡ nhất


def test_CHOT_CONG_XONG_tien_com_tang_ca_KHONG_DOI(client):
    """⭐ Lớp lỗi đã dính BA LẦN (`excused_cong` · `paid_leave_days` · `ca_lam`): thiếu một khoá ở
    nhánh ảnh chụp thì số CHẠY ĐÚNG lúc kỳ còn nháp và NHẢY đúng lúc HCNS bấm Chốt công.

    Ca này đo hai lần trên cùng dữ liệu: trước chốt (nhánh live) và sau chốt (nhánh ảnh chụp)."""
    h = _h(client)
    eid = _nv(client, h)
    _ca_hanh_chinh(client, h, eid)
    _khai_com_tc(client, h)
    d = _ngay_lam_viec(client, h)[0]
    _phieu_tang_ca(client, h, eid, d)
    _lam_ngay(client, h, eid, d, ot_gio=5)

    truoc = _dong(client, h, eid)["com_tang_ca_pay"]
    assert truoc == MUC

    assert client.post("/api/attendance/period/lock", json={"year": NAM, "month": THANG},
                       headers=h).status_code == 200
    sau = _dong(client, h, eid)["com_tang_ca_pay"]
    assert sau == truoc, (
        f"chốt công xong tiền cơm tăng ca nhảy {truoc} → {sau} — nhánh ảnh chụp thiếu `ot_days`"
    )


def test_giao_dien_that_su_hien_va_khai_duoc(client):
    """Máy chủ đổi, giao diện quên — khuôn sai đã lặp 4 lần vòng này."""
    from tests._fe_source import (
        MAN_CAU_HINH_LUONG, MAN_LUONG, doc_file_fe, doc_module_fe,
    )

    assert "com_tang_ca_pay" in doc_file_fe("api", "client.ts")
    assert "com_tang_ca_muc" in doc_file_fe("api", "client.ts")
    # Màn Cấu hình lương là thư mục con của màn Lương nhưng `doc_module_fe` KHÔNG nuốt nó vào
    # (nó có `index.ts` riêng) — nhờ vậy hai câu hỏi dưới đây vẫn là HAI câu hỏi khác nhau.
    assert "Cơm tăng ca" in doc_module_fe(*MAN_LUONG), (
        "phiếu lương không có dòng Cơm tăng ca"
    )
    cfg = doc_module_fe(*MAN_CAU_HINH_LUONG)
    assert "com_tang_ca_muc" in cfg and "com_tang_ca_nguong_phut" in cfg, (
        "màn Cấu hình lương không khai được hai ô — 'setup động' thành số cứng"
    )
