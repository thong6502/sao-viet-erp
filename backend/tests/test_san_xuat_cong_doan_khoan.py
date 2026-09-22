"""Ghi mẻ tự lấy cấu hình Khoán của công đoạn, không cho người dùng chọn danh mục riêng."""
from __future__ import annotations

from datetime import timedelta

import pytest

from app.models.bai_ghep_cong_doan import BaiGhepCongDoan
from app.models.cong_doan import CongDoan, CongDoanKhoan, CongDoanKhoanPhatSinh
from app.models.lsx import LsxCongDoan
from app.models.san_xuat import CV_DANG_CHAY
from app.models.san_xuat_san_luong import SanXuatBatch
from app.services.san_xuat import san_luong, viec_khoan
from tests.san_xuat_me_fixtures import T0
from tests.test_san_xuat_thuc_thi import (  # noqa: F401
    _mot_cv,
    admin,
    customer,
    db,
    lsx_svc,
    orders,
)


def _cv_chay(db, orders, lsx_svc, admin, customer, ma="TO-CD-KHOAN"):
    _to, cv = _mot_cv(db, orders, lsx_svc, admin, customer, ma=ma)
    cv.trang_thai = CV_DANG_CHAY
    cv.don_vi_ra = "tờ"
    cv.don_vi_vao = "tờ"
    db.commit()
    return cv


def _cong_doan(db, cv) -> CongDoan:
    if cv.bai_ghep_cong_doan_id:
        buoc = db.get(BaiGhepCongDoan, cv.bai_ghep_cong_doan_id)
    else:
        buoc = db.get(LsxCongDoan, cv.lsx_cong_doan_id)
    assert buoc is not None and buoc.cong_doan_id is not None
    cd = db.get(CongDoan, buoc.cong_doan_id)
    assert cd is not None
    return cd


def _cau_hinh(db, cv, *, don_gia=25) -> tuple[CongDoanKhoan, CongDoanKhoanPhatSinh]:
    cd = _cong_doan(db, cv)
    k = CongDoanKhoan(cong_doan_id=cd.id, unit="to", unit_price=don_gia)
    k.viec_phat_sinh.append(CongDoanKhoanPhatSinh(
        ten="Thay kẽm", don_gia=100000, don_vi="kem", thu_tu=0,
    ))
    db.add(k)
    db.commit()
    return k, k.viec_phat_sinh[0]


def _ghi(db, admin, cv, **kw):
    kw.setdefault("bat_dau", T0)
    kw.setdefault("ket_thuc", T0 + timedelta(hours=1))
    kw.setdefault("tong", 100)
    kw.setdefault("tot", 100)
    return san_luong.tao_batch(db, user=admin, cong_viec_id=cv.id, **kw)


def test_me_tu_chup_cau_hinh_khoan_cua_cong_doan(db, orders, lsx_svc, admin, customer):
    cv = _cv_chay(db, orders, lsx_svc, admin, customer)
    k, ps = _cau_hinh(db, cv)

    b = db.get(SanXuatBatch, _ghi(
        db, admin, cv, phat_sinh=[{"phat_sinh_id": ps.id, "so_luong": 2}],
    )["batch_id"])

    assert b.piece_rate_id is None
    assert b.khoan_cong_doan_id == k.id
    assert b.ten_khoan_snapshot == _cong_doan(db, cv).ten
    assert b.don_vi_khoan_snapshot == "to"
    assert float(b.don_gia_khoan_snapshot) == 25
    rows = san_luong.SanXuatSanLuongRepository(db).phat_sinh_cua_batch(b.id)
    assert [(r.ten_snapshot, float(r.so_luong), float(r.don_gia_snapshot)) for r in rows] == [
        ("Thay kẽm", 2, 100000),
    ]


def test_cong_doan_chua_cau_hinh_van_ghi_me_binh_thuong(db, orders, lsx_svc, admin, customer):
    cv = _cv_chay(db, orders, lsx_svc, admin, customer)
    b = db.get(SanXuatBatch, _ghi(db, admin, cv)["batch_id"])
    assert b.piece_rate_id is None
    assert b.khoan_cong_doan_id is None
    assert b.ten_khoan_snapshot is None


def test_khong_co_cau_hinh_thi_khong_duoc_ghi_phat_sinh(db, orders, lsx_svc, admin, customer):
    cv = _cv_chay(db, orders, lsx_svc, admin, customer)
    with pytest.raises(ValueError, match="chưa cấu hình Khoán"):
        _ghi(db, admin, cv, phat_sinh=[{"phat_sinh_id": 1, "so_luong": 1}])


def test_phat_sinh_phai_thuoc_cau_hinh_va_so_luong_duong(db, orders, lsx_svc, admin, customer):
    cv = _cv_chay(db, orders, lsx_svc, admin, customer)
    _k, ps = _cau_hinh(db, cv)
    cases = [
        ([{"phat_sinh_id": ps.id + 999, "so_luong": 1}], "không thuộc cấu hình Khoán"),
        ([{"phat_sinh_id": ps.id, "so_luong": 0}], "phải lớn hơn 0"),
        ([{"phat_sinh_id": ps.id, "so_luong": "abc"}], "không hợp lệ"),
        ([{"phat_sinh_id": ps.id, "so_luong": 1}, {"phat_sinh_id": ps.id, "so_luong": 2}],
         "bị chọn hai lần"),
    ]
    for rows, message in cases:
        with pytest.raises(ValueError, match=message):
            _ghi(db, admin, cv, phat_sinh=rows)
        db.rollback()


def test_snapshot_chi_doi_khi_nguoi_bam_cap_nhat(db, orders, lsx_svc, admin, customer):
    cv = _cv_chay(db, orders, lsx_svc, admin, customer)
    k, ps = _cau_hinh(db, cv, don_gia=25)
    bid = _ghi(db, admin, cv, phat_sinh=[{"phat_sinh_id": ps.id, "so_luong": 1}])["batch_id"]
    b = db.get(SanXuatBatch, bid)

    k.unit_price = 30
    ps.ten = "Thay kẽm mới"
    db.commit()
    rows = san_luong.SanXuatSanLuongRepository(db).phat_sinh_cua_batch(bid)
    doi = viec_khoan.danh_muc_doi(db, b, rows, department_id=cv.department_id)
    assert sorted(o["truong"] for o in doi) == ["don_gia", "ten"]
    assert float(b.don_gia_khoan_snapshot) == 25

    viec_khoan.cap_nhat_theo_danh_muc(db, user=admin, batch_id=bid)
    db.refresh(b)
    assert float(b.don_gia_khoan_snapshot) == 30
    rows = san_luong.SanXuatSanLuongRepository(db).phat_sinh_cua_batch(bid)
    assert rows[0].ten_snapshot == "Thay kẽm mới"
    assert viec_khoan.danh_muc_doi(db, b, rows, department_id=cv.department_id) == []
