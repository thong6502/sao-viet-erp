"""Màn của THỢ (spec 2026-09-11 §6): thấy lệnh mình làm, trong mẻ chỉ thấy dòng của mình, không tiền.

Phần "thợ thấy gì trong mẻ" soi ở tầng SERVICE (`board.chi_tiet_cong_viec`) vì dàn cảnh cần hai
người cùng một mẻ có chấm công thật — chỉ dựng được bằng helper của `test_san_xuat_phan_bo`. Phần
luỹ kế tháng soi cả service lẫn HTTP (route mới, phải chắc nó không nhận `employee_id` từ client).
"""
from __future__ import annotations

from types import SimpleNamespace

from app.models.role import SCOPE_OWN
from app.models.user import User
from app.services.san_xuat import board, phan_bo
from app.services.san_xuat.san_luong_cua_toi import san_luong_cua_toi

# Fixtures + helper luồng thật.
from tests.test_san_xuat_phan_bo import (  # noqa: F401
    _T0,
    _canh_phan_bo,
    _cham_cong,
    _khoang,
    admin,
    customer,
    db,
    lsx_svc,
    orders,
)
from tests.test_san_xuat_board import _giao
from tests.test_san_xuat_thuc_thi import _emp


class _FakeAuthz:
    """Ép cứng scope để soi nhánh THỢ mà không phụ thuộc tên role seed."""

    def __init__(self, scope: str) -> None:
        self._scope = scope

    def scope_for(self, user, module_key):  # noqa: D401 - stub
        return self._scope


def _authz(db):
    from app.repositories.rbac_repo import RoleRepository
    from app.services.rbac_service import AuthorizationService

    return AuthorizationService(RoleRepository(db))


def _canh_2_nguoi(db, orders, lsx_svc, admin, customer, *, ma):
    """Tổ (admin làm tổ trưởng) + MỘT mẻ + hai người A/B cùng làm, cùng có chấm công hợp lệ.

    A có tài khoản riêng (để đóng vai THỢ mở bàn), B thì không — B chỉ cần tồn tại để chứng minh
    thợ A không nhìn thấy phần của người khác.

    Cả hai đều phải có PHÂN CÔNG còn hiệu lực: thợ chưa được giao việc thì bị chặn ngay ở cửa
    drawer (§7.1), bài sẽ đỏ vì lý do khác hẳn điều nó muốn soi."""
    to, cv, batch = _canh_phan_bo(db, orders, lsx_svc, admin, customer, ma=ma)
    u_a = User(username=f"tho_a_{ma.lower()}", name="Thợ A", password_hash="x")
    db.add(u_a)
    db.flush()
    a = _emp(db, to, f"NV-A-{ma}", ten="Thợ A Tên", user_id=u_a.id)
    b = _emp(db, to, f"NV-B-{ma}", ten="Thợ B Tên")
    _cham_cong(db, a)
    _cham_cong(db, b)
    db.commit()
    _giao(db, cv.id, a.id)
    _giao(db, cv.id, b.id)
    _khoang(db, cv, a, batch.bat_dau, batch.ket_thuc, heso=1.0)
    _khoang(db, cv, b, batch.bat_dau, batch.ket_thuc, heso=1.0)
    db.commit()
    tho = SimpleNamespace(id=u_a.id, department_id=to.id, role_id=admin.role_id)
    return to, cv, batch, tho, a, b


def _ten_moi_dong(d) -> list[str]:
    return [x["ho_ten"] for pb in d["phan_bo"] for x in pb["dong"]] + [
        x["ho_ten"]
        for b in d["san_luong"]["batches"] if b["chia_du_kien"]
        for x in b["chia_du_kien"]["dong"]
    ]


def test_tho_chi_thay_dong_cua_minh_trong_me(db, orders, lsx_svc, admin, customer):
    _to, cv, _batch, tho, a, b = _canh_2_nguoi(
        db, orders, lsx_svc, admin, customer, ma="TO-THO-1")

    d = board.chi_tiet_cong_viec(db, tho, _FakeAuthz(SCOPE_OWN), cong_viec_id=cv.id)
    ten = _ten_moi_dong(d)
    assert ten, "phải có ít nhất một dòng để bài này nói được điều gì"
    assert set(ten) == {a.full_name}
    assert b.full_name not in ten


def test_to_truong_van_thay_ca_to(db, orders, lsx_svc, admin, customer):
    _to, cv, _batch, _tho, a, b = _canh_2_nguoi(
        db, orders, lsx_svc, admin, customer, ma="TO-THO-2")

    d = board.chi_tiet_cong_viec(db, admin, _authz(db), cong_viec_id=cv.id)
    assert {a.full_name, b.full_name} <= set(_ten_moi_dong(d))


def test_luy_ke_thang_cua_toi_chi_tra_cua_chinh_minh(db, orders, lsx_svc, admin, customer):
    _to, cv, batch, tho, a, _b = _canh_2_nguoi(
        db, orders, lsx_svc, admin, customer, ma="TO-THO-3")
    kq = phan_bo.tinh_phan_bo(db, user=admin, batch_id=batch.id)
    phan_bo.chot_phan_bo(db, user=admin, phan_bo_id=kq["phan_bo_id"])
    db.commit()
    cua_a = next(
        float(x.so_luong_tra_luong)
        for x in phan_bo.SanXuatPhanBoRepository(db).cac_dong(kq["phan_bo_id"])
        if x.employee_id == a.id
    )

    d = san_luong_cua_toi(db, tho, nam=_T0.year, thang=_T0.month)
    assert d["employee_id"] == a.id
    assert abs(sum(x["tong"] for x in d["theo_don_vi"]) - cua_a) < 1e-6
    assert d["so_me"] == 1
    assert "tien" not in str(d) and "don_gia" not in str(d)


def test_luy_ke_bo_qua_ban_chia_chua_chot(db, orders, lsx_svc, admin, customer):
    """Bản nháp còn đổi theo chấm công và còn bị tính lại — đưa vào luỹ kế thì mỗi lần mở màn ra
    một số khác."""
    _to, _cv, batch, tho, _a, _b = _canh_2_nguoi(
        db, orders, lsx_svc, admin, customer, ma="TO-THO-4")
    phan_bo.tinh_phan_bo(db, user=admin, batch_id=batch.id)  # chỉ TÍNH, không chốt
    db.commit()

    d = san_luong_cua_toi(db, tho, nam=_T0.year, thang=_T0.month)
    assert d["theo_don_vi"] == [] and d["so_me"] == 0


def test_tai_khoan_chua_noi_ho_so_thi_luy_ke_rong(db, admin):
    u = User(username="chua_noi_ho_so", name="Chưa Nối", password_hash="x")
    db.add(u)
    db.commit()
    d = san_luong_cua_toi(db, u, nam=2026, thang=9)
    assert d == {"nam": 2026, "thang": 9, "employee_id": None, "theo_don_vi": [], "so_me": 0}
