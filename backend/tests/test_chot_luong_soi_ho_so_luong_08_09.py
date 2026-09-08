"""L15 — chốt lương phải soi HỒ SƠ LƯƠNG / THAM SỐ đổi SAU lần Tính lại cuối (bản rà liên thông E5,
08/09/2026). Cùng khuôn với L12 (tạm ứng): HCNS sửa mức lương rồi bấm Chốt ngay là khoá số cũ.
Kèm E12/C9: khai mốc lương, đổi tham số, sửa bậc thuế/bậc phạt phải có nhật ký.
"""
from __future__ import annotations

from tests.test_chan_ghi_khi_ky_cong_da_chot import _chot_cong
from tests.test_ra_soat_nhan_su_luong_07_09 import (
    NAM, _bam_du_thang, _gen, _h, _khai_luong, _line, _nv,
)

THANG = 8   # ≥ mốc AP_DUNG_CHOT_CONG_TRUOC_TU để đi trọn chuỗi chốt công → chốt lương


def _san_sang(client, h) -> int:
    e = _nv(client, h, "L15", "Kinh doanh")
    _khai_luong(client, h, e)
    _bam_du_thang(client, h, e, thang=THANG, den=31)
    _chot_cong(client, h, nam=NAM, thang=THANG)
    _gen(client, h, month=THANG)
    return e


def _lock(client, h):
    return client.post("/api/luong/lock", json={"year": NAM, "month": THANG}, headers=h)


def test_doi_muc_luong_sau_tinh_lai_thi_chua_chot_duoc(client):
    h = _h(client)
    e = _san_sang(client, h)
    assert _line(_gen(client, h, month=THANG), e)["monthly_salary"] == 10_400_000
    # Khai mốc mới hiệu lực trong kỳ SAU lần Tính lại → chặn; Tính lại → dòng theo số mới → chốt được.
    _khai_luong(client, h, e, effective_from=f"{NAM}-08-01", luong_vi_tri=15_600_000)
    r = _lock(client, h)
    assert r.status_code == 400 and "SAU lần" in r.json()["detail"] and "mức lương" in r.json()["detail"], r.text
    assert _line(_gen(client, h, month=THANG), e)["monthly_salary"] == 15_600_000
    assert _lock(client, h).status_code == 200


def test_doi_tham_so_sau_tinh_lai_thi_chua_chot_duoc(client):
    h = _h(client)
    _san_sang(client, h)
    r = client.put("/api/luong/params", json={"bhxh_rate": 0.085}, headers=h)
    assert r.status_code == 200, r.text
    r = _lock(client, h)
    assert r.status_code == 400 and "tham số" in r.json()["detail"], r.text
    _gen(client, h, month=THANG)
    assert _lock(client, h).status_code == 200
    # Nhật ký có vết đổi tham số + khai mốc lương (E12/C9).
    from app.db import SessionLocal
    from app.repositories.audit_repo import AuditLogRepository
    db = SessionLocal()
    try:
        assert AuditLogRepository(db).list_by_action("payroll_update_params")
        assert AuditLogRepository(db).list_by_action("payroll_set_salary")
    finally:
        db.close()


def test_moc_luong_hieu_luc_ky_sau_khong_chan(client):
    h = _h(client)
    e = _san_sang(client, h)
    _khai_luong(client, h, e, effective_from=f"{NAM}-09-01", luong_vi_tri=20_000_000)
    assert _lock(client, h).status_code == 200


def test_sua_bac_phat_sau_tinh_lai_thi_chua_chot_duoc(client):
    h = _h(client)
    _san_sang(client, h)
    r = client.post("/api/luong/late-penalty-brackets", json={"seq": 9, "up_to_minute": 5, "amount": 1_000}, headers=h)
    assert r.status_code in (200, 201), r.text
    r = _lock(client, h)
    assert r.status_code == 400 and "bảng phạt" in r.json()["detail"], r.text
    _gen(client, h, month=THANG)
    assert _lock(client, h).status_code == 200
