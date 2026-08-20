"""Thực hiện sản xuất — Giai đoạn 3 mặt GHI: BÀN GIAO công đoạn (§11.2 · §11.3).

Soi tầng service `services/san_xuat/ban_giao.py` (nơi chứa LUẬT), không qua HTTP:
  · cùng tổ + cùng LSX → tự `confirmed`; khác tổ/LSX → `proposed` rồi bên NHẬN xác nhận;
  · không giao vượt (tổng tốt − đã giao); sửa số chỉ khi còn `proposed`;
  · xác nhận là quyền tổ ĐÍCH; điều chỉnh đẻ dòng lịch sử, giảm dưới lượng đã dùng ⇒ cờ không nhất quán.

`cung_to`/`lsx_id`/`department_id` là các cột SNAPSHOT của công việc — set thẳng trong test để soi
từng nhánh luật, không phụ thuộc số công đoạn mà fixture routing sinh ra.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.models.department import Department
from app.models.san_xuat import CV_DANG_CHAY
from app.models.san_xuat_ly_do import (
    NHOM_DIEU_CHINH_BAN_GIAO,
    NHOM_TAM_DUNG,
    SanXuatLyDo,
)
from app.models.san_xuat_san_luong import (
    BG_DE_XUAT,
    BG_DIEU_CHINH,
    BG_XAC_NHAN,
    SanXuatBanGiaoDieuChinh,
)
from app.models.user import User
from app.services.san_xuat import ban_giao, san_luong

from tests.test_san_xuat_thuc_thi import (  # noqa: F401
    _cvs,
    _phat_hanh_vao_to,
    _to_khoan,
    admin,
    customer,
    db,
    lsx_svc,
    orders,
)

_T0 = datetime(2026, 8, 19, 8, 0, tzinfo=timezone.utc)


def _ly_do(db, nhom, ma, ten) -> SanXuatLyDo:
    ld = SanXuatLyDo(ma=ma, nhom=nhom, ten=ten)
    db.add(ld)
    db.flush()
    return ld


def _hai_cv(db, orders, lsx_svc, admin, customer, ma="TO-BG"):
    """Hai công việc cùng một tổ khoán, cùng ĐANG CHẠY. Trả (to, cv_nguon, cv_dich, lsx_id)."""
    to = _to_khoan(db, admin, ma=ma)
    a, _b, _goi = _phat_hanh_vao_to(db, orders, lsx_svc, admin, customer, to.id)
    cv1, cv2 = _cvs(db, to)[:2]
    for cv in (cv1, cv2):
        cv.trang_thai = CV_DANG_CHAY
        cv.don_vi_ra = "tờ"
        cv.don_vi_vao = "tờ"
    db.commit()
    return to, cv1, cv2, a.id


def _to_dich(db, ma="TO-BG-DICH") -> tuple[Department, User]:
    u = User(username=f"head_{ma.lower()}", name="Tổ trưởng đích", password_hash="x")
    db.add(u)
    db.flush()
    d = Department(
        name="Tổ Đích", code=ma, la_san_xuat=True, has_piece_work=True, head_user_id=u.id
    )
    db.add(d)
    db.flush()
    return d, u


def _batch(db, admin, cv, *, tot=100, lot_vao=None, t0=_T0):
    return san_luong.tao_batch(
        db, user=admin, cong_viec_id=cv.id,
        bat_dau=t0, ket_thuc=t0 + timedelta(hours=1),
        tong=tot, tot=tot, lot_vao=lot_vao,
    )["batch_id"]


# --- Đề xuất / tự xác nhận (§11.2) ----------------------------------------------------------
def test_de_xuat_khac_to_cho_xac_nhan(db, orders, lsx_svc, admin, customer):
    to, cv1, cv2, _lsx = _hai_cv(db, orders, lsx_svc, admin, customer)
    to_b, ub = _to_dich(db)
    cv2.department_id = to_b.id                          # khác tổ → phải chờ xác nhận
    db.commit()
    _batch(db, admin, cv1, tot=100)

    res = ban_giao.de_xuat(
        db, user=admin, nguon_cong_viec_id=cv1.id, dich_cong_viec_id=cv2.id, so_luong=60
    )
    assert res["trang_thai_ban_giao"] == BG_DE_XUAT
    assert res["so_luong"] == 60
    assert res["notify_user_id"] == ub.id               # đẩy cho tổ trưởng ĐÍCH


def test_cung_to_cung_lsx_tu_xac_nhan(db, orders, lsx_svc, admin, customer):
    to, cv1, cv2, lsx = _hai_cv(db, orders, lsx_svc, admin, customer)
    cv1.lsx_id = cv2.lsx_id = lsx                        # cùng tổ + cùng LSX → tự confirmed
    db.commit()
    _batch(db, admin, cv1, tot=100)

    res = ban_giao.de_xuat(
        db, user=admin, nguon_cong_viec_id=cv1.id, dich_cong_viec_id=cv2.id, so_luong=80
    )
    assert res["trang_thai_ban_giao"] == BG_XAC_NHAN
    assert res["notify_user_id"] is None                # không ai phải đợi


def test_giao_vuot_san_luong_tot_bi_chan(db, orders, lsx_svc, admin, customer):
    to, cv1, cv2, lsx = _hai_cv(db, orders, lsx_svc, admin, customer)
    cv1.lsx_id = cv2.lsx_id = lsx
    db.commit()
    _batch(db, admin, cv1, tot=50)                       # chỉ 50 tốt
    with pytest.raises(ValueError):
        ban_giao.de_xuat(
            db, user=admin, nguon_cong_viec_id=cv1.id, dich_cong_viec_id=cv2.id, so_luong=60
        )


def test_sua_de_xuat_chi_khi_proposed(db, orders, lsx_svc, admin, customer):
    to, cv1, cv2, _lsx = _hai_cv(db, orders, lsx_svc, admin, customer)
    to_b, ub = _to_dich(db)
    cv2.department_id = to_b.id
    db.commit()
    _batch(db, admin, cv1, tot=100)
    r = ban_giao.de_xuat(
        db, user=admin, nguon_cong_viec_id=cv1.id, dich_cong_viec_id=cv2.id, so_luong=60
    )

    r2 = ban_giao.sua_de_xuat(db, user=admin, ban_giao_id=r["ban_giao_id"], so_luong=40)
    assert r2["so_luong"] == 40

    ban_giao.xac_nhan(db, user=ub, ban_giao_id=r["ban_giao_id"])
    with pytest.raises(ValueError):                      # đã xác nhận → không sửa đề xuất nữa
        ban_giao.sua_de_xuat(db, user=admin, ban_giao_id=r["ban_giao_id"], so_luong=30)


def test_xac_nhan_la_quyen_to_dich(db, orders, lsx_svc, admin, customer):
    to, cv1, cv2, _lsx = _hai_cv(db, orders, lsx_svc, admin, customer)
    to_b, ub = _to_dich(db)
    cv2.department_id = to_b.id
    db.commit()
    _batch(db, admin, cv1, tot=100)
    r = ban_giao.de_xuat(
        db, user=admin, nguon_cong_viec_id=cv1.id, dich_cong_viec_id=cv2.id, so_luong=60
    )

    with pytest.raises(PermissionError):                 # tổ NGUỒN không được tự xác nhận
        ban_giao.xac_nhan(db, user=admin, ban_giao_id=r["ban_giao_id"])
    res = ban_giao.xac_nhan(db, user=ub, ban_giao_id=r["ban_giao_id"])
    assert res["trang_thai_ban_giao"] == BG_XAC_NHAN
    assert res["notify_user_id"] == admin.id             # báo ngược tổ nguồn


# --- Điều chỉnh (§11.3) ---------------------------------------------------------------------
def test_dieu_chinh_ghi_lich_su_va_co_khong_nhat_quan(db, orders, lsx_svc, admin, customer):
    to, cv1, cv2, lsx = _hai_cv(db, orders, lsx_svc, admin, customer)
    cv1.lsx_id = cv2.lsx_id = lsx
    db.commit()
    b1 = _batch(db, admin, cv1, tot=100)
    r = ban_giao.de_xuat(
        db, user=admin, nguon_cong_viec_id=cv1.id, dich_cong_viec_id=cv2.id, so_luong=100
    )
    # Công đoạn sau tiêu thụ 80 (lot trỏ về batch của nguồn) → giảm bàn giao xuống dưới 80 = lệch.
    _batch(db, admin, cv2, tot=80, lot_vao=[{"nguon_batch_id": b1, "so_luong": 80}],
           t0=_T0 + timedelta(hours=3))
    dc = _ly_do(db, NHOM_DIEU_CHINH_BAN_GIAO, "DC-1", "Đếm lại thiếu")

    res = ban_giao.dieu_chinh(
        db, user=admin, ban_giao_id=r["ban_giao_id"], so_luong_sau=50, ly_do_id=dc.id
    )
    assert res["trang_thai_ban_giao"] == BG_DIEU_CHINH
    assert res["so_luong"] == 50 and res["khong_nhat_quan"] is True
    ls = db.query(SanXuatBanGiaoDieuChinh).filter_by(ban_giao_id=r["ban_giao_id"]).all()
    assert len(ls) == 1 and float(ls[0].so_luong_truoc) == 100 and float(ls[0].so_luong_sau) == 50

    # Nâng lại trên mức đã dùng → hết lệch.
    res2 = ban_giao.dieu_chinh(
        db, user=admin, ban_giao_id=r["ban_giao_id"], so_luong_sau=90, ly_do_id=dc.id
    )
    assert res2["khong_nhat_quan"] is False


def test_dieu_chinh_bat_buoc_ly_do_dung_nhom(db, orders, lsx_svc, admin, customer):
    to, cv1, cv2, lsx = _hai_cv(db, orders, lsx_svc, admin, customer)
    cv1.lsx_id = cv2.lsx_id = lsx
    db.commit()
    _batch(db, admin, cv1, tot=100)
    r = ban_giao.de_xuat(
        db, user=admin, nguon_cong_viec_id=cv1.id, dich_cong_viec_id=cv2.id, so_luong=100
    )

    with pytest.raises(ValueError):                      # thiếu lý do
        ban_giao.dieu_chinh(db, user=admin, ban_giao_id=r["ban_giao_id"], so_luong_sau=80)
    sai = _ly_do(db, NHOM_TAM_DUNG, "TD-9", "Chờ mực")  # sai nhóm
    with pytest.raises(ValueError):
        ban_giao.dieu_chinh(
            db, user=admin, ban_giao_id=r["ban_giao_id"], so_luong_sau=80, ly_do_id=sai.id
        )
