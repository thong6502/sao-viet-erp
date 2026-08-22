"""Quyền CHI TIẾT (Cách B) cho các module ngoài Khách hàng — chặn thật ở backend.

Chứng minh các quyền mới tách khỏi CRUD:
  - bao_gia `approve`      : duyệt báo giá (→ accepted) tách khỏi `update`.
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


def test_employee_salary_fields_masked_without_view_salary(client):
    """nhan_su: role có `read` nhưng THIẾU `view_salary` → field nhạy cảm (BHXH/TK NH/
    nhóm lương) bị ẩn (None); có `view_salary` thì thấy lại. Field thường luôn thấy."""
    admin = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"}).json()["access_token"]
    db = SessionLocal()
    try:
        hcns = DepartmentRepository(db).get_by_name("Hành chính nhân sự").id
    finally:
        db.close()
    eid = client.post("/api/employees", json={"probation_end_date": "2025-12-31",
        "full_name": "NV Mật", "department_id": hcns, "hire_date": "2020-01-01",
        "social_insurance_no": "SI123", "bank_account": "9999", "payroll_group": "van_phong",
    }, headers=_h(admin)).json()["employee"]["id"]

    # admin có view_salary → thấy đủ
    full = client.get(f"/api/employees/{eid}", headers=_h(admin)).json()
    assert full["bank_account"] == "9999" and full["social_insurance_no"] == "SI123" and full["payroll_group"] == "van_phong"

    # role chỉ read, KHÔNG view_salary → ẩn
    masked = client.get(f"/api/employees/{eid}", headers=_h(_user_with_role("nv-no-salary", "nhan_su", can_read=True))).json()
    assert masked["bank_account"] is None and masked["social_insurance_no"] is None and masked["payroll_group"] is None
    assert masked["full_name"] == "NV Mật"  # field thường vẫn thấy

    # role read + view_salary → thấy lại
    seen = client.get(f"/api/employees/{eid}", headers=_h(_user_with_role("nv-has-salary", "nhan_su", can_read=True, can_view_salary=True))).json()
    assert seen["bank_account"] == "9999" and seen["payroll_group"] == "van_phong"


def test_quotation_accept_requires_update_permission(client):
    # P8: ghi nhận "Khách đồng ý" (accepted) = thao tác thường, gộp vào "Sửa". Vai chỉ-đọc → 403.
    # (Chốt quyền nằm TRƯỚC lookup nên không cần báo giá thật để chứng minh gate.)
    token = _user_with_role("fp-quote", "bao_gia", can_read=True)
    r = client.post(
        "/api/quotations/1/transition", json={"to_status": "accepted"}, headers=_h(token)
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


# P8: vòng đời báo giá (gửi/ghi nhận đồng ý-từ chối/hủy/hết hạn/tạo bản mới) KHÔNG tách quyền vụn — gộp
# vào "Sửa" (can_update). Vai chỉ-đọc (không Sửa) → mọi thao tác này bị 403.
def test_requote_requires_update_permission(client):
    # Chỉ-đọc báo giá (không Sửa) → tạo bản mới bị 403.
    token = _user_with_role("fp-requote", "bao_gia", can_read=True)
    r = client.post("/api/quotations/1/requote", json={"change_reason": "x"}, headers=_h(token))
    assert r.status_code == 403, r.text


def test_transition_requires_update_bao_gia(client):
    # Chỉ-đọc (không Sửa) → gửi khách bị 403 (thao tác vòng đời cần quyền Sửa).
    token = _user_with_role("fp-qstatus", "bao_gia", can_read=True)
    r = client.post(
        "/api/quotations/1/transition", json={"to_status": "sent"}, headers=_h(token)
    )
    assert r.status_code == 403, r.text


def test_cancel_quotation_requires_update_permission(client):
    # Chỉ-đọc (không Sửa) → hủy bị 403 (chốt quyền nằm TRƯỚC lookup nên không cần báo giá thật).
    token = _user_with_role("fp-cancel", "bao_gia", can_read=True)
    r = client.post(
        "/api/quotations/1/transition",
        json={"to_status": "cancelled", "cancel_reason": "x"},
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
