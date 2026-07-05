"""Quyền CHI TIẾT (Cách B) cho các module ngoài Khách hàng — chặn thật ở backend.

Chứng minh 3 quyền mới tách khỏi CRUD:
  - bao_gia `approve`      : duyệt báo giá (→ accepted) tách khỏi `update`.
  - don_hang_ban `manage_status`: chốt/hủy đơn tách khỏi `update`.
  - nguoi_dung `reset_password` : đặt lại mật khẩu tách khỏi `update`.
Mỗi test dựng một vai trò CÓ `update` nhưng THIẾU quyền chi tiết → thao tác phải 403.
"""
from __future__ import annotations

from app.db import SessionLocal
from app.models.role import SCOPE_ALL
from app.repositories.rbac_repo import DepartmentRepository, RoleRepository
from app.repositories.user_repo import UserRepository
from app.security import create_access_token, hash_password


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


def test_quotation_approve_requires_approve_permission(client):
    # Vai trò CÓ update báo giá nhưng KHÔNG có `approve` → duyệt (accepted) bị 403.
    # Chốt approve nằm TRƯỚC lookup nên không cần báo giá thật để chứng minh gate.
    token = _user_with_role("fp-quote", "bao_gia", can_read=True, can_update=True)
    r = client.post(
        "/api/quotations/1/transition", json={"to_status": "accepted"}, headers=_h(token)
    )
    assert r.status_code == 403, r.text


def test_order_chot_requires_approve(client):
    # CÓ update + manage_status nhưng KHÔNG `approve` → CHỐT đơn (ordered) bị 403.
    token = _user_with_role(
        "fp-chot", "don_hang_ban", can_read=True, can_update=True, can_manage_status=True
    )
    r = client.post(
        "/api/orders/1/transition", json={"to_status": "ordered"}, headers=_h(token)
    )
    assert r.status_code == 403, r.text


def test_order_huy_requires_cancel(client):
    # CÓ update + manage_status nhưng KHÔNG `cancel` → HỦY đơn (cancelled) bị 403.
    token = _user_with_role(
        "fp-huy", "don_hang_ban", can_read=True, can_update=True, can_manage_status=True
    )
    r = client.post(
        "/api/orders/1/transition",
        json={"to_status": "cancelled", "cancel_reason": "x"},
        headers=_h(token),
    )
    assert r.status_code == 403, r.text


def test_order_other_transition_requires_manage_status(client):
    # CÓ update nhưng KHÔNG `manage_status` → đổi trạng thái khác (on_hold) bị 403.
    token = _user_with_role("fp-order", "don_hang_ban", can_read=True, can_update=True)
    r = client.post(
        "/api/orders/1/transition", json={"to_status": "on_hold"}, headers=_h(token)
    )
    assert r.status_code == 403, r.text


def test_reset_password_requires_reset_permission_not_update(client):
    # Vai trò CÓ update người dùng nhưng KHÔNG có `reset_password` → đặt lại MK bị 403,
    # chứng minh reset_password đã tách khỏi update.
    token = _user_with_role("fp-hr", "nguoi_dung", can_read=True, can_update=True)
    r = client.post("/api/users/1/reset-password", headers=_h(token))
    assert r.status_code == 403, r.text


# --- Nhóm 1: các quyền chi tiết đặc thù tách khỏi CRUD ------------------------


def _mk_plain_user(username: str, dept_name: str = "Kinh doanh") -> tuple[int, int]:
    """Tạo user thường (không vai trò) trong phòng; trả (user_id, department_id)."""
    db = SessionLocal()
    try:
        users = UserRepository(db)
        dept = DepartmentRepository(db).get_by_name(dept_name)
        u = users.get_by_username(username)
        if u is None:
            u = users.create(
                username=username, name=username, password_hash=hash_password("x")
            )
        users.set_assignment(u, department_id=dept.id, role_id=None, is_active=True)
        return u.id, dept.id
    finally:
        db.close()


def _dept_id(name: str) -> int:
    db = SessionLocal()
    try:
        return DepartmentRepository(db).get_by_name(name).id
    finally:
        db.close()


def test_lock_requires_lock_permission(client):
    token = _user_with_role("fp-lock", "nguoi_dung", can_read=True, can_update=True)
    r = client.put("/api/users/1/active", json={"is_active": False}, headers=_h(token))
    assert r.status_code == 403, r.text


def test_revoke_sessions_requires_permission(client):
    token = _user_with_role("fp-revoke", "nguoi_dung", can_read=True, can_update=True)
    r = client.post("/api/users/1/revoke-sessions", headers=_h(token))
    assert r.status_code == 403, r.text


def test_assign_role_requires_assign_permission(client):
    token = _user_with_role("fp-assign", "nguoi_dung", can_read=True, can_update=True)
    r = client.put("/api/users/1/role", json={"role_id": 1}, headers=_h(token))
    assert r.status_code == 403, r.text


def test_requote_requires_requote_permission(client):
    # CÓ quyền Thêm báo giá nhưng KHÔNG có `requote` → tạo bản mới bị 403.
    token = _user_with_role("fp-requote", "bao_gia", can_read=True, can_create=True)
    r = client.post("/api/quotations/1/requote", headers=_h(token))
    assert r.status_code == 403, r.text


def test_manage_status_requires_permission_bao_gia(client):
    # CÓ read+update báo giá nhưng KHÔNG `manage_status` → gửi/từ chối/hết hạn bị 403.
    token = _user_with_role("fp-qstatus", "bao_gia", can_read=True, can_update=True)
    r = client.post(
        "/api/quotations/1/transition", json={"to_status": "sent"}, headers=_h(token)
    )
    assert r.status_code == 403, r.text


def test_cancel_quotation_requires_cancel_permission(client):
    # CÓ quyền Sửa báo giá nhưng KHÔNG có `cancel` → hủy (→ cancelled) bị 403.
    # Chốt cancel nằm TRƯỚC lookup nên không cần báo giá thật để chứng minh gate.
    token = _user_with_role("fp-cancel", "bao_gia", can_read=True, can_update=True)
    r = client.post(
        "/api/quotations/1/transition",
        json={"to_status": "cancelled", "cancel_reason": "x"},
        headers=_h(token),
    )
    assert r.status_code == 403, r.text


def test_manage_price_requires_permission(client):
    # CÓ quyền Sửa vật liệu nhưng KHÔNG có `manage_price` → thêm giá theo mốc bị 403.
    token = _user_with_role("fp-price", "dm_giay_vat_tu", can_read=True, can_update=True)
    r = client.post(
        "/api/materials/1/costs",
        json={"price_unit": "ram", "unit_price": 1000, "effective_from": "2026-01-01"},
        headers=_h(token),
    )
    assert r.status_code == 403, r.text


def test_transfer_department_via_edit_requires_transfer(client):
    # Đổi TÊN trong cùng phòng chỉ cần `update`; ĐỔI PHÒNG cần `transfer`.
    token = _user_with_role("fp-tf", "nguoi_dung", can_read=True, can_update=True)
    uid, kd_id = _mk_plain_user("fp-target")
    other = _dept_id("Hành chính nhân sự")
    ok = client.put(
        f"/api/users/{uid}", json={"name": "Đổi tên", "department_id": kd_id}, headers=_h(token)
    )
    assert ok.status_code == 200, ok.text
    r = client.put(
        f"/api/users/{uid}", json={"name": "Đổi tên", "department_id": other}, headers=_h(token)
    )
    assert r.status_code == 403, r.text


def test_set_head_requires_permission(client):
    # CÓ quyền Sửa phòng ban nhưng KHÔNG có `set_head` → đổi trưởng phòng bị 403.
    token = _user_with_role("fp-head", "phong_ban", can_read=True, can_update=True)
    uid, kd_id = _mk_plain_user("fp-headtarget")
    r = client.put(
        f"/api/departments/{kd_id}",
        json={"name": "Kinh doanh", "head_user_id": uid, "description": None, "level_id": None},
        headers=_h(token),
    )
    assert r.status_code == 403, r.text


# --- Nhóm B --------------------------------------------------------------------


def test_manage_permissions_requires_permission(client):
    # CÓ vai_tro update (đổi tên) nhưng KHÔNG `manage_permissions` → sửa ma trận bị 403.
    token = _user_with_role("fp-perm", "vai_tro", can_read=True, can_update=True)
    r = client.put(
        "/api/roles/1/permissions", json={"permissions": []}, headers=_h(token)
    )
    assert r.status_code == 403, r.text


def test_clone_material_requires_clone_permission(client):
    # CÓ Thêm vật liệu nhưng KHÔNG `clone` → nhân bản bị 403.
    token = _user_with_role("fp-clone", "dm_giay_vat_tu", can_read=True, can_create=True)
    r = client.post(
        "/api/materials/1/clone",
        json={"gsm": 200, "width_cm": 65, "height_cm": 86},
        headers=_h(token),
    )
    assert r.status_code == 403, r.text


def test_toggle_active_material_requires_permission(client):
    # CÓ Sửa vật liệu nhưng KHÔNG `toggle_active` → bật/tắt bị 403.
    token = _user_with_role("fp-toggle", "dm_giay_vat_tu", can_read=True, can_update=True)
    r = client.patch("/api/materials/1/toggle-active", headers=_h(token))
    assert r.status_code == 403, r.text


def test_customer_edit_cannot_change_sale_without_reassign(client):
    # CÓ Sửa KH nhưng KHÔNG `reassign` → đổi NV phụ trách QUA NÚT SỬA bị 403
    # (bịt đường vòng: endpoint reassign riêng đã chặn nhưng PUT chung thì chưa).
    token = _user_with_role(
        "fp-khsale", "khach_hang", can_read=True, can_create=True, can_update=True
    )
    other_id, _ = _mk_plain_user("fp-khsale-target")
    r = client.post("/api/customers", json={"name": "KH fp-sale"}, headers=_h(token))
    assert r.status_code == 201, r.text
    cid = r.json()["customer"]["id"]
    base = {
        "name": "KH fp-sale đổi tên",
        "tax_code": None,
        "phone": None,
        "email": None,
        "address": None,
        "contact_name": None,
        "credit_limit": 0,
        "status": "active",
    }
    # Sửa thông tin thường (sale giữ nguyên qua None-fallback) vẫn OK.
    ok = client.put(
        f"/api/customers/{cid}", json={**base, "sale_user_id": None}, headers=_h(token)
    )
    assert ok.status_code == 200, ok.text
    # Đổi người phụ trách → 403.
    r = client.put(
        f"/api/customers/{cid}", json={**base, "sale_user_id": other_id}, headers=_h(token)
    )
    assert r.status_code == 403, r.text


def test_material_edit_cannot_flip_active_without_toggle(client):
    # CÓ Sửa vật tư nhưng KHÔNG `toggle_active` → đổi is_active QUA NÚT SỬA bị 403
    # (các field khác vẫn sửa bình thường).
    token = _user_with_role(
        "fp-matact", "dm_giay_vat_tu", can_read=True, can_create=True, can_update=True
    )
    payload = {
        "name": "VT fp-active",
        "material_type": "chemical",
        "unit": "kg",
        "min_fee": 0,
        "default_waste_pct": 0,
        "min_purchase_qty": 0,
        "is_active": True,
    }
    r = client.post("/api/materials", json=payload, headers=_h(token))
    assert r.status_code == 201, r.text
    mid = r.json()["id"]
    ok = client.put(
        f"/api/materials/{mid}", json={**payload, "name": "VT fp-active sửa"}, headers=_h(token)
    )
    assert ok.status_code == 200, ok.text
    r = client.put(
        f"/api/materials/{mid}",
        json={**payload, "name": "VT fp-active sửa", "is_active": False},
        headers=_h(token),
    )
    assert r.status_code == 403, r.text


def test_reparent_department_requires_permission(client):
    # CÓ Sửa phòng ban nhưng KHÔNG `reparent` → đổi cấp trên bị 403 (đổi tên vẫn OK).
    token = _user_with_role("fp-reparent", "phong_ban", can_read=True, can_update=True)
    kd_id = _dept_id("Kinh doanh")
    other = _dept_id("Hành chính nhân sự")
    r = client.put(
        f"/api/departments/{kd_id}",
        json={
            "name": "Kinh doanh",
            "head_user_id": None,
            "description": None,
            "level_id": None,
            "parent_id": other,
        },
        headers=_h(token),
    )
    assert r.status_code == 403, r.text
