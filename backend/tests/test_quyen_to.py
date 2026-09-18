"""Dòng quyền THEO TỔ (mg 0302, bản chốt 14/09/2026).

Soi `services/quyen_to.py` trên cây giống ví dụ trong spec:

    Sản xuất (la_san_xuat)
    ├── Tổ in
    │   └── Nhóm in máy 2 màu
    │       └── Ca đêm 2 màu
    └── Tổ cắt

  · dòng quyền tự sinh / đổi nhãn / gỡ theo cây;
  · phạm vi tính từ VỊ TRÍ NGƯỜI XEM trong VÙNG của dòng (bảng ví dụ §2 của spec);
  · người nhận thông báo cấp tổ;
  · migration chép quyền `san_xuat` cũ sang dòng tổ.
"""
from __future__ import annotations

import pytest
from sqlalchemy import text

from app.db_migrations import chuyen_quyen_san_xuat_sang_to
from app.models.department import Department
from app.models.module import Module
from app.models.role import SCOPE_ALL, SCOPE_DEPARTMENT, SCOPE_OWN, Role, RolePermission
from app.models.user import User
from app.repositories.rbac_repo import RoleRepository
from app.services.quyen_to import (
    MUC_CUA_TOI,
    MUC_TAT_CA,
    dong_bo_dong_quyen_to,
    khoa_to,
    nguoi_co_quyen,
    quyen_to_cua,
)
from tests.conftest import phien_da_seed
from tests.quyen_to_fixtures import cap_quyen_to


@pytest.fixture
def db():
    yield from phien_da_seed()


def _phong(db, ten, cha=None, *, sx=False):
    d = Department(name=ten, code=ten[:12].upper().replace(" ", ""), parent_id=cha.id if cha else None,
                   la_san_xuat=sx)
    db.add(d)
    db.flush()
    return d


def _nguoi(db, ten, phong):
    u = User(username=ten, name=ten, password_hash="x", department_id=phong.id, is_active=True)
    db.add(u)
    db.flush()
    return u


@pytest.fixture
def cay(db):
    sx = _phong(db, "SX Test", sx=True)
    to_in = _phong(db, "Tổ in T", sx)
    nhom2 = _phong(db, "Nhóm 2 màu T", to_in)
    ca_dem = _phong(db, "Ca đêm 2 màu T", nhom2)
    to_cat = _phong(db, "Tổ cắt T", sx)
    dong_bo_dong_quyen_to(db)
    return {"sx": sx, "in": to_in, "nhom2": nhom2, "dem": ca_dem, "cat": to_cat}


def test_dong_quyen_sinh_doi_nhan_va_go_theo_cay(db, cay):
    keys = {m.key: m.label for m in db.query(Module).filter(Module.key.like("to_sx_%"))}
    for d in cay.values():
        assert keys[khoa_to(d.id)] == d.name

    cay["nhom2"].name = "Nhóm in máy 2 màu T"
    db.flush()
    dong_bo_dong_quyen_to(db)
    assert db.get(Module, db.query(Module.id).filter(Module.key == khoa_to(cay["nhom2"].id)).scalar()).label \
        == "Nhóm in máy 2 màu T"

    # Tổ cắt rời khối (chuyển sang phòng ngoài khối) ⇒ dòng + ô đã cấp đi theo.
    ngoai = _phong(db, "Văn phòng T")
    u = _nguoi(db, "u_cat", cay["cat"])
    cap_quyen_to(db, u, cay["cat"], scope=SCOPE_ALL)
    cay["cat"].parent_id = ngoai.id
    db.flush()
    dong_bo_dong_quyen_to(db)
    assert db.query(Module).filter(Module.key == khoa_to(cay["cat"].id)).count() == 0
    assert db.query(RolePermission).filter(RolePermission.module_key == khoa_to(cay["cat"].id)).count() == 0


@pytest.mark.parametrize(
    "scope, noi_ngoi, thay_tron",
    [
        # A thuộc Nhóm 2 màu (nấc giữa) · dòng "Tổ in"
        (SCOPE_OWN, "nhom2", set()),
        (SCOPE_DEPARTMENT, "nhom2", {"nhom2", "dem"}),
        (SCOPE_ALL, "nhom2", {"in", "nhom2", "dem"}),
        # B thuộc Tổ in
        (SCOPE_DEPARTMENT, "in", {"in", "nhom2", "dem"}),
        (SCOPE_ALL, "in", {"in", "nhom2", "dem"}),
        # C thuộc phòng CHA (Sản xuất) — đứng trên nút của dòng: Cả phòng = cả vùng
        (SCOPE_DEPARTMENT, "sx", {"in", "nhom2", "dem"}),
        # Người Tổ cắt cấp dòng Tổ in: Cả phòng ⇒ không thấy gì; Tất cả ⇒ cả Tổ in
        (SCOPE_DEPARTMENT, "cat", set()),
        (SCOPE_ALL, "cat", {"in", "nhom2", "dem"}),
    ],
)
def test_pham_vi_tinh_tu_vi_tri_nguoi_xem(db, cay, scope, noi_ngoi, thay_tron):
    u = _nguoi(db, f"u_{scope}_{noi_ngoi}", cay[noi_ngoi])
    cap_quyen_to(db, u, cay["in"], scope=scope, viec=("run_order",))
    q = quyen_to_cua(db, u)
    tron = {k for k, d in cay.items() if q.muc("read", d.id) == MUC_TAT_CA}
    assert tron == thay_tron
    # Phạm vi áp cho cả quyền chi tiết; quyền không bật thì không có ở đâu.
    assert {k for k, d in cay.items() if q.muc("run_order", d.id) == MUC_TAT_CA} == thay_tron
    assert all(q.muc("warehouse", d.id) is None for d in cay.values())
    # Ngoài vùng của dòng thì không bao giờ có gì.
    assert q.muc("read", cay["sx"].id) is None
    assert q.muc("read", cay["cat"].id) is None


def test_cua_toi_chi_mo_ban_cua_minh_va_chong_dong_lay_rong_nhat(db, cay):
    u = _nguoi(db, "tho_dem", cay["dem"])
    cap_quyen_to(db, u, cay["in"], scope=SCOPE_OWN, viec=())
    q = quyen_to_cua(db, u)
    assert q.muc("read", cay["nhom2"].id) == MUC_CUA_TOI
    assert [(d, m) for d, _, m in q.ban_thay_duoc()] == [(cay["dem"].id, MUC_CUA_TOI)]

    # Thêm dòng Nhóm 2 màu · Tất cả ⇒ phần đó rộng ra, phần còn lại của Tổ in vẫn "của tôi".
    cap_quyen_to(db, u, cay["nhom2"], scope=SCOPE_ALL, viec=())
    q = quyen_to_cua(db, u)
    assert q.muc("read", cay["nhom2"].id) == MUC_TAT_CA
    assert q.muc("read", cay["dem"].id) == MUC_TAT_CA
    assert q.muc("read", cay["in"].id) == MUC_CUA_TOI
    ban = [(d, m) for d, _, m in q.ban_thay_duoc()]
    assert (cay["nhom2"].id, MUC_TAT_CA) in ban and (cay["dem"].id, MUC_TAT_CA) in ban


def test_nguoi_nhan_thong_bao_cap_to(db, cay):
    truong_in = _nguoi(db, "truong_in", cay["in"])
    cap_quyen_to(db, truong_in, cay["in"], scope=SCOPE_DEPARTMENT, viec=("confirm_output",))
    truong_nhom = _nguoi(db, "truong_nhom", cay["nhom2"])
    cap_quyen_to(db, truong_nhom, cay["in"], scope=SCOPE_DEPARTMENT, viec=("confirm_output",))
    tho = _nguoi(db, "tho_in", cay["in"])
    cap_quyen_to(db, tho, cay["in"], scope=SCOPE_OWN, viec=("confirm_output",))
    quan_ly = _nguoi(db, "ql_cat", cay["cat"])
    cap_quyen_to(db, quan_ly, cay["sx"], scope=SCOPE_ALL, viec=("confirm_output",))

    assert set(nguoi_co_quyen(db, cay["dem"].id, "confirm_output")) == {
        truong_in.id, truong_nhom.id, quan_ly.id}
    assert set(nguoi_co_quyen(db, cay["in"].id, "confirm_output")) == {truong_in.id, quan_ly.id}
    assert nguoi_co_quyen(db, cay["in"].id, "warehouse") == []


def test_migration_chep_quyen_san_xuat_cu_sang_dong_to(db, cay):
    roles = RoleRepository(db)
    truong = Role(name="TT cũ", department_id=cay["in"].id)
    tho = Role(name="Thợ cũ", department_id=cay["in"].id)
    tho_khong_xem = Role(name="Thợ không xem", department_id=cay["in"].id)
    ke_hoach = Role(name="KH cũ", department_id=cay["sx"].id)
    db.add_all([truong, tho, tho_khong_xem, ke_hoach])
    db.flush()
    roles.set_permission(role_id=truong.id, module_key="san_xuat", can_read=True, scope=SCOPE_OWN,
                         can_assign_work=True, commit=False)
    roles.set_permission(role_id=tho.id, module_key="san_xuat", can_read=True, scope=SCOPE_OWN,
                         commit=False)
    roles.set_permission(role_id=tho_khong_xem.id, module_key="san_xuat", scope=SCOPE_OWN,
                         commit=False)
    roles.set_permission(role_id=ke_hoach.id, module_key="san_xuat", can_read=True, scope=SCOPE_ALL,
                         commit=False)
    db.commit()

    chuyen_quyen_san_xuat_sang_to(db)
    chuyen_quyen_san_xuat_sang_to(db)  # chạy lại không nhân đôi

    def dong(role, dept):
        return roles.get_permission(role.id, khoa_to(dept.id))

    p = dong(truong, cay["in"])
    assert (p.can_read, p.scope, p.can_run_order, p.can_confirm_output, p.can_warehouse) \
        == (True, SCOPE_DEPARTMENT, True, True, True)
    p = dong(tho, cay["in"])
    assert (p.can_read, p.scope, p.can_run_order) == (True, SCOPE_OWN, False)
    assert dong(tho_khong_xem, cay["in"]) is None
    p = dong(ke_hoach, cay["sx"])
    assert (p.can_read, p.scope, p.can_run_order) == (True, SCOPE_ALL, False)
    assert db.execute(text(
        "SELECT COUNT(*) FROM role_permissions WHERE role_id = :r AND module_key LIKE 'to_sx_%'"),
        {"r": truong.id}).scalar() == 1
