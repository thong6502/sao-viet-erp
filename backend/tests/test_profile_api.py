"""Self-service profile tests (feat-019/020/021, spec-04).

Covers the enriched GET /api/auth/me profile, PATCH /api/users/me (display name), and the
avatar upload/remove endpoints (type + size validation).
"""
from __future__ import annotations

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


def test_update_name_succeeds(client):
    token = _login(client)
    resp = client.patch("/api/users/me", headers=_auth(token), json={"name": "Quản Trị Viên"})
    assert resp.status_code == 200
    assert resp.json()["name"] == "Quản Trị Viên"
    # Persisted: /me reflects it.
    assert client.get("/api/auth/me", headers=_auth(token)).json()["name"] == "Quản Trị Viên"


def test_update_name_trims_whitespace(client):
    token = _login(client)
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
    assert url.startswith("/static/avatars/")
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
