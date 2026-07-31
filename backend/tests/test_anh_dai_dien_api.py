"""Ảnh đại diện phải đi kèm TỪNG người trong danh sách, không chỉ người đang đăng nhập.

Chủ báo 30/07/2026: *"chỗ nhân sự nó không xem được ảnh đại diện của user, người khác bấm vào thì
không xem được ảnh đại diện"*.

Nguyên nhân: `avatar_url` nằm trên bảng `users`, nhưng 3 schema của màn Phòng ban đều KHÔNG trả nó
ra. Frontend vì thế chỉ có duy nhất một nguồn ảnh — ảnh của người đang đăng nhập trong context xác
thực — nên nó hiện đúng một ảnh (của chính mình) và mọi người khác ra chữ viết tắt.

Chỗ khiến lỗi lọt qua được: FE đọc `(m as any).avatar_url`. Cái ép `as any` đó **bịt miệng
TypeScript**, đúng cái đáng ra phải báo "field này không tồn tại". Nên test phải nằm ở tầng API:
hợp đồng có field thì FE mới có gì mà đọc.
"""
from __future__ import annotations

from app.db import SessionLocal
from app.repositories.rbac_repo import DepartmentRepository
from app.repositories.user_repo import UserRepository
from tests.test_luong_api import _admin_token, _h

_ANH = "/api/files/avatars/9/anh-that.jpg"


def _gan_anh_cho_admin() -> tuple[int, int]:
    """Đặt ảnh cho tài khoản admin + trả (user_id, department_id của người đó)."""
    db = SessionLocal()
    try:
        users = UserRepository(db)
        u = users.get_by_username("admin")
        u.avatar_url = _ANH
        db.commit()
        return u.id, u.department_id
    finally:
        db.close()


def test_danh_sach_nhan_su_phong_tra_anh_cua_TUNG_nguoi(client):
    """⭐ Chính lỗi chủ báo: ảnh phải nằm trong từng dòng của danh sách.

    Không có field này thì FE không có cách nào biết ảnh của người khác — và nó sẽ rơi về ảnh của
    chính người đang xem, tức cả màn chỉ có đúng một ảnh."""
    token = _admin_token(client)
    user_id, dept_id = _gan_anh_cho_admin()

    r = client.get(f"/api/departments/{dept_id}/users", headers=_h(token))
    assert r.status_code == 200, r.text
    rows = r.json()
    assert rows, "phòng của admin phải có ít nhất một hồ sơ"

    assert all("avatar_url" in row for row in rows), \
        f"MỌI dòng phải có khoá `avatar_url` (kể cả khi null): {rows}"
    cua_admin = [row for row in rows if row["user_id"] == user_id]
    assert cua_admin, f"không thấy dòng của user {user_id}: {rows}"
    assert cua_admin[0]["avatar_url"] == _ANH


def test_nguoi_chua_co_tai_khoan_thi_anh_la_null_chu_khong_no(client):
    """Công nhân xưởng không cần đăng nhập ⇒ không có `users` row ⇒ không có ảnh.

    Phải là `null` gọn gàng để FE hiện chữ viết tắt, KHÔNG được nổ 500 vì đọc thuộc tính trên
    `None` — đường này rất dễ vỡ khi thêm field mới lấy từ user row."""
    token = _admin_token(client)
    db = SessionLocal()
    try:
        dept_id = DepartmentRepository(db).get_by_name("Sản xuất").id
    finally:
        db.close()

    r = client.get(f"/api/departments/{dept_id}/users", headers=_h(token))
    assert r.status_code == 200, r.text
    for row in r.json():
        if row["user_id"] is None:
            assert row["avatar_url"] is None


def test_danh_sach_phong_tra_anh_cua_TRUONG_phong(client):
    """Khối "Trưởng phòng" ở đầu khay chi tiết cũng phải thấy ảnh — cùng lý do."""
    token = _admin_token(client)
    user_id, dept_id = _gan_anh_cho_admin()

    db = SessionLocal()
    try:
        depts = DepartmentRepository(db)
        d = depts.get_by_id(dept_id)
        d.head_user_id = user_id
        db.commit()
    finally:
        db.close()

    r = client.get("/api/departments", headers=_h(token))
    assert r.status_code == 200, r.text
    rows = r.json()
    assert all("head_avatar_url" in row for row in rows), "mọi phòng phải có khoá này"

    cua_ta = [row for row in rows if row["id"] == dept_id][0]
    assert cua_ta["head_avatar_url"] == _ANH
    # Phòng chưa gán trưởng thì null — không được mượn ảnh của phòng khác.
    for row in rows:
        if row["head_user_id"] is None:
            assert row["head_avatar_url"] is None, f"phòng chưa có trưởng mà có ảnh: {row}"


def test_danh_sach_chon_truong_phong_cung_co_anh(client):
    """Danh sách ứng viên Trưởng phòng (`UserBrief`) — chọn người bằng MẶT nhanh hơn bằng tên,
    nhất là khi công ty có nhiều người trùng tên."""
    token = _admin_token(client)
    user_id, dept_id = _gan_anh_cho_admin()

    r = client.get(f"/api/departments/{dept_id}/head-candidates", headers=_h(token))
    assert r.status_code == 200, r.text
    rows = r.json()
    assert all("avatar_url" in row for row in rows), f"thiếu khoá `avatar_url`: {rows}"
    assert [row for row in rows if row["id"] == user_id][0]["avatar_url"] == _ANH
