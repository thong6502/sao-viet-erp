"""Danh mục THAM CHIẾU đọc-được-để-Tính-giá (require_any_permission).

Màn Tính giá cần đổ dropdown Loại SP · Giấy · Máy · Công đoạn. Bốn danh mục này
mặc định gate bằng module cấu hình riêng (dm_loai_san_pham / kho / dm_thiet_bi /
dm_cong_doan) — thứ MỞ menu cấu hình. Ai làm Tính giá (tinh_gia_thanh:read) phải
ĐỌC được danh mục mà KHÔNG cần quyền cấu hình (không lộ menu). Ghi vẫn cần quyền module.
"""
from __future__ import annotations

from app.db import SessionLocal
from app.repositories.rbac_repo import DepartmentRepository, RoleRepository
from app.repositories.user_repo import UserRepository
from app.security import create_access_token, hash_password

# 4 endpoint LIST mà dropdown Tính giá gọi.
LIST_ENDPOINTS = [
    "/api/loai-san-pham",
    "/api/may-thiet-bi",
    "/api/cong-doan",
    "/api/vat-lieu-kho/giay",
]


def _h(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _token_for_role(username: str, perms: list[tuple[str, str]]) -> str:
    """Mint a user whose brand-new role grants exactly `perms` (module, scope)."""
    db = SessionLocal()
    try:
        users = UserRepository(db)
        existing = users.get_by_username(username)
        if existing is not None:
            return create_access_token(str(existing.id))
        kd = DepartmentRepository(db).get_by_name("Kinh doanh")
        roles = RoleRepository(db)
        role = roles.create(name=f"R-{username}", department_id=kd.id)
        for module_key, scope in perms:
            roles.set_permission(
                role_id=role.id, module_key=module_key, can_read=True, scope=scope
            )
        u = users.create(username=username, name="U", password_hash=hash_password("x"))
        users.set_assignment(u, department_id=kd.id, role_id=role.id, is_active=True)
        return create_access_token(str(u.id))
    finally:
        db.close()


def test_costing_reader_can_list_all_reference_catalogs(client):
    """tinh_gia_thanh:read (không có quyền cấu hình nào) → ĐỌC được cả 4 danh mục."""
    token = _token_for_role("costing-only", [("tinh_gia_thanh", "all")])
    for ep in LIST_ENDPOINTS:
        resp = client.get(ep, headers=_h(token))
        assert resp.status_code == 200, f"{ep} -> {resp.status_code} (mong 200)"
        assert "items" in resp.json()


def test_no_permission_still_forbidden_on_reference_catalogs(client):
    """Không quyền cấu hình LẪN tính giá → 403 (OR-gate không mở cho người lạ)."""
    token = _token_for_role("nobody", [("dashboard", "own")])
    for ep in LIST_ENDPOINTS:
        assert client.get(ep, headers=_h(token)).status_code == 403, ep


def test_costing_reader_cannot_create_catalog(client):
    """OR-gate chỉ nới READ; GHI vẫn đòi quyền cấu hình module (dm_loai_san_pham:create)."""
    token = _token_for_role("costing-only", [("tinh_gia_thanh", "all")])
    resp = client.post(
        "/api/loai-san-pham",
        json={"ma": "X-CT", "ten": "x", "structural_type": "flat"},
        headers=_h(token),
    )
    assert resp.status_code == 403
