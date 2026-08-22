"""KẸP GIỜ RA THEO PHIẾU VỀ SỚM (chủ chốt 12/08/2026).

Chủ chốt hỏi: *"Ca đến 18h, tôi viết đơn xin về sớm 2 tiếng là 16h phải về rồi, mà 17h tôi mới
bấm ra thì hệ thống ghi nhận 16h hay 17h?"* — engine lúc đó lấy **17h** (giờ bấm thật). Chủ chốt:
*"Vậy sai rồi, phải lấy 16h chứ."*

HAI CHUYỆN CÓ DỮ LIỆU Y HỆT NHAU, hệ thống không phân biệt được:
  (A) về đúng 16h nhưng QUÊN BẤM, 17h mới bấm  → luật cũ cộng dư 1 tiếng, xưởng chịu thiệt
  (B) xin về 16h nhưng Ở LẠI LÀM tới 17h       → luật mới cắt mất 1 tiếng công thật

Chọn cách nào cũng là chọn **chịu sai ở đâu**. Chủ chốt chọn chịu sai ở (B): *"Kệ họ, họ có thể
sửa công hoặc là xoá phiếu tạo lại"* — nên hai đường đó PHẢI còn dùng được, và đó chính là hai ca
đối chứng quan trọng nhất trong file này.
"""

from __future__ import annotations

from datetime import datetime, timezone

from app.db import SessionLocal
from app.repositories.attendance_repo import AttendanceRepository
from app.repositories.rbac_repo import DepartmentRepository

ADMIN = {"username": "admin", "password": "admin123"}
NAM, THANG, NGAY = 2026, 6, 1          # 01/06/2026 = Thứ Hai
NGAY_STR = f"{NAM}-{THANG:02d}-{NGAY:02d}"


def _h(client) -> dict[str, str]:
    tok = client.post("/api/auth/login", json=ADMIN).json()["access_token"]
    return {"Authorization": f"Bearer {tok}"}


def _dept_id(name: str) -> int:
    db = SessionLocal()
    try:
        return DepartmentRepository(db).get_by_name(name).id
    finally:
        db.close()


def _nv_ca_8_18(client, h) -> int:
    """NV ca 08:00–18:00 (600 phút) — số tròn nên công đọc ra dễ đối chiếu."""
    r = client.post("/api/employees",
                    json={"probation_end_date": "2025-12-31", "full_name": "NV Ve Som", "department_id": _dept_id("Hành chính nhân sự"),
                          "hire_date": "2020-01-01"}, headers=h)
    assert r.status_code in (200, 201), r.text
    eid = r.json()["employee"]["id"]
    items = client.get("/api/attendance/shifts", headers=h).json()["items"]
    ca = next((s for s in items if s["name"] == "Ca thử về sớm"), None)
    if ca is None:
        ca = client.post("/api/attendance/shifts",
                         json={"name": "Ca thử về sớm", "start_time": "08:00",
                               "end_time": "18:00"}, headers=h).json()
    assert client.put(f"/api/employees/{eid}/shift",
                      json={"default_shift_id": ca["id"], "effective_from": "2020-01-01"},
                      headers=h).status_code == 200
    return eid


def _bam(eid: int, gio_vn: float, kieu: str) -> None:
    tong = int(round(gio_vn * 60)) - 7 * 60          # UTC = VN − 7
    db = SessionLocal()
    try:
        AttendanceRepository(db).create_log(
            employee_id=eid, check_type=kieu, within_range=True,
            checked_at=datetime(NAM, THANG, NGAY, tong // 60, tong % 60, tzinfo=timezone.utc))
    finally:
        db.close()


def _phieu_ve_som(client, h, eid: int, *, tu=960, den=1080) -> int:
    """Phiếu về sớm 16:00 → 18:00 (phút 960 → 1080), khai hộ ⇒ DUYỆT LUÔN."""
    r = client.post("/api/late-early",
                    json={"employee_id": eid, "work_date": NGAY_STR,
                          "from_minute": tu, "to_minute": den, "reason": "việc nhà"},
                    headers=h)
    assert r.status_code in (200, 201), r.text
    return r.json()["id"]


def _cong(client, h, eid: int) -> float:
    ts = client.get("/api/attendance/timesheet", params={"year": NAM, "month": THANG},
                    headers=h).json()
    row = next(r for r in ts["rows"] if r["employee_id"] == eid)
    return float(row["total_cong"] or 0)


# ══════════════════════════════════════════════ luật chính


def test_bam_ra_MUON_hon_phieu_thi_lay_gio_PHIEU(client):
    """⭐ Ca gốc chủ chốt nêu. Ca 08–18 (600'), xin về 16:00, bấm ra 17:00.

    Lấy giờ phiếu ⇒ làm 08:00–16:00 = 480' ⇒ công 0,80.
    (Luật cũ lấy giờ bấm ⇒ 540' ⇒ 0,90 — xưởng trả dư 1 tiếng cho người quên bấm.)"""
    h = _h(client)
    eid = _nv_ca_8_18(client, h)
    _phieu_ve_som(client, h, eid)
    _bam(eid, 8, "in")
    _bam(eid, 17, "out")

    assert _cong(client, h, eid) == 0.8, "vẫn đang lấy giờ bấm 17:00"


def test_khong_co_phieu_thi_van_lay_gio_BAM(client):
    """Vế đối chứng: không phiếu thì không kẹp. Thiếu ca này thì chỉ cần luôn cắt công về 0,80 là
    test trên vẫn xanh."""
    h = _h(client)
    eid = _nv_ca_8_18(client, h)
    _bam(eid, 8, "in")
    _bam(eid, 17, "out")

    assert _cong(client, h, eid) == 0.9


def test_bam_ra_SOM_hon_phieu_thi_lay_gio_BAM(client):
    """Phiếu là TRẦN, không phải sàn. Xin về 16:00 mà 15:00 đã về ⇒ tính 15:00 (420' ⇒ 0,70),
    phần vắng vượt đơn vẫn phạt như cũ."""
    h = _h(client)
    eid = _nv_ca_8_18(client, h)
    _phieu_ve_som(client, h, eid)
    _bam(eid, 8, "in")
    _bam(eid, 15, "out")

    assert _cong(client, h, eid) == 0.7


def test_phieu_DI_MUON_khong_dung_toi_gio_ra(client):
    """Phiếu đầu ca (08:00–09:00) là ĐI MUỘN — không phải về sớm, không được kẹp giờ ra.
    Gộp hai loại phiếu vào một luật là cắt oan công của người đi muộn rồi ở lại làm đủ."""
    h = _h(client)
    eid = _nv_ca_8_18(client, h)
    _phieu_ve_som(client, h, eid, tu=480, den=540)     # 08:00 → 09:00
    _bam(eid, 9, "in")
    _bam(eid, 18, "out")

    assert _cong(client, h, eid) == 0.9, "phiếu đi muộn đang bị đem đi kẹp giờ ra"


# ══════════════════════════════════════════════ hai đường lui chủ chốt yêu cầu


def test_XOA_PHIEU_thi_cong_ve_theo_gio_bam(client):
    """Đường lui 1: *"xoá phiếu tạo lại"*. Không còn phiếu ⇒ không kẹp ⇒ công về đúng giờ bấm."""
    h = _h(client)
    eid = _nv_ca_8_18(client, h)
    rid = _phieu_ve_som(client, h, eid)
    _bam(eid, 8, "in")
    _bam(eid, 17, "out")
    assert _cong(client, h, eid) == 0.8

    assert client.post(f"/api/late-early/{rid}/cancel", headers=h).status_code == 200
    assert _cong(client, h, eid) == 0.9, "huỷ phiếu rồi mà công vẫn bị kẹp"


def test_HCNS_CHAM_BU_thi_THANG_phieu(client):
    """Đường lui 2: *"sửa công"*. Chấm bù là hành động CÓ CHỦ Ý của người quản — có lý do, có tên
    người sửa — nên nó thắng phiếu. Thợ quên bấm thì không có gì cả.

    Thiếu ngoại lệ này thì "sửa công" chạy xong mà số không đổi, HCNS tưởng hệ thống nuốt thao tác."""
    h = _h(client)
    eid = _nv_ca_8_18(client, h)
    _phieu_ve_som(client, h, eid)
    _bam(eid, 8, "in")
    assert _cong(client, h, eid) == 0.0        # thiếu chấm ra ⇒ ngày treo

    r = client.post("/api/attendance/adjust",
                    json={"employee_id": eid, "date": NGAY_STR, "check_type": "out",
                          "time": "17:00", "reason": "NV quên chấm ra, đã xác nhận ở lại làm"},
                    headers=h)
    assert r.status_code == 200, r.text
    assert _cong(client, h, eid) == 0.9, (
        "chấm bù không thắng được phiếu — 'sửa công' thành đường cụt"
    )
