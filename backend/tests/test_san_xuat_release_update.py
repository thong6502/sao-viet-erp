"""Thực hiện sản xuất §4.3 — PHÁT HÀNH CẬP NHẬT & THU HỒI gói khi lịch đổi sau phát hành.

Soi đúng luật §4.3: chỉ việc CHƯA bắt đầu mới cập nhật được; cập nhật TÁI CHỤP máy + giờ theo lịch
hiện tại, tăng `version_hien_tai`, đẻ `san_xuat_phien_ban(cap_nhat)` kèm LÝ DO, và HUỶ phân công +
hỗ trợ của việc đó (tổ xác nhận lại). Việc ĐÃ bắt đầu giữ nguyên snapshot và CHẶN thu hồi toàn gói.

Tái dùng fixtures + helper của test xếp lịch/release để dựng một gói phát hành thật.
"""
from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from app.models.employee import Employee
from app.models.machine import Machine
from app.models.order import OrderLine
from app.models.san_xuat import (
    GOI_DA_THU_HOI,
    PB_CAP_NHAT,
    SanXuatCongViec,
    SanXuatPhienBan,
)
from app.models.san_xuat_phan_bo import HT_CHO_HAI_BEN, HT_HUY, SanXuatHoTro
from app.models.san_xuat_thuc_thi import (
    PC_DA_RUT,
    PC_HOAT_DONG,
    SanXuatPhanCong,
    SanXuatPhienChay,
)
from app.models.xep_lich import XepLichCongDoan
from app.services.san_xuat import release, release_update

# Fixtures + helper dùng chung từ test xếp lịch.
from tests.test_xep_lich_service import (  # noqa: F401
    _giu_cho_du,
    _hai_lsx_san_sang,
    admin,
    bg_svc,
    customer,
    db,
    lsx_svc,
    orders,
    xl_svc,
)


# --- helpers -----------------------------------------------------------------
def _lsx_da_phat_hanh(db, orders, lsx_svc, xl_svc, admin, customer):
    """Một LSX đã đưa vào lịch + phát hành gói. Trả (lsx, goi)."""
    a, _b = _hai_lsx_san_sang(db, orders, lsx_svc, admin, customer)
    xl_svc.dua_vao_lsx(lsx_id=a.id, actor=admin)
    goi = release.phat_hanh(db, lsx_ids={a.id}, actor=admin)
    db.commit()
    return a, goi


def _cvs(db, goi_id):
    return (
        db.query(SanXuatCongViec)
        .filter_by(goi_id=goi_id)
        .order_by(SanXuatCongViec.id)
        .all()
    )


def _emp(db) -> Employee:
    e = db.query(Employee).first()
    assert e is not None, "seed phải có nhân viên"
    return e


def _mark_started(db, cv) -> None:
    """Đánh dấu một công việc ĐÃ bắt đầu bằng một phiên chạy mở (tín hiệu `bat_dau` đặt §4.3)."""
    db.add(SanXuatPhienChay(
        cong_viec_id=cv.id, so_thu_tu=1,
        bat_dau=datetime(2026, 8, 1, 8, 0, tzinfo=timezone.utc),
    ))
    db.flush()


# --- Đọc thông tin gói (cho UI quyết nút Cập nhật / Thu hồi) ------------------
def test_thong_tin_goi_chua_phat_hanh(db, orders, lsx_svc, admin, customer):
    a, _b = _hai_lsx_san_sang(db, orders, lsx_svc, admin, customer)
    assert release_update.thong_tin_goi(db, nguon="lsx", id=a.id) == {"co_goi": False}


def test_thong_tin_goi_sau_phat_hanh(db, orders, lsx_svc, xl_svc, admin, customer):
    a, goi = _lsx_da_phat_hanh(db, orders, lsx_svc, xl_svc, admin, customer)
    tt = release_update.thong_tin_goi(db, nguon="lsx", id=a.id)

    assert tt["co_goi"] and tt["goi_id"] == goi.id
    assert tt["version_hien_tai"] == 1
    assert tt["so_cong_viec"] > 0
    assert tt["so_da_bat_dau"] == 0
    assert tt["so_chua_bat_dau"] == tt["so_cong_viec"]
    assert tt["cho_phep_cap_nhat"] and tt["cho_phep_thu_hoi"]
    assert len(tt["phien_bans"]) == 1 and tt["phien_bans"][0]["so"] == 1


# --- Cập nhật: tái chụp máy + giờ theo lịch hiện tại, tăng phiên bản ----------
def test_cap_nhat_tai_chup_may_gio_va_tang_phien_ban(db, orders, lsx_svc, xl_svc, admin, customer):
    a, goi = _lsx_da_phat_hanh(db, orders, lsx_svc, xl_svc, admin, customer)
    cvs = _cvs(db, goi.id)
    cd_ids = [cv.lsx_cong_doan_id for cv in cvs if cv.lsx_cong_doan_id]
    sched = db.query(XepLichCongDoan).filter(
        XepLichCongDoan.lsx_cong_doan_id.in_(cd_ids)
    ).first()
    assert sched is not None, "phải có ít nhất một dòng lịch để tái chụp"
    target = next(cv for cv in cvs if cv.lsx_cong_doan_id == sched.lsx_cong_doan_id)

    may = db.query(Machine).first()
    may_id_moi = may.id if may else 4242
    sched.may_id = may_id_moi
    sched.start_at = datetime(2026, 9, 1, 8, 0, tzinfo=timezone.utc)
    sched.finish_at = datetime(2026, 9, 1, 12, 0, tzinfo=timezone.utc)
    db.commit()

    kq = release_update.phat_hanh_cap_nhat(
        db, nguon="lsx", id=a.id, ly_do="Dời lịch do máy bận", actor=admin,
    )
    assert kq["version_hien_tai"] == 2
    assert kq["so_cong_viec_cap_nhat"] == len(cvs)
    assert kq["so_giu_nguyen"] == 0

    db.refresh(target)
    assert target.phien_ban_so == 2
    assert target.may_id == may_id_moi
    assert target.du_kien_bat_dau is not None
    assert (target.du_kien_bat_dau.month, target.du_kien_bat_dau.day,
            target.du_kien_bat_dau.hour) == (9, 1, 8)

    pb2 = db.query(SanXuatPhienBan).filter_by(goi_id=goi.id, so=2).one()
    assert pb2.loai == PB_CAP_NHAT and pb2.ly_do == "Dời lịch do máy bận"
    db.refresh(goi)
    assert goi.version_hien_tai == 2


def test_cap_nhat_huy_phan_cong_va_ho_tro(db, orders, lsx_svc, xl_svc, admin, customer):
    a, goi = _lsx_da_phat_hanh(db, orders, lsx_svc, xl_svc, admin, customer)
    cv = _cvs(db, goi.id)[0]
    emp = _emp(db)
    pc = SanXuatPhanCong(cong_viec_id=cv.id, employee_id=emp.id, trang_thai=PC_HOAT_DONG)
    ht = SanXuatHoTro(
        cong_viec_id=cv.id, employee_id=emp.id, to_goc_id=emp.department_id,
        ngay_lam_viec=date(2026, 9, 1), ty_le_phan_tram=10, trang_thai=HT_CHO_HAI_BEN,
    )
    db.add_all([pc, ht])
    db.commit()

    kq = release_update.phat_hanh_cap_nhat(
        db, nguon="lsx", id=a.id, ly_do="Đổi tổ thực hiện", actor=admin,
    )
    assert kq["so_huy_phan_cong"] >= 1 and kq["so_huy_ho_tro"] >= 1

    db.refresh(pc)
    db.refresh(ht)
    assert pc.trang_thai == PC_DA_RUT and pc.ly_do_rut
    assert ht.trang_thai == HT_HUY


def test_cap_nhat_thieu_ly_do_thi_chan(db, orders, lsx_svc, xl_svc, admin, customer):
    a, _goi = _lsx_da_phat_hanh(db, orders, lsx_svc, xl_svc, admin, customer)
    with pytest.raises(ValueError):
        release_update.phat_hanh_cap_nhat(db, nguon="lsx", id=a.id, ly_do="x", actor=admin)


# --- Việc đã bắt đầu: giữ nguyên + chặn thu hồi toàn gói ----------------------
def test_viec_da_bat_dau_giu_nguyen_va_van_cap_nhat_phan_con_lai(
    db, orders, lsx_svc, xl_svc, admin, customer
):
    # Gói routing seed chỉ 1 công đoạn/LSX → gộp HAI LSX cùng nhóm để có ≥2 công việc.
    a, b = _hai_lsx_san_sang(db, orders, lsx_svc, admin, customer)
    for l in (a, b):
        db.get(OrderLine, l.order_line_id).nhom = "Sách A5"
    db.commit()
    xl_svc.dua_vao_lsx(lsx_id=a.id, actor=admin)
    xl_svc.dua_vao_lsx(lsx_id=b.id, actor=admin)
    goi = release.phat_hanh(db, lsx_ids={a.id, b.id}, actor=admin)
    db.commit()

    cvs = _cvs(db, goi.id)
    assert len(cvs) >= 2, "hai LSX cùng nhóm phải cho ≥2 công việc để tách đã/chưa bắt đầu"
    da_chay = cvs[0]
    _mark_started(db, da_chay)
    db.commit()

    assert release_update.co_cong_viec_da_bat_dau(db, nguon="lsx", id=a.id) is True

    kq = release_update.phat_hanh_cap_nhat(
        db, nguon="lsx", id=a.id, ly_do="Cập nhật phần còn lại", actor=admin,
    )
    assert kq["so_giu_nguyen"] >= 1
    assert kq["so_cong_viec_cap_nhat"] == len(cvs) - kq["so_giu_nguyen"]

    db.refresh(da_chay)
    assert da_chay.phien_ban_so == 1  # việc đã bắt đầu KHÔNG bị tái chụp


def test_het_viec_chua_bat_dau_thi_chan_cap_nhat(db, orders, lsx_svc, xl_svc, admin, customer):
    a, goi = _lsx_da_phat_hanh(db, orders, lsx_svc, xl_svc, admin, customer)
    for cv in _cvs(db, goi.id):
        _mark_started(db, cv)
    db.commit()
    with pytest.raises(ValueError):
        release_update.phat_hanh_cap_nhat(
            db, nguon="lsx", id=a.id, ly_do="Không còn gì để cập nhật", actor=admin,
        )


# --- Thu hồi gói khi chưa việc nào bắt đầu -----------------------------------
def test_thu_hoi_goi_khi_chua_bat_dau(db, orders, lsx_svc, xl_svc, admin, customer):
    a, goi = _lsx_da_phat_hanh(db, orders, lsx_svc, xl_svc, admin, customer)
    cv = _cvs(db, goi.id)[0]
    emp = _emp(db)
    db.add(SanXuatPhanCong(cong_viec_id=cv.id, employee_id=emp.id, trang_thai=PC_HOAT_DONG))
    db.commit()

    n = release_update.thu_hoi_goi(db, nguon="lsx", id=a.id, actor=admin)
    db.commit()
    assert n == len(_cvs(db, goi.id))

    db.refresh(goi)
    assert goi.trang_thai == GOI_DA_THU_HOI
    # Gói đã thu hồi biến khỏi "gói hiện tại" → thông tin gói báo không còn.
    assert release_update.thong_tin_goi(db, nguon="lsx", id=a.id) == {"co_goi": False}

    pc = db.query(SanXuatPhanCong).filter_by(cong_viec_id=cv.id).first()
    assert pc.trang_thai == PC_DA_RUT
