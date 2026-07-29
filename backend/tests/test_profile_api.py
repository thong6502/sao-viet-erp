"""Self-service profile tests (feat-019/020/021, spec-04).

Covers the enriched GET /api/auth/me profile, PATCH /api/users/me (display name), and the
avatar upload/remove endpoints (type + size validation).
"""
from __future__ import annotations

from app.db import SessionLocal
from app.repositories.employee_repo import EmployeeRepository
from app.repositories.user_repo import UserRepository

# 1x1 transparent PNG (smallest valid PNG) — used as a real image upload payload.
PNG_1PX = bytes.fromhex(
    "89504e470d0a1a0a0000000d4948445200000001000000010806000000"
    "1f15c4890000000d49444154789c6360000002000100ffff03000006000557bfabd40000000049454e44ae426082"
)


def _login(client) -> str:
    return client.post(
        "/api/auth/login", json={"username": "admin", "password": "admin123"}
    ).json()["access_token"]


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _orphan_admin() -> None:
    """Gỡ hồ sơ khỏi tài khoản admin (tầng DB).

    LUẬT hiện tại: mọi tài khoản đều có hồ sơ (`backfill_employee_profiles`) ⇒ tên hiển thị do HỒ
    SƠ quyết, tự đổi tên qua PATCH /users/me bị chặn (nhờ HCNS). Tính năng tự-đổi-tên chỉ còn áp
    cho tài khoản MỒ CÔI (dữ liệu cũ) — dựng tiền đề đó thẳng ở DB để canh đúng nhánh này."""
    db = SessionLocal()
    try:
        emp = EmployeeRepository(db).get_by_user_id(UserRepository(db).get_by_username("admin").id)
        if emp is not None:
            emp.user_id = None
            db.commit()
    finally:
        db.close()


def test_me_returns_enriched_profile(client):
    token = _login(client)
    body = client.get("/api/auth/me", headers=_auth(token)).json()
    assert body["username"] == "admin"
    # Enriched fields present (spec-04 account panel).
    for key in ("department_name", "role_name", "created_at", "avatar_url"):
        assert key in body
    # Seeded admin is linked to a department + role (feat-004 seed).
    assert body["department_name"] is not None
    assert body["role_name"] is not None
    assert body["avatar_url"] is None  # no avatar yet


def test_update_name_blocked_when_linked_to_employee(client):
    """LUẬT (mọi tài khoản có hồ sơ): tên hiển thị lấy từ hồ sơ nhân sự → tự đổi tên bị chặn 400."""
    token = _login(client)   # admin đã nối hồ sơ NV009 (seed)
    resp = client.patch("/api/users/me", headers=_auth(token), json={"name": "Quản Trị Viên"})
    assert resp.status_code == 400


def test_update_name_succeeds(client):
    token = _login(client)
    _orphan_admin()   # tài khoản mồ côi (dữ liệu cũ) mới tự đổi tên được
    resp = client.patch("/api/users/me", headers=_auth(token), json={"name": "Quản Trị Viên"})
    assert resp.status_code == 200
    assert resp.json()["name"] == "Quản Trị Viên"
    # Persisted: /me reflects it.
    assert client.get("/api/auth/me", headers=_auth(token)).json()["name"] == "Quản Trị Viên"


def test_update_name_trims_whitespace(client):
    token = _login(client)
    _orphan_admin()
    resp = client.patch("/api/users/me", headers=_auth(token), json={"name": "  Tên Mới  "})
    assert resp.status_code == 200
    assert resp.json()["name"] == "Tên Mới"


def test_update_name_blank_is_422(client):
    token = _login(client)
    assert client.patch("/api/users/me", headers=_auth(token), json={"name": "   "}).status_code == 422
    assert client.patch("/api/users/me", headers=_auth(token), json={"name": ""}).status_code == 422


def test_update_name_requires_auth(client):
    assert client.patch("/api/users/me", json={"name": "x"}).status_code == 401


def test_upload_avatar_succeeds_and_me_reflects_it(client):
    token = _login(client)
    resp = client.post(
        "/api/users/me/avatar",
        headers=_auth(token),
        files={"file": ("a.png", PNG_1PX, "image/png")},
    )
    assert resp.status_code == 200
    url = resp.json()["avatar_url"]
    assert url.startswith("/api/files/avatars/")
    # The file is actually served.
    assert client.get(url).status_code == 200
    # /me now carries the avatar path.
    assert client.get("/api/auth/me", headers=_auth(token)).json()["avatar_url"] == url


def test_upload_avatar_wrong_type_is_400(client):
    token = _login(client)
    resp = client.post(
        "/api/users/me/avatar",
        headers=_auth(token),
        files={"file": ("note.txt", b"hello", "text/plain")},
    )
    assert resp.status_code == 400


def test_upload_avatar_too_large_is_400(client):
    token = _login(client)
    big = b"\x89PNG" + b"0" * (2 * 1024 * 1024 + 1)  # > 2 MB
    resp = client.post(
        "/api/users/me/avatar",
        headers=_auth(token),
        files={"file": ("big.png", big, "image/png")},
    )
    assert resp.status_code == 400


def test_remove_avatar_clears_it(client):
    token = _login(client)
    client.post(
        "/api/users/me/avatar",
        headers=_auth(token),
        files={"file": ("a.png", PNG_1PX, "image/png")},
    )
    resp = client.delete("/api/users/me/avatar", headers=_auth(token))
    assert resp.status_code == 204
    assert client.get("/api/auth/me", headers=_auth(token)).json()["avatar_url"] is None
