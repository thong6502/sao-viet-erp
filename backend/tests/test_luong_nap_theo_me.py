"""Nạp THEO MẺ phải ra ĐÚNG số của nạp từng người (09/09/2026).

Nút "Tính lương" trước đây hỏi DB lẻ trong vòng lặp từng nhân viên: 300 người = 7.281 truy vấn,
20,7 giây (đo được, xem `docs/plan-toi-uu-tinh-luong.md`). Đợt tối ưu đổi sang nạp một lượt cho cả
kỳ. Rủi ro DUY NHẤT của kiểu sửa này là bản gom trả khác bản lẻ — mà khác ở đây là **lệch tiền của
cả bảng lương**, nên khoá lại bằng test đối chiếu hai đường trên cùng dữ liệu.
"""
from __future__ import annotations

from datetime import date

from app.db import SessionLocal
from app.deps import (
    get_accounting_repository,
    get_attendance_repository,
    get_attendance_service,
    get_audit_repository,
    get_calendar_repository,
    get_calendar_service,
    get_department_repository,
    get_employee_repository,
    get_late_early_repository,
    get_leave_repository,
    get_overtime_repository,
    get_payroll_component_repository,
    get_payroll_repository,
    get_piece_work_repository,
    get_piece_work_service,
)
from app.services.hoa_hong_service import HoaHongService
from app.services.payroll_service import PayrollService

from .test_hoa_hong_kinh_doanh import KY_DEN, KY_TU, _don, _hoa_don, _sales
from .test_work_shifts_api import _admin_token, _h, _mk_emp


def _svc(db) -> PayrollService:
    cal = get_calendar_service(get_calendar_repository(db), get_audit_repository(db), db)
    att = get_attendance_service(
        get_attendance_repository(db), get_employee_repository(db), get_audit_repository(db),
        get_leave_repository(db), cal, get_payroll_repository(db), get_overtime_repository(db),
        get_late_early_repository(db),
    )
    return PayrollService(
        get_payroll_repository(db), get_employee_repository(db), att,
        audit=get_audit_repository(db),
        piece=get_piece_work_service(get_piece_work_repository(db), db),
        departments=get_department_repository(db),
        components=get_payroll_component_repository(db),
        vouchers=get_accounting_repository(db),
    )


def _khoan(client, token, ten: str, so_tien: int, *, kind: str = "thu") -> int:
    r = client.post("/api/luong/components",
                    json={"name": ten, "kind": kind, "is_taxable": True}, headers=_h(token))
    assert r.status_code in (200, 201), r.text
    return r.json()["id"]


def _gan_khoan(client, token, emp_id: int, cap: list[tuple[int, int]]):
    r = client.put(f"/api/luong/components/employee/{emp_id}",
                   json={"items": [{"component_id": cid, "amount": tien} for cid, tien in cap]},
                   headers=_h(token))
    assert r.status_code == 200, r.text


def test_khoan_ho_so_nap_ca_me_bang_nap_tung_nguoi(client):
    """`_components_map` (cả mẻ) phải ra y hệt `_components_for` (từng người)."""
    token = _admin_token(client)
    com = _khoan(client, token, "Phu cap com me", 500_000)
    xang = _khoan(client, token, "Phu cap xang me", 300_000)

    a = _mk_emp(client, token, "Me Khoan A")["id"]
    b = _mk_emp(client, token, "Me Khoan B")["id"]
    khong_khoan = _mk_emp(client, token, "Me Khoan Trong")["id"]
    _gan_khoan(client, token, a, [(com, 500_000), (xang, 300_000)])
    _gan_khoan(client, token, b, [(com, 250_000)])

    db = SessionLocal()
    try:
        svc = _svc(db)
        repo = get_employee_repository(db)
        ids = [a, b, khong_khoan]
        theo_me = svc._components_map(ids)
        for emp_id in ids:
            tung_nguoi = svc._components_for(repo.get_by_id(emp_id))
            assert sorted(theo_me.get(emp_id, []), key=lambda c: c["component_id"]) == \
                sorted(tung_nguoi, key=lambda c: c["component_id"]), f"NV {emp_id}"
        # và không phải "khớp vì cả hai cùng rỗng"
        assert len(theo_me[a]) == 2 and len(theo_me[b]) == 1 and theo_me[khong_khoan] == []
    finally:
        db.close()


def test_hoa_hong_nap_ca_me_bang_tinh_tung_nguoi(client):
    """`hoa_hong_ky_map` phải ra đúng số của `hoa_hong_ky` cho TỪNG người, kể cả người 0 đồng."""
    e1, u1 = _sales("me hoa hong 1", pct=0.05)
    e2, u2 = _sales("me hoa hong 2", pct=0.03)
    e3, _ = _sales("me hoa hong 3", pct=0.05)          # không có đơn nào

    o1 = _don("DH-ME-01", u1, truoc_vat=100_000_000, vat_pct=8)
    _hoa_don(o1, 108_000_000)
    o2 = _don("DH-ME-02", u1, truoc_vat=50_000_000, vat_pct=10)
    _hoa_don(o2, 55_000_000)
    o3 = _don("DH-ME-03", u2, truoc_vat=200_000_000, vat_pct=8, pct=0.03)
    _hoa_don(o3, 216_000_000)
    o4 = _don("DH-ME-04", u2, truoc_vat=10_000_000, vat_pct=8, pct=None)   # đơn không hoa hồng
    _hoa_don(o4, 10_800_000)

    db = SessionLocal()
    try:
        svc = HoaHongService(db)
        theo_me = svc.hoa_hong_ky_map(tu_ngay=KY_TU, den_ngay=KY_DEN)
        for emp_id in (e1, e2, e3):
            assert theo_me.get(emp_id, 0.0) == \
                svc.hoa_hong_ky(emp_id, tu_ngay=KY_TU, den_ngay=KY_DEN), f"NV {emp_id}"
        # neo cứng vài số để test không xanh vì cả hai đường cùng sai
        assert theo_me[e1] == 100_000_000 * 0.05 + 50_000_000 * 0.05
        assert theo_me[e2] == 200_000_000 * 0.03   # % lấy theo ĐƠN, không theo hồ sơ lương
        assert e3 not in theo_me
    finally:
        db.close()


def test_tinh_lai_hai_lan_ra_cung_so(client):
    """Bấm "Tính lại" lần thứ hai KHÔNG được đổi một đồng nào — bẫy kinh điển của việc gom ghi
    (xoá/ghi lại khoản snapshot) là cộng đôi ở lượt sau."""
    token = _admin_token(client)
    com = _khoan(client, token, "Phu cap com lap", 400_000)
    emp_id = _mk_emp(client, token, "Tinh Lai Hai Lan")["id"]
    _gan_khoan(client, token, emp_id, [(com, 400_000)])

    nam, thang = 2026, 8

    def _chup():
        r = client.post("/api/luong/generate", json={"year": nam, "month": thang},
                        headers=_h(token))
        assert r.status_code == 200, r.text
        dong = next((l for l in r.json()["lines"] if l["employee_id"] == emp_id), None)
        assert dong is not None
        return ({k: v for k, v in dong.items() if k not in ("updated_at", "id")},
                sorted((c["code"], c["amount"]) for c in dong.get("components", [])))

    lan1 = _chup()
    lan2 = _chup()
    assert lan1 == lan2
    assert lan1[1] and all(sl == 400_000 for _, sl in lan1[1])   # khoản có, và KHÔNG nhân đôi
