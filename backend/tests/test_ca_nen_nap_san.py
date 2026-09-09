"""Ca nền giải TRONG BỘ NHỚ phải ra CÙNG đáp án với hỏi DB từng ngày (09/09/2026).

`monthly_timesheet` nạp sẵn mốc ca nền cho cả mẻ (`shift_assignments_map`) rồi gieo vào cache
(`gieo_ca_nen`), thay vì để `_shift_for_day` hỏi DB mỗi (người × ngày) — đo được 2 truy vấn cho
MỖI ô, tức 300 người × 26 ngày ≈ 15.600 truy vấn một lần mở bảng công.

Hai đường mà lệch nhau là BẢNG CÔNG lệch, kéo theo LƯƠNG lệch. File này khoá bốn ca dễ sai:
không có mốc nào, ngày trước mốc đầu tiên, đúng ngày mốc, và hai mốc cùng ngày hiệu lực.
"""
from __future__ import annotations

from datetime import date, timedelta

from app.db import SessionLocal
from app.repositories.employee_repo import EmployeeRepository

from .test_work_shifts_api import _admin_token, _h, _mk_emp, _mk_shift, _save_plan


def _dat_moc(client, token, emp_id: int, shift_id: int | None, tu_ngay: str):
    r = client.put(f"/api/employees/{emp_id}/shift",
                   json={"default_shift_id": shift_id, "effective_from": tu_ngay},
                   headers=_h(token))
    assert r.status_code in (200, 201), r.text
    return r.json()


def test_hai_duong_giai_ca_nen_ra_cung_ket_qua(client):
    token = _admin_token(client)
    ca_a = _mk_shift(client, token, "CN-A", "08:00", "17:00")["id"]
    ca_b = _mk_shift(client, token, "CN-B", "06:00", "14:00")["id"]

    # (1) NV chưa từng có mốc nào — rơi về `default_shift_id` (tương thích dữ liệu cũ)
    trong = _mk_emp(client, token, "Ca Nen Trong")["id"]
    # (2) NV có hai mốc: đổi ca giữa chừng
    doi_ca = _mk_emp(client, token, "Ca Nen Doi")["id"]
    _dat_moc(client, token, doi_ca, ca_a, "2026-03-01")
    _dat_moc(client, token, doi_ca, ca_b, "2026-06-15")
    # (3) NV có mốc GỠ ca (shift_id None)
    go_ca = _mk_emp(client, token, "Ca Nen Go")["id"]
    _dat_moc(client, token, go_ca, ca_a, "2026-03-01")
    _dat_moc(client, token, go_ca, None, "2026-07-01")

    db = SessionLocal()
    try:
        repo = EmployeeRepository(db)
        nv = [repo.get_by_id(i) for i in (trong, doi_ca, go_ca)]
        moc_map = repo.shift_assignments_map([e.id for e in nv])
        assert set(moc_map) == {trong, doi_ca, go_ca}

        d = date(2026, 2, 1)
        so_o = 0
        while d <= date(2026, 9, 30):
            for e in nv:
                assert repo.base_shift_id_on(e, d) == \
                    repo.base_shift_id_on(e, d, assignments=moc_map[e.id]), f"{e.code} {d}"
                so_o += 1
            d += timedelta(days=1)
        assert so_o > 600            # quét thật, không phải vòng rỗng

        # Vài mốc neo cứng để test không "xanh vì cả hai đường cùng sai"
        emp_doi = repo.get_by_id(doi_ca)
        mocs = moc_map[doi_ca]
        assert repo.base_shift_id_on(emp_doi, date(2026, 2, 1), assignments=mocs) is None
        assert repo.base_shift_id_on(emp_doi, date(2026, 3, 1), assignments=mocs) == ca_a
        assert repo.base_shift_id_on(emp_doi, date(2026, 6, 14), assignments=mocs) == ca_a
        assert repo.base_shift_id_on(emp_doi, date(2026, 6, 15), assignments=mocs) == ca_b
        assert repo.base_shift_id_on(repo.get_by_id(go_ca), date(2026, 7, 2),
                                     assignments=moc_map[go_ca]) is None
    finally:
        db.close()


def test_nv_du_lieu_cu_chua_co_moc_nao_van_ra_ca_mac_dinh(client):
    """NV chưa từng có mốc (dữ liệu trước khi có bảng mốc) rơi về `default_shift_id` — luật tương
    thích này phải giống nhau ở CẢ hai đường, nếu không cả xưởng cũ mất ca một lượt."""
    token = _admin_token(client)
    ca = _mk_shift(client, token, "CU-A", "08:00", "17:00")["id"]
    emp_id = _mk_emp(client, token, "Ca Nen Du Lieu Cu")["id"]

    db = SessionLocal()
    try:
        repo = EmployeeRepository(db)
        emp = repo.get_by_id(emp_id)
        emp.default_shift_id = ca            # gán thẳng như dữ liệu cũ: KHÔNG có dòng mốc nào
        db.commit()
        assert repo.shift_assignments_map([emp_id])[emp_id] == []
        for d in (date(2020, 1, 1), date(2026, 5, 20), date(2030, 12, 31)):
            trong_bo_nho = repo.base_shift_id_on(emp, d, assignments=[])
            assert repo.base_shift_id_on(emp, d) == trong_bo_nho == ca
    finally:
        db.close()


def test_gieo_ca_nen_khong_de_len_o_luoi_da_khai(client):
    """Ô lưới phân ca (khai tay theo ngày) vẫn THẮNG mốc ca nền sau khi gieo cache."""
    from app.deps import (
        get_attendance_repository,
        get_attendance_service,
        get_audit_repository,
        get_calendar_repository,
        get_calendar_service,
        get_employee_repository,
        get_late_early_repository,
        get_leave_repository,
        get_overtime_repository,
        get_payroll_repository,
    )

    token = _admin_token(client)
    ca_nen = _mk_shift(client, token, "GC-nen", "08:00", "17:00")["id"]
    ca_luoi = _mk_shift(client, token, "GC-luoi", "06:00", "14:00")["id"]
    emp_id = _mk_emp(client, token, "Ca Nen Vs Luoi")["id"]
    _dat_moc(client, token, emp_id, ca_nen, "2026-01-01")
    # Ô lưới chỉ tô được cho ngày CHƯA QUA (máy chủ chặn sửa ca quá khứ) ⇒ dùng tháng sau.
    thang_sau = date.today().replace(day=1) + timedelta(days=32)
    ngay_luoi = thang_sau.replace(day=10)
    _save_plan(client, token,
               [{"employee_id": emp_id, "work_date": ngay_luoi.isoformat(), "shift_id": ca_luoi}],
               year=thang_sau.year, month=thang_sau.month)

    db = SessionLocal()
    try:
        repo = get_employee_repository(db)
        cal = get_calendar_service(get_calendar_repository(db), get_audit_repository(db), db)
        svc = get_attendance_service(
            get_attendance_repository(db), repo, get_audit_repository(db),
            get_leave_repository(db), cal, get_payroll_repository(db),
            get_overtime_repository(db), get_late_early_repository(db),
        )
        emp = repo.get_by_id(emp_id)
        dau = ngay_luoi.replace(day=1)
        cuoi = ngay_luoi.replace(day=28)
        svc.prefetch_shift_days({emp_id}, dau, cuoi)
        svc.gieo_ca_nen(emp, repo.shift_assignments_map([emp_id])[emp_id], dau, cuoi)
        khac = ngay_luoi.replace(day=11)
        # ngày có ô lưới → ca lưới; ngày khác → ca nền
        assert svc._shift_id_cache[(emp_id, ngay_luoi)] == ca_luoi
        assert svc._shift_id_cache[(emp_id, khac)] == ca_nen
        # và trùng khớp với đường hỏi DB
        assert repo.shift_id_on(emp, ngay_luoi) == ca_luoi
        assert repo.shift_id_on(emp, khac) == ca_nen
    finally:
        db.close()
