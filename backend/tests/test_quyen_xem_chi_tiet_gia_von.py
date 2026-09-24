"""Quyền chi tiết `tinh_gia_thanh:view_cost` — gác RUỘT GIÁ của màn Tính giá.

Phiếu tính giá bày trọn cách ra giá vốn: giấy gì, bao nhiêu tờ, đơn giá kg, mỗi công đoạn ăn
bao nhiêu. Nhìn vào là biết nhà máy mua giấy giá nào và còn lãi mấy phần. Ô này tách hai mức:

  · THIẾU `can_view_cost` → vẫn mở được phiếu, vẫn thấy giá vốn tổng + đơn giá bình quân (đủ
    đi chào khách), nhưng KHÔNG thấy phần diễn giải và KHÔNG gọi được các đường bày cấu hình
    sản phẩm / bình bài / preview.
  · CÓ `can_view_cost` → thấy đủ như trước.

Hàng rào phải ở MÁY CHỦ: ẩn nút ở giao diện thì gọi thẳng API vẫn lấy được số.
"""
from __future__ import annotations

from app.db import SessionLocal
from app.models.role import SCOPE_ALL
from app.repositories.rbac_repo import DepartmentRepository, RoleRepository
from app.repositories.user_repo import UserRepository
from app.security import create_access_token, hash_password

MODULE = "tinh_gia_thanh"


def _h(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _user_with_role(username: str, module_key: str, **perm) -> str:
    """Tạo (nếu chưa có) user trong Kinh doanh, gán vai trò riêng chỉ có quyền `perm`
    trên `module_key`, trả về access token."""
    db = SessionLocal()
    try:
        users = UserRepository(db)
        depts = DepartmentRepository(db)
        roles = RoleRepository(db)
        kd = depts.get_by_name("Kinh doanh")
        role_name = f"role-{username}"
        role = roles.get_by_name_and_department(role_name, kd.id)
        if role is None:
            role = roles.create(name=role_name, department_id=kd.id)
        roles.set_permission(role_id=role.id, module_key=module_key, scope=SCOPE_ALL, **perm)
        u = users.get_by_username(username)
        if u is None:
            u = users.create(
                username=username, name=username, password_hash=hash_password("x")
            )
        users.set_assignment(u, department_id=kd.id, role_id=role.id, is_active=True)
        return create_access_token(str(u.id))
    finally:
        db.close()


_BINH_BAI = {
    "kho_in_dai": 650, "kho_in_rong": 450,
    "dai_thanh_pham": 100, "rong_thanh_pham": 80,
}


def test_thieu_view_cost_khong_binh_bai_duoc(client):
    token = _user_with_role("kd_khong_ruot", MODULE, can_read=True)
    r = client.post("/api/tinh-gia/binh-bai", headers=_h(token), json=_BINH_BAI)
    assert r.status_code == 403


def test_thieu_view_cost_khong_tao_duoc_phieu(client):
    token = _user_with_role("kd_khong_ruot_2", MODULE, can_read=True, can_create=True)
    r = client.post("/api/phieu-tinh-gia", headers=_h(token), json={"ten_san_pham": "Thử"})
    assert r.status_code == 403


def test_co_view_cost_thi_binh_bai_duoc(client):
    token = _user_with_role("kd_co_ruot", MODULE, can_read=True, can_view_cost=True)
    r = client.post("/api/tinh-gia/binh-bai", headers=_h(token), json=_BINH_BAI)
    assert r.status_code == 200


def _tao_phieu(client) -> int:
    """Người ĐỦ quyền lập sẵn một phiếu để test người THIẾU quyền mở nó."""
    token = _user_with_role(
        "kd_lap_phieu", MODULE,
        can_read=True, can_create=True, can_update=True, can_view_cost=True,
    )
    r = client.post(
        "/api/phieu-tinh-gia",
        headers=_h(token),
        json={"ten_san_pham": "Hộp giấy thử", "so_luong": 1000},
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


def test_thieu_view_cost_mo_phieu_khong_thay_dien_giai(client):
    p_id = _tao_phieu(client)
    token = _user_with_role("kd_chi_xem", MODULE, can_read=True)
    r = client.get(f"/api/phieu-tinh-gia/{p_id}", headers=_h(token))
    assert r.status_code == 200
    body = r.json()
    # Vẫn thấy phần đi chào khách được
    assert body["ma"]
    assert "tong_gia_von" in body and "gia_von_don" in body
    # Không còn ruột giá
    assert "result" not in body
    assert "warnings" not in body
    assert "danh_muc_doi" not in body
    for tp in body["thanh_phans"]:
        assert "giay_id" not in tp
        assert "don_gia_giay" not in tp
        assert "may_id" not in tp
        assert "gia_von_tp" in tp


def test_co_view_cost_mo_phieu_thay_du(client):
    p_id = _tao_phieu(client)
    token = _user_with_role("kd_xem_du", MODULE, can_read=True, can_view_cost=True)
    r = client.get(f"/api/phieu-tinh-gia/{p_id}", headers=_h(token))
    assert r.status_code == 200
    assert "result" in r.json()
