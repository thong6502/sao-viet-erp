"""Đóng nhóm thành phẩm — đường dây HTTP `/api/san-xuat/kho/nhom/{id}/*` (§16 + §13.3).

Soi tầng router + gác quyền, KHÔNG dựng lại cả luồng phát hành (luật đã có 13 test service ở
`test_san_xuat_dong_nhom.py`, khớp schema đã kiểm bằng `model_validate` ở đó). Ở đây chỉ chứng minh:
  · GET checklist cổng đóng gác `san_xuat:read` — chưa đăng nhập → 401; admin (có read) chạm được
    service, nhóm không tồn tại → 400 (ràng buộc, đúng ánh xạ `_chay`);
  · POST đóng thiếu gác `san_xuat:assign_work` — admin (Giám đốc, KHÔNG có bit) → 403, đúng như
    các endpoint ghi khác của module (khớp `test_api_admin_thieu_bit_assign_work_403`).
"""
from __future__ import annotations

ADMIN = {"username": "admin", "password": "admin123"}


def _admin_h(client) -> dict[str, str]:
    tok = client.post("/api/auth/login", json=ADMIN).json()["access_token"]
    return {"Authorization": f"Bearer {tok}"}


def test_dieu_kien_dong_can_dang_nhap(client):
    assert client.get("/api/san-xuat/kho/nhom/1/dieu-kien-dong").status_code == 401


def test_dieu_kien_dong_admin_nhom_khong_ton_tai_400(client):
    # Admin có quyền đọc module → qua cổng RBAC, chạm service; nhóm 999999 không có → 400.
    resp = client.get(
        "/api/san-xuat/kho/nhom/999999/dieu-kien-dong", headers=_admin_h(client)
    )
    assert resp.status_code == 400


def test_dong_thieu_can_dang_nhap(client):
    assert (
        client.post("/api/san-xuat/kho/nhom/1/dong-thieu", json={"ly_do_id": 1}).status_code
        == 401
    )


def test_dong_thieu_admin_thieu_bit_assign_work_403(client):
    resp = client.post(
        "/api/san-xuat/kho/nhom/999999/dong-thieu",
        json={"ly_do_id": 1},
        headers=_admin_h(client),
    )
    assert resp.status_code == 403
