"""Đóng nhóm thành phẩm — đường dây HTTP `/api/san-xuat/kho/nhom/{id}/*` (§16 + §13.3).

Soi tầng router + gác quyền, KHÔNG dựng lại cả luồng phát hành (luật đã có test service ở
`test_san_xuat_dong_nhom.py`, khớp schema đã kiểm bằng `model_validate` ở đó). Ở đây chỉ chứng minh:
  · GET checklist cổng đóng gác Xem ở ít nhất một tổ HOẶC ô tĩnh `kho:read` — chưa đăng nhập → 401;
    admin (có `kho:read`) chạm được service, nhóm không tồn tại → 400 (ràng buộc, đúng ánh xạ `_chay`);
  · POST đóng thiếu chỉ đòi đăng nhập ở router; ranh giới thật là TRƯỞNG phòng ban `is_kcs` ở
    service (KCS theo lệnh, mg 0306): admin (không đứng đầu tổ KCS nào) → 403; thành viên tổ KCS
    nhưng không phải trưởng → 403; trưởng tổ KCS chạm service, nhóm không tồn tại → 400.
"""
from __future__ import annotations

from app.db import SessionLocal
from app.models.department import Department
from app.models.user import User
from app.security import create_access_token

ADMIN = {"username": "admin", "password": "admin123"}


def _admin_h(client) -> dict[str, str]:
    tok = client.post("/api/auth/login", json=ADMIN).json()["access_token"]
    return {"Authorization": f"Bearer {tok}"}


def _nguoi_to_kcs_h(*, truong: bool) -> dict[str, str]:
    """Header của một tài khoản mới đứng trong một phòng ban `is_kcs` — `truong` thì đứng đầu phòng."""
    db = SessionLocal()
    try:
        ma = "TR" if truong else "TV"
        to = Department(name=f"Tổ KCS Đóng Thiếu {ma}", code=f"TO-KCS-DT-{ma}", is_kcs=True)
        db.add(to)
        db.flush()
        u = User(username=f"kcs_dong_thieu_{ma.lower()}", name="KCS đóng thiếu", password_hash="x",
                 department_id=to.id)
        db.add(u)
        db.flush()
        if truong:
            to.head_user_id = u.id
        db.commit()
        return {"Authorization": f"Bearer {create_access_token(str(u.id))}"}
    finally:
        db.close()


def test_dieu_kien_dong_can_dang_nhap(client):
    assert client.get("/api/san-xuat/kho/nhom/1/dieu-kien-dong").status_code == 401


def test_dieu_kien_dong_admin_nhom_khong_ton_tai_400(client):
    # Admin có `kho:read` → qua cổng router, chạm service; nhóm 999999 không có → 400.
    resp = client.get(
        "/api/san-xuat/kho/nhom/999999/dieu-kien-dong", headers=_admin_h(client)
    )
    assert resp.status_code == 400


def test_dong_thieu_can_dang_nhap(client):
    assert (
        client.post("/api/san-xuat/kho/nhom/1/dong-thieu", json={}).status_code
        == 401
    )


def test_dong_thieu_admin_khong_phai_truong_kcs_403(client):
    resp = client.post(
        "/api/san-xuat/kho/nhom/999999/dong-thieu",
        json={},
        headers=_admin_h(client),
    )
    assert resp.status_code == 403


def test_dong_thieu_thanh_vien_kcs_khong_phai_truong_403(client):
    resp = client.post(
        "/api/san-xuat/kho/nhom/999999/dong-thieu",
        json={},
        headers=_nguoi_to_kcs_h(truong=False),
    )
    assert resp.status_code == 403


def test_dong_thieu_truong_kcs_cham_service(client):
    resp = client.post(
        "/api/san-xuat/kho/nhom/999999/dong-thieu",
        json={},
        headers=_nguoi_to_kcs_h(truong=True),
    )
    assert resp.status_code == 400, resp.text          # qua cổng, service báo nhóm không tồn tại
