"""Tương thích đọc lịch sử mẻ từng trỏ tới module Công việc khoán đã gỡ."""
from __future__ import annotations

from datetime import timedelta

from app.models.san_xuat import CV_DANG_CHAY
from app.models.san_xuat_san_luong import SanXuatBatch
from app.services.san_xuat import board, viec_khoan
from tests.san_xuat_me_fixtures import T0, viec_khoan_cua_to
from tests.test_san_xuat_thuc_thi import (  # noqa: F401
    _mot_cv,
    admin,
    customer,
    db,
    lsx_svc,
    orders,
)


def _authz(db):
    from app.repositories.rbac_repo import RoleRepository
    from app.services.rbac_service import AuthorizationService

    return AuthorizationService(RoleRepository(db))


def _legacy_batch(db, orders, lsx_svc, admin, customer):
    to, cv = _mot_cv(db, orders, lsx_svc, admin, customer, ma="TO-LEGACY-KHOAN")
    cv.trang_thai = CV_DANG_CHAY
    cv.don_vi_ra = "tờ"
    rate = viec_khoan_cua_to(db, to.id, ma="VK-LEGACY", ten="Bế hộp cũ", don_gia=120, unit="to")
    db.flush()
    batch = SanXuatBatch(
        cong_viec_id=cv.id, bat_dau=T0, ket_thuc=T0 + timedelta(hours=1),
        tong=100, tot=100, hong=0, don_vi="tờ", created_by=admin.id,
        piece_rate_id=rate.id, khoan_cong_doan_id=None,
        ten_khoan_snapshot="Bế hộp cũ", don_vi_khoan_snapshot="to",
        don_gia_khoan_snapshot=120,
    )
    db.add(batch)
    db.commit()
    return to, cv, rate, batch


def test_drawer_van_doc_duoc_me_legacy(db, orders, lsx_svc, admin, customer):
    _to, cv, rate, batch = _legacy_batch(db, orders, lsx_svc, admin, customer)
    detail = board.chi_tiet_cong_viec(db, admin, _authz(db), cong_viec_id=cv.id)
    row = next(r for r in detail["san_luong"]["batches"] if r["id"] == batch.id)
    assert row["viec_khoan_id"] == rate.id
    assert row["viec_khoan_ten"] == "Bế hộp cũ"
    assert row["viec_khoan_don_gia"] == 120


def test_me_legacy_van_doi_chieu_va_cap_nhat_co_chu_dich(db, orders, lsx_svc, admin, customer):
    to, _cv, rate, batch = _legacy_batch(db, orders, lsx_svc, admin, customer)
    rate.unit_price = 150
    db.commit()
    doi = viec_khoan.danh_muc_doi(db, batch, [], department_id=to.id)
    assert [r["truong"] for r in doi] == ["don_gia"]
    assert float(batch.don_gia_khoan_snapshot) == 120

    viec_khoan.cap_nhat_theo_danh_muc(db, user=admin, batch_id=batch.id)
    db.refresh(batch)
    assert float(batch.don_gia_khoan_snapshot) == 150
