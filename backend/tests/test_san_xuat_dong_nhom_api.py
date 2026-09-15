"""Đóng nhóm thành phẩm — đường dây HTTP `/api/san-xuat/kho/nhom/{id}/*` (§16 + §13.3).

Soi tầng router + gác quyền, KHÔNG dựng lại cả luồng phát hành (luật đã có test service ở
`test_san_xuat_dong_nhom.py`, khớp schema đã kiểm bằng `model_validate` ở đó). Ở đây chỉ chứng minh:
  · GET checklist cổng đóng gác Xem ở ít nhất một tổ HOẶC ô tĩnh `kho:read` — chưa đăng nhập → 401;
    admin (có `kho:read`) chạm được service, nhóm không tồn tại → 400 (ràng buộc, đúng ánh xạ `_chay`);
  · POST đóng thiếu gác `require_quyen_to("qc")` — vai bật KCS ở ÍT NHẤT MỘT tổ mới qua cổng router
    (đúng tổ nào do service hỏi): admin (Giám đốc, không có dòng quyền theo tổ nào) → 403; người có
    KCS ở một tổ bất kỳ qua cổng, chạm service, nhóm không tồn tại → 400.
"""
from __future__ import annotations

from app.db import SessionLocal
from app.models.department import Department
from app.models.user import User
from app.security import create_access_token
from tests.quyen_to_fixtures import cap_quyen_to

ADMIN = {"username": "admin", "password": "admin123"}


def _admin_h(client) -> dict[str, str]:
    tok = client.post("/api/auth/login", json=ADMIN).json()["access_token"]
    return {"Authorization": f"Bearer {tok}"}


def _nguoi_co_kcs_mot_to_h() -> dict[str, str]:
    """Header của một tài khoản mới, vai chỉ bật Xem + KCS trên dòng quyền của MỘT tổ SX."""
    db = SessionLocal()
    try:
        to = Department(name="Tổ KCS Đóng Thiếu API", code="TO-KCS-DT-API", la_san_xuat=True)
        db.add(to)
        db.flush()
        u = User(username="kcs_dong_thieu_api", name="KCS đóng thiếu", password_hash="x",
                 department_id=to.id)
        db.add(u)
        db.flush()
        cap_quyen_to(db, u, to, viec=("qc",))
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


def test_dong_thieu_admin_khong_co_quyen_kcs_o_to_nao_403(client):
    resp = client.post(
        "/api/san-xuat/kho/nhom/999999/dong-thieu",
        json={},
        headers=_admin_h(client),
    )
    assert resp.status_code == 403


def test_dong_thieu_nguoi_co_kcs_mot_to_qua_cong_router(client):
    resp = client.post(
        "/api/san-xuat/kho/nhom/999999/dong-thieu",
        json={},
        headers=_nguoi_co_kcs_mot_to_h(),
    )
    assert resp.status_code == 400, resp.text          # qua cổng, service báo nhóm không tồn tại
