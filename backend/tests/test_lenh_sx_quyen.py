"""Hai ô quyền mới của khối Sản xuất: `lenh_san_xuat` (Lệnh sản xuất) và `theo_doi_san_xuat`
(Theo dõi sản xuất). Task 1 chỉ dựng NỀN QUYỀN — chưa có màn, chưa có API riêng — nên bài test
chỉ canh ba việc: (1) hai khoá có mặt trong danh mục module, (2) vai đủ điều kiện được cấp đúng
phạm vi, (3) vai KHÔNG đủ điều kiện (nhất là mẫu Tổ trưởng SX/Thợ SX) không bị cấp.

Luật phạm vi (chốt tại task-1-brief.md sau MỘT VÒNG SỬA — bản đầu "scope rộng hơn giữa
`don_hang_ban` và `san_xuat`, không phân biệt scope nào" có lỗ hổng: nó lỡ cấp cho Tổ trưởng SX/
Thợ SX ở scope `own`, mà scope `own` trên HAI MÀN MỚI nghĩa là "lệnh của đơn CHÍNH TÔI bán" — hai
vai đó không bán đơn nào nên màn sẽ luôn rỗng, một mục menu chết. Luật ĐÃ SỬA:
    - vai đọc được `don_hang_ban` (can_read=True, MỌI scope kể cả `own`) → cấp, lấy scope đó.
    - HOẶC vai giữ `san_xuat` ở scope `department`/`all` → cấp, lấy scope đó.
    - có cả hai vế → lấy scope RỘNG HƠN (thứ tự own < department < all).
    - CHỈ đủ điều kiện nhờ `san_xuat` ở scope `own` → KHÔNG cấp.
    - không đọc được khoá nào trong hai khoá gốc → không cấp gì.
"""
from __future__ import annotations

from app.db import SessionLocal
from app.db_migrations import _migrate_hai_man_chi_doc
from app.models.role import SCOPE_ALL, SCOPE_DEPARTMENT, SCOPE_OWN, SCOPES
from app.repositories.rbac_repo import DepartmentRepository, RoleRepository


def _dang_nhap(client, seed_credentials) -> str:
    r = client.post("/api/auth/login", json=seed_credentials)
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _scope_ky_vong(quyen: dict) -> str | None:
    """Scope kỳ vọng của hai khoá mới cho MỘT vai — cài y nguyên luật đã chốt (xem docstring
    module). Trả None nghĩa là KHÔNG được cấp."""
    ung_vien = []
    don = quyen.get("don_hang_ban")
    if don and don["can_read"]:
        ung_vien.append(don["scope"])
    sx = quyen.get("san_xuat")
    if sx and sx["can_read"] and sx["scope"] != SCOPE_OWN:
        ung_vien.append(sx["scope"])
    if not ung_vien:
        return None
    return max(ung_vien, key=SCOPES.index)


def test_hai_module_moi_co_trong_danh_muc(client, seed_credentials):
    token = _dang_nhap(client, seed_credentials)
    r = client.get("/api/rbac/modules", headers=_auth(token))
    assert r.status_code == 200, r.text
    keys = {m["key"] for m in r.json()}
    assert "lenh_san_xuat" in keys
    assert "theo_doi_san_xuat" in keys


def test_moi_vai_duoc_cap_hoac_khong_cap_dung_luat(client, seed_credentials):
    """Duyệt TOÀN BỘ vai đang seed (qua đúng API mà giao diện Vai trò dùng — `GET /api/roles`
    đòi `department_id`, không có đường liệt kê hết vai cùng lúc; ma trận quyền lấy qua
    `GET /api/roles/{id}/permissions`, `RoleOut` không có field `permissions`).

    Với MỖI vai: tính scope kỳ vọng theo `_scope_ky_vong`; None thì hai khoá mới phải KHÔNG được
    cấp (can_read=False hoặc vắng mặt); có giá trị thì phải được cấp ĐÚNG scope đó."""
    token = _dang_nhap(client, seed_credentials)
    depts = client.get("/api/departments", headers=_auth(token))
    assert depts.status_code == 200, depts.text

    so_duoc_cap = 0
    so_khong_cap = 0
    for dept in depts.json():
        roles_resp = client.get(
            "/api/roles", params={"department_id": dept["id"]}, headers=_auth(token)
        )
        assert roles_resp.status_code == 200, roles_resp.text
        for vai in roles_resp.json():
            perm_resp = client.get(
                f"/api/roles/{vai['id']}/permissions", headers=_auth(token)
            )
            assert perm_resp.status_code == 200, perm_resp.text
            quyen = {p["module_key"]: p for p in perm_resp.json()}
            ky_vong = _scope_ky_vong(quyen)
            nhan = f"vai '{vai['name']}' (phòng '{dept['name']}')"
            if ky_vong is None:
                so_khong_cap += 1
                for khoa in ("lenh_san_xuat", "theo_doi_san_xuat"):
                    assert not quyen.get(khoa, {}).get("can_read", False), (
                        f"{nhan} không đủ điều kiện nhưng vẫn được cấp '{khoa}'"
                    )
                continue
            so_duoc_cap += 1
            for khoa in ("lenh_san_xuat", "theo_doi_san_xuat"):
                assert khoa in quyen, f"{nhan} thiếu module '{khoa}'"
                assert quyen[khoa]["can_read"] is True, (
                    f"{nhan}: '{khoa}' có mặt nhưng can_read=False"
                )
                assert quyen[khoa]["scope"] == ky_vong, (
                    f"{nhan}: '{khoa}' scope={quyen[khoa]['scope']!r}, kỳ vọng {ky_vong!r}"
                )
    # Chống test rỗng-mà-vẫn-xanh: bộ seed hiện có 13 vai đủ điều kiện, >=8 vai không đủ.
    assert so_duoc_cap >= 10
    assert so_khong_cap >= 5


def test_vai_chi_co_san_xuat_scope_own_khong_duoc_cap(client, seed_credentials):
    """Khoá lại ĐÚNG lỗi đã xảy ra một lần trong quá trình làm task này: bản luật đầu tiên
    ("scope rộng hơn giữa don_hang_ban/san_xuat", không loại trừ `own`) đã lỡ cấp cho 'Tổ trưởng
    SX' và 'Thợ SX' — hai vai chỉ đọc `san_xuat` ở scope `own`, không đọc `don_hang_ban`. Scope
    `own` trên HAI MÀN MỚI nghĩa là "lệnh của đơn CHÍNH TÔI bán": hai vai này không bán đơn nào
    nên màn sẽ luôn rỗng — một mục menu chết. Nếu ai cấp lại (kể cả vô tình, kiểu "sửa cho nhất
    quán với các vai khác"), test này phải đỏ ngay."""
    token = _dang_nhap(client, seed_credentials)
    depts = client.get("/api/departments", headers=_auth(token))
    assert depts.status_code == 200, depts.text
    sx_dept = next(d for d in depts.json() if d["name"] == "Sản xuất")

    roles_resp = client.get(
        "/api/roles", params={"department_id": sx_dept["id"]}, headers=_auth(token)
    )
    assert roles_resp.status_code == 200, roles_resp.text

    ten_can_kiem = {"Tổ trưởng SX", "Thợ SX"}
    da_kiem = set()
    for vai in roles_resp.json():
        if vai["name"] not in ten_can_kiem:
            continue
        da_kiem.add(vai["name"])
        perm_resp = client.get(
            f"/api/roles/{vai['id']}/permissions", headers=_auth(token)
        )
        assert perm_resp.status_code == 200, perm_resp.text
        quyen = {p["module_key"]: p for p in perm_resp.json()}

        # Xác nhận đúng tiền đề của lỗi: san_xuat=own, không đọc don_hang_ban.
        assert quyen["san_xuat"]["can_read"] is True
        assert quyen["san_xuat"]["scope"] == SCOPE_OWN
        assert quyen.get("don_hang_ban", {}).get("can_read", False) is False

        for khoa in ("lenh_san_xuat", "theo_doi_san_xuat"):
            assert quyen.get(khoa, {}).get("can_read", False) is False, (
                f"vai '{vai['name']}' được cấp '{khoa}' dù san_xuat chỉ ở scope own "
                "-> màn sẽ luôn rỗng (đơn CHÍNH TÔI bán, mà vai này không bán đơn nào)"
            )
    assert da_kiem == ten_can_kiem, f"thiếu vai để kiểm: {ten_can_kiem - da_kiem}"


def test_migration_0246_chep_quyen_cho_vai_tu_tao(client):
    """mg `0246` lo phần `seed_roles` KHÔNG đụng tới: vai do người dùng tự tạo sau khi hệ thống
    đã chạy production một thời gian. `client` fixture đã seed đủ modules/departments — dựng
    trực tiếp bốn vai TỰ TẠO (không có trong seed.ROLES) qua repository, giả lập DB đã có dữ
    liệu từ trước khi migration 0246 chạy, rồi gọi thẳng hàm migration."""
    db = SessionLocal()
    try:
        depts = DepartmentRepository(db)
        roles = RoleRepository(db)
        sx = depts.get_by_name("Sản xuất")
        kd = depts.get_by_name("Kinh doanh")
        assert sx is not None and kd is not None

        # A. Chỉ đọc `san_xuat` ở scope department (đủ điều kiện, không có `don_hang_ban`).
        vai_a = roles.create(name="Test A — san_xuat department", department_id=sx.id)
        roles.set_permission(
            role_id=vai_a.id, module_key="san_xuat", can_read=True, scope=SCOPE_DEPARTMENT,
        )
        # B. Đọc CẢ HAI, scope khác nhau — kỳ vọng lấy scope RỘNG HƠN (all).
        vai_b = roles.create(name="Test B — cả hai, scope khác nhau", department_id=kd.id)
        roles.set_permission(
            role_id=vai_b.id, module_key="don_hang_ban", can_read=True, scope=SCOPE_OWN,
        )
        roles.set_permission(
            role_id=vai_b.id, module_key="san_xuat", can_read=True, scope=SCOPE_ALL,
        )
        # C. Không đọc khoá nào trong hai khoá gốc -> không được cấp gì.
        vai_c = roles.create(name="Test C — không liên quan", department_id=kd.id)
        roles.set_permission(
            role_id=vai_c.id, module_key="khach_hang", can_read=True, scope=SCOPE_ALL,
        )
        # D. Mẫu Tổ trưởng SX/Thợ SX: CHỈ đọc `san_xuat` ở scope OWN, không có `don_hang_ban`
        # -> KHÔNG được cấp (đúng luật đã sửa, không phải bản nháp đầu).
        vai_d = roles.create(name="Test D — san_xuat own (mẫu Tổ trưởng SX)", department_id=sx.id)
        roles.set_permission(
            role_id=vai_d.id, module_key="san_xuat", can_read=True, scope=SCOPE_OWN,
        )
        # E. Đọc `don_hang_ban` ở scope OWN, không có `san_xuat` -> ĐƯỢC cấp scope OWN (own trên
        # `don_hang_ban` hợp lệ — người bán có đơn của chính họ, không giống vế san_xuat).
        vai_e = roles.create(name="Test E — don_hang_ban own", department_id=kd.id)
        roles.set_permission(
            role_id=vai_e.id, module_key="don_hang_ban", can_read=True, scope=SCOPE_OWN,
        )

        # Trước migration: cả năm vai đều CHƯA có hai khoá mới.
        for vai in (vai_a, vai_b, vai_c, vai_d, vai_e):
            for khoa in ("lenh_san_xuat", "theo_doi_san_xuat"):
                assert roles.get_permission(vai.id, khoa) is None

        _migrate_hai_man_chi_doc(db)

        for khoa in ("lenh_san_xuat", "theo_doi_san_xuat"):
            pa = roles.get_permission(vai_a.id, khoa)
            assert pa is not None and pa.can_read is True and pa.scope == SCOPE_DEPARTMENT
            pb = roles.get_permission(vai_b.id, khoa)
            assert pb is not None and pb.can_read is True and pb.scope == SCOPE_ALL
            assert roles.get_permission(vai_c.id, khoa) is None
            assert roles.get_permission(vai_d.id, khoa) is None, (
                f"vai D (san_xuat=own, mẫu Tổ trưởng SX) không được cấp '{khoa}'"
            )
            pe = roles.get_permission(vai_e.id, khoa)
            assert pe is not None and pe.can_read is True and pe.scope == SCOPE_OWN

        # Idempotent: chạy lại không đẻ hàng trùng (set_permission upsert nên chỉ cần kiểm còn
        # đúng MỘT dòng mỗi khoá — permissions_for trả list phẳng, đếm được số dòng trùng module).
        _migrate_hai_man_chi_doc(db)
        for vai in (vai_a, vai_b, vai_e):
            for khoa in ("lenh_san_xuat", "theo_doi_san_xuat"):
                so_dong = sum(
                    1 for p in roles.permissions_for(vai.id) if p.module_key == khoa
                )
                assert so_dong == 1, f"vai {vai.name}: '{khoa}' bị đẻ trùng ({so_dong} dòng)"
    finally:
        db.close()
