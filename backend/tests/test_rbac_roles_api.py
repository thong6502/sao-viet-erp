"""feat-007 — Vai trò admin API.

Admin can list modules/departments/roles, create a role (with per-department name
dedup), and read/save a role's permission matrix; a non-admin (NV Sales, no vai_tro
permission) is forbidden.
"""
from __future__ import annotations

from app.db import SessionLocal
from app.repositories.rbac_repo import DepartmentRepository, RoleRepository
from app.repositories.user_repo import UserRepository
from app.security import create_access_token, hash_password

ADMIN = {"username": "admin", "password": "admin123"}


def _admin_token(client) -> str:
    return client.post("/api/auth/login", json=ADMIN).json()["access_token"]


def _h(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _kd_id() -> int:
    db = SessionLocal()
    try:
        return DepartmentRepository(db).get_by_name("Kinh doanh").id
    finally:
        db.close()


def _sales_token() -> str:
    """A non-admin: NV Sales role has no vai_tro permission."""
    db = SessionLocal()
    try:
        users = UserRepository(db)
        existing = users.get_by_username("sales")
        if existing is not None:
            return create_access_token(str(existing.id))
        kd = DepartmentRepository(db).get_by_name("Kinh doanh")
        sales_role = RoleRepository(db).get_by_name_and_department("NV Sales", kd.id)
        user = users.create(
            username="sales", name="S", password_hash=hash_password("x")
        )
        users.set_assignment(
            user, department_id=kd.id, role_id=sales_role.id, is_active=True
        )
        return create_access_token(str(user.id))
    finally:
        db.close()


def test_admin_lists_modules(client):
    resp = client.get("/api/rbac/modules", headers=_h(_admin_token(client)))
    assert resp.status_code == 200
    keys = {m["key"] for m in resp.json()}
    assert {"khach_hang", "vai_tro", "nguoi_dung"} <= keys


def test_admin_lists_departments(client):
    resp = client.get("/api/departments", headers=_h(_admin_token(client)))
    assert resp.status_code == 200
    assert "Kinh doanh" in {d["name"] for d in resp.json()}


def test_create_role_with_dedup_and_validation(client):
    token = _admin_token(client)
    kd_id = _kd_id()

    created = client.post(
        "/api/roles", json={"name": "Telesales", "department_id": kd_id}, headers=_h(token)
    )
    assert created.status_code == 201
    role_id = created.json()["id"]

    # Duplicate name in the same department -> 409.
    dup = client.post(
        "/api/roles", json={"name": "Telesales", "department_id": kd_id}, headers=_h(token)
    )
    assert dup.status_code == 409

    # Empty name -> 422 (schema validation).
    empty = client.post(
        "/api/roles", json={"name": "", "department_id": kd_id}, headers=_h(token)
    )
    assert empty.status_code == 422

    listed = client.get(f"/api/roles?department_id={kd_id}", headers=_h(token))
    assert any(r["id"] == role_id for r in listed.json())


def test_matrix_get_defaults_and_save_persists(client):
    token = _admin_token(client)
    kd_id = _kd_id()
    role_id = client.post(
        "/api/roles", json={"name": "MatrixTest", "department_id": kd_id}, headers=_h(token)
    ).json()["id"]

    rows = client.get(f"/api/roles/{role_id}/permissions", headers=_h(token)).json()
    # Một dòng cho mỗi module. Vai mới TẮT HẾT, trừ ĐÚNG HAI ô bật sẵn (10/08/2026, xem
    # `RoleRepository.O_MAC_DINH`): Tự phục vụ + Nội quy — hai thứ là quyền của mọi người lao
    # động, không phải đặc quyền của một vai. Vai mới mà thiếu chúng thì người vừa được gán vai
    # không tự chấm công nổi và không đọc được nội quy.
    assert len(rows) >= 11
    bat_san = {"self_service", "noi_quy"}
    for r in rows:
        if r["module_key"] in bat_san:
            assert r["can_read"], f'{r["module_key"]} phải bật sẵn cho vai mới'
            # `self_service` cần CẢ ô Thao tác (`can_create`) — từ 11/08/2026 nó mới là thứ cho
            # chấm công / gửi đơn nghỉ · phiếu tăng ca · xin tạm ứng. Chỉ bật Xem thì vai mới gán
            # xong, thợ mở màn ra mà không bấm được nút nào.
            assert r["can_create"] is (r["module_key"] == "self_service"), (
                f'{r["module_key"]}: can_create sai — Tự phục vụ phải có ô Thao tác, Nội quy thì không'
            )
            assert not (r["can_update"] or r["can_delete"])
        else:
            assert not r["can_read"], f'{r["module_key"]} không được tự bật cho vai mới'
        assert r["scope"] == "own"

    for row in rows:
        if row["module_key"] == "khach_hang":
            row["can_read"] = True
            row["can_update"] = True
            row["scope"] = "department"
    saved = client.put(
        f"/api/roles/{role_id}/permissions", json={"permissions": rows}, headers=_h(token)
    )
    assert saved.status_code == 200

    again = client.get(f"/api/roles/{role_id}/permissions", headers=_h(token)).json()
    kh = next(r for r in again if r["module_key"] == "khach_hang")
    assert kh["can_read"] and kh["can_update"] and kh["scope"] == "department"
    assert not kh["can_delete"]


def test_bao_gia_approve_exception_roundtrips(client):
    """P8: toggle 'Duyệt báo giá đặc thù' (can_approve_exception) trên bao_gia đọc/lưu qua ma trận vai trò
    — đây là quyền chi tiết DUY NHẤT còn lại của Báo giá (các thao tác thường đã gộp vào 'Sửa')."""
    token = _admin_token(client)
    kd_id = _kd_id()
    db = SessionLocal()
    try:
        tp_id = RoleRepository(db).get_by_name_and_department("Trưởng phòng KD", kd_id).id
        sales_id = RoleRepository(db).get_by_name_and_department("NV Sales", kd_id).id
    finally:
        db.close()
    # Đọc: TP KD (seed) BẬT approve_exception, NV Sales TẮT.
    tp_bg = next(r for r in client.get(f"/api/roles/{tp_id}/permissions", headers=_h(token)).json()
                 if r["module_key"] == "bao_gia")
    assert tp_bg["can_approve_exception"] is True
    sales_rows = client.get(f"/api/roles/{sales_id}/permissions", headers=_h(token)).json()
    s_bg = next(r for r in sales_rows if r["module_key"] == "bao_gia")
    assert s_bg["can_approve_exception"] is False
    # Lưu: bật approve_exception cho NV Sales → đọc lại phải GIỮ (round-trip đúng field FE dùng).
    s_bg["can_approve_exception"] = True
    assert client.put(f"/api/roles/{sales_id}/permissions",
                      json={"permissions": sales_rows}, headers=_h(token)).status_code == 200
    reloaded = next(r for r in client.get(f"/api/roles/{sales_id}/permissions", headers=_h(token)).json()
                    if r["module_key"] == "bao_gia")
    assert reloaded["can_approve_exception"] is True


def test_rename_role(client):
    token = _admin_token(client)
    kd_id = _kd_id()
    role_id = client.post(
        "/api/roles", json={"name": "RenameMe", "department_id": kd_id}, headers=_h(token)
    ).json()["id"]

    renamed = client.put(
        f"/api/roles/{role_id}", json={"name": "Renamed"}, headers=_h(token)
    )
    assert renamed.status_code == 200
    assert renamed.json()["name"] == "Renamed"

    names = {r["name"] for r in client.get(f"/api/roles?department_id={kd_id}", headers=_h(token)).json()}
    assert "Renamed" in names and "RenameMe" not in names

    # Rename onto an existing name in the same department -> 409.
    clash = client.put(f"/api/roles/{role_id}", json={"name": "NV Sales"}, headers=_h(token))
    assert clash.status_code == 409


def test_delete_role_not_in_use(client):
    token = _admin_token(client)
    kd_id = _kd_id()
    role_id = client.post(
        "/api/roles", json={"name": "TempRole", "department_id": kd_id}, headers=_h(token)
    ).json()["id"]

    deleted = client.delete(f"/api/roles/{role_id}", headers=_h(token))
    assert deleted.status_code == 204

    ids = {r["id"] for r in client.get(f"/api/roles?department_id={kd_id}", headers=_h(token)).json()}
    assert role_id not in ids


def test_delete_role_in_use_is_blocked(client):
    token = _admin_token(client)
    kd_id = _kd_id()
    role_id = client.post(
        "/api/roles", json={"name": "BusyRole", "department_id": kd_id}, headers=_h(token)
    ).json()["id"]

    db = SessionLocal()
    try:
        users = UserRepository(db)
        user = users.create(
            username="busy", name="B", password_hash=hash_password("x")
        )
        users.set_assignment(user, department_id=kd_id, role_id=role_id, is_active=True)
    finally:
        db.close()

    blocked = client.delete(f"/api/roles/{role_id}", headers=_h(token))
    assert blocked.status_code == 409
    # Still present (not deleted).
    ids = {r["id"] for r in client.get(f"/api/roles?department_id={kd_id}", headers=_h(token)).json()}
    assert role_id in ids


def test_non_admin_forbidden(client):
    token = _sales_token()
    assert client.get("/api/rbac/modules", headers=_h(token)).status_code == 403
    assert (
        client.post(
            "/api/roles", json={"name": "X", "department_id": _kd_id()}, headers=_h(token)
        ).status_code
        == 403
    )
    # No phong_ban NOR vai_tro read → cannot even list role names.
    assert (
        client.get(f"/api/roles?department_id={_kd_id()}", headers=_h(token)).status_code
        == 403
    )


def _dept_viewer_token() -> str:
    """A user whose role grants ONLY phong_ban:read (no vai_tro permission) — the
    view-only employee looking at the department screen (spec-09)."""
    db = SessionLocal()
    try:
        users = UserRepository(db)
        existing = users.get_by_username("pb-viewer")
        if existing is not None:
            return create_access_token(str(existing.id))
        kd = DepartmentRepository(db).get_by_name("Kinh doanh")
        roles = RoleRepository(db)
        role = roles.create(name="PB Viewer", department_id=kd.id)
        roles.set_permission(
            role_id=role.id, module_key="phong_ban", can_read=True, scope="all"
        )
        u = users.create(username="pb-viewer", name="V", password_hash=hash_password("x"))
        users.set_assignment(u, department_id=kd.id, role_id=role.id, is_active=True)
        return create_access_token(str(u.id))
    finally:
        db.close()


def test_dept_viewer_can_list_role_names_but_not_matrix(client):
    """Role NAMES inside a department are part of viewing the department
    (phong_ban:read); the permission matrix stays behind vai_tro:read."""
    token = _dept_viewer_token()
    kd_id = _kd_id()

    listed = client.get(f"/api/roles?department_id={kd_id}", headers=_h(token))
    assert listed.status_code == 200
    roles = listed.json()
    assert {"NV Sales", "Trưởng phòng KD"} <= {r["name"] for r in roles}

    # …but the detailed permission matrix of any role stays forbidden.
    role_id = roles[0]["id"]
    assert (
        client.get(f"/api/roles/{role_id}/permissions", headers=_h(token)).status_code
        == 403
    )


def test_moi_cot_quyen_deu_di_het_duong_ong_len_API():
    """Thêm một cột quyền mà quên nối đường ống ⇒ ma trận hỏng ÂM THẦM, không báo gì.

    ĐÃ VỠ HAI LẦN, hai chặng khác nhau:
      • 11/08 (lần 1) `can_view_log` thiếu ở **schema API** ⇒ tick, Lưu, không lỗi — mở lại vẫn tắt.
      • 11/08 (lần 2) `can_view_salary` · `can_edit_salary` · `can_adjust` thiếu ở **`get_matrix`**
        ⇒ DB lưu đúng, máy chủ gác đúng, chỉ đường ĐỌC không trả về nên công tắc luôn hiện tắt.
        Chủ chốt tick đi tick lại, tưởng hệ thống không nhận.

    Bản guard đầu tiên KHÔNG bắt được lần 2: nó chỉ đếm "tên cột xuất hiện ≥2 lần trong
    role_service.py", mà `can_adjust` có mặt ở danh sách cờ + `save_matrix` là đủ 2 — vẫn thiếu ở
    `get_matrix`. Nay soi RIÊNG TỪNG HÀM, không đếm tổng nữa.

    Bốn chặng phía máy chủ (chặng thứ năm là giao diện — xem
    `test_giao_dien_va_may_chu_hoi_cung_mot_o_quyen`):
      model → `RoleRepository.set_permission` → `get_matrix` (đọc) + `save_matrix` (ghi) → schema API.
    """
    import inspect as _inspect

    from app.models.role import RolePermission
    from app.repositories.rbac_repo import RoleRepository
    from app.schemas.rbac import PermissionRow
    from app.services.role_service import RoleService

    cot = {
        c.name for c in RolePermission.__table__.columns
        if c.name not in ("id", "role_id", "module_key", "scope")
    }

    thieu_schema = sorted(cot - set(PermissionRow.model_fields))
    assert not thieu_schema, (
        "cột quyền chưa khai trong `PermissionRow` (schemas/rbac.py) ⇒ API nuốt mất khi lưu: "
        + ", ".join(thieu_schema)
    )

    tham_so = set(_inspect.signature(RoleRepository.set_permission).parameters)
    thieu_repo = sorted(cot - tham_so)
    assert not thieu_repo, (
        "cột quyền chưa có tham số trong `RoleRepository.set_permission` ⇒ seed/migration không "
        "đặt được: " + ", ".join(thieu_repo)
    )

    # Soi RIÊNG hai hàm — đây là chỗ bản guard cũ hụt.
    nguon_doc = _inspect.getsource(RoleService.get_matrix)
    thieu_doc = sorted(c for c in cot if c not in nguon_doc)
    assert not thieu_doc, (
        "cột quyền không có trong `RoleService.get_matrix` ⇒ ma trận LUÔN HIỆN TẮT dù đã bật và "
        "đã Lưu (DB vẫn đúng): " + ", ".join(thieu_doc)
    )

    nguon_ghi = _inspect.getsource(RoleService.save_matrix)
    thieu_ghi = sorted(c for c in cot if c not in nguon_ghi)
    assert not thieu_ghi, (
        "cột quyền không có trong `RoleService.save_matrix` ⇒ bật rồi Lưu nhưng KHÔNG xuống DB: "
        + ", ".join(thieu_ghi)
    )
