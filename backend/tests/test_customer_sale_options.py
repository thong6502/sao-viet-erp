"""Danh sách NV phụ trách — GET /api/customers/sales.

Hộp chọn này đổ vào 4 chỗ trên màn Khách hàng (lọc, cột bảng, ô gán, điều chuyển). Luật:

· ai ĐỦ TƯ CÁCH nhận khách = thuộc khối Kinh doanh (`departments.la_kinh_doanh`), hoặc — khi chưa
  tick phòng nào — người có quyền đọc module `khach_hang`;
· ai ĐANG GIỮ khách trong tầm nhìn cũng phải có tên (kể cả ngoài khối), nếu không thì bảng có dòng
  mà hộp lọc không lọc ra được. Họ mang `co_the_gan=False` để ô GÁN loại ra.
"""
from __future__ import annotations

from app.db import SessionLocal
from app.repositories.customer_repo import CustomerRepository
from app.repositories.rbac_repo import DepartmentRepository, RoleRepository
from app.repositories.user_repo import UserRepository
from app.security import create_access_token, hash_password


def _mk_user(username: str, role_name: str | None, dept_name: str) -> int:
    db = SessionLocal()
    try:
        users = UserRepository(db)
        u = users.get_by_username(username)
        if u is None:
            dept = DepartmentRepository(db).get_by_name(dept_name)
            role = (
                RoleRepository(db).get_by_name_and_department(role_name, dept.id)
                if role_name
                else None
            )
            u = users.create(username=username, name=username, password_hash=hash_password("x"))
            users.set_assignment(
                u, department_id=dept.id, role_id=role.id if role else None, is_active=True
            )
        return u.id
    finally:
        db.close()


def _token(uid: int) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(str(uid))}"}


def _mk_customer(name: str, sale_user_id: int | None) -> int:
    db = SessionLocal()
    try:
        c = CustomerRepository(db).create(
            name=name,
            tax_code=None,
            phone=None,
            email=None,
            address=None,
            contact_name=None,
            credit_limit=0,
            sale_user_id=sale_user_id,
            status="active",
        )
        return c.id
    finally:
        db.close()


def _set_khoi_kinh_doanh(dept_name: str, value: bool) -> None:
    db = SessionLocal()
    try:
        depts = DepartmentRepository(db)
        depts.set_la_kinh_doanh(depts.get_by_name(dept_name), value)
    finally:
        db.close()


def _by_name(rows: list[dict]) -> dict[str, dict]:
    return {r["name"]: r for r in rows}


def _by_id(rows: list[dict]) -> dict[int, dict]:
    """Tra theo id — tài khoản seed sẵn (admin) có tên hiển thị khác username."""
    return {r["id"]: r for r in rows}


def test_thu_kho_khong_lot_vao_danh_sach(client):
    """Lỗi đang sửa: hộp chọn đổ MỌI tài khoản nên Thủ kho đứng lẫn giữa Sale."""
    admin = _mk_user("admin", None, "Ban giám đốc")
    _mk_user("t-sale1", "NV Sales", "Kinh doanh")
    _mk_user("t-thukho", "Thủ kho", "Kho")

    r = client.get("/api/customers/sales", headers=_token(admin))
    assert r.status_code == 200, r.text
    ten = _by_name(r.json())
    assert "t-sale1" in ten
    assert "t-thukho" not in ten


def test_nguoi_ngoai_khoi_dang_giu_khach_van_hien_nhung_khong_gan_duoc(client):
    """Admin (Ban giám đốc) giữ 1 khách: phải lọc ra được, nhưng không phải người để GÁN mới."""
    admin = _mk_user("admin", None, "Ban giám đốc")
    _mk_customer("CTY ABC", admin)

    rows = client.get("/api/customers/sales", headers=_token(admin)).json()
    dong = _by_id(rows)[admin]
    assert dong["co_the_gan"] is False
    assert dong["so_kh"] == 1


def test_kem_vai_tro_va_phong(client):
    admin = _mk_user("admin", None, "Ban giám đốc")
    _mk_user("t-sale1", "NV Sales", "Kinh doanh")

    dong = _by_name(client.get("/api/customers/sales", headers=_token(admin)).json())["t-sale1"]
    assert dong["vai_tro"] == "NV Sales"
    assert dong["phong_ban"] == "Kinh doanh"
    assert dong["co_the_gan"] is True


def test_chua_tick_khoi_nao_thi_lui_ve_quyen_khach_hang(client):
    """Bỏ cờ khối ⇒ không rỗng, mà suy theo quyền — DB cũ chưa khai vẫn chạy đúng."""
    _set_khoi_kinh_doanh("Kinh doanh", False)
    admin = _mk_user("admin", None, "Ban giám đốc")
    _mk_user("t-sale1", "NV Sales", "Kinh doanh")
    _mk_user("t-thukho", "Thủ kho", "Kho")

    ten = _by_name(client.get("/api/customers/sales", headers=_token(admin)).json())
    assert ten["t-sale1"]["co_the_gan"] is True   # có quyền khach_hang
    assert "t-thukho" not in ten                  # không có quyền khach_hang


def test_scope_own_chi_thay_chinh_minh(client):
    s1 = _mk_user("t-sale1", "NV Sales", "Kinh doanh")
    _mk_user("t-sale2", "NV Sales", "Kinh doanh")

    rows = client.get("/api/customers/sales", headers=_token(s1)).json()
    assert [r["name"] for r in rows] == ["t-sale1"]


def test_scope_phong_lay_ca_cay_con(client):
    """TP KD ở phòng cha phải thấy sale của tổ con — dữ liệu đã tính theo cây, hộp chọn cũng phải."""
    tp = _mk_user("t-tpkd", "Trưởng phòng KD", "Kinh doanh")
    db = SessionLocal()
    try:
        depts = DepartmentRepository(db)
        kd = depts.get_by_name("Kinh doanh")
        kd1 = depts.get_by_name("Kinh doanh 1") or depts.create(name="Kinh doanh 1")
        depts.set_parent(kd1, kd.id)
        roles = RoleRepository(db)
        vai = roles.get_by_name_and_department("NV Sales KD1", kd1.id) or roles.create(
            name="NV Sales KD1", department_id=kd1.id
        )
        users = UserRepository(db)
        u = users.create(username="t-sale-kd1", name="t-sale-kd1", password_hash=hash_password("x"))
        users.set_assignment(u, department_id=kd1.id, role_id=vai.id, is_active=True)
    finally:
        db.close()

    ten = _by_name(client.get("/api/customers/sales", headers=_token(tp)).json())
    # Kế thừa cờ khối từ phòng cha ⇒ người của tổ con vừa có mặt, vừa gán được.
    assert "t-sale-kd1" in ten
    assert ten["t-sale-kd1"]["co_the_gan"] is True


def test_loc_khach_chua_gan_ai(client):
    admin = _mk_user("admin", None, "Ban giám đốc")
    _mk_customer("KH vô chủ", None)
    _mk_customer("KH có chủ", admin)

    r = client.get("/api/customers?chua_gan=true", headers=_token(admin))
    assert r.status_code == 200, r.text
    ten = [c["name"] for c in r.json()["items"]]
    assert ten == ["KH vô chủ"]
