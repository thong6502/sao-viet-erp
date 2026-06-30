"""Self-service change-password tests (feat-022, spec-04).

Verifies POST /api/auth/change-password: success returns 204 and kills the old session
(both the access token via token_version and the refresh token), wrong/duplicate passwords
are 400, and a weak new password is 422.
"""
from __future__ import annotations


def _login(client, username="admin", password="admin123") -> str:
    return client.post(
        "/api/auth/login", json={"username": username, "password": password}
    ).json()["access_token"]


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_change_password_success_returns_204(client):
    token = _login(client)
    resp = client.post(
        "/api/auth/change-password",
        headers=_auth(token),
        json={"current_password": "admin123", "new_password": "newpass123"},
    )
    assert resp.status_code == 204
    # The new password now works for login.
    assert client.post(
        "/api/auth/login", json={"username": "admin", "password": "newpass123"}
    ).status_code == 200


def test_old_access_token_rejected_after_change(client):
    token = _login(client)
    assert client.get("/api/auth/me", headers=_auth(token)).status_code == 200
    client.post(
        "/api/auth/change-password",
        headers=_auth(token),
        json={"current_password": "admin123", "new_password": "newpass123"},
    )
    # token_version bumped → the pre-change access token is now dead.
    assert client.get("/api/auth/me", headers=_auth(token)).status_code == 401


def test_old_refresh_token_rejected_after_change(client):
    token = _login(client)  # login also set an httpOnly refresh cookie on the client
    client.post(
        "/api/auth/change-password",
        headers=_auth(token),
        json={"current_password": "admin123", "new_password": "newpass123"},
    )
    # Every refresh token was revoked → refresh fails.
    assert client.post("/api/auth/refresh").status_code == 401


def test_wrong_current_password_is_400(client):
    token = _login(client)
    resp = client.post(
        "/api/auth/change-password",
        headers=_auth(token),
        json={"current_password": "wrong", "new_password": "newpass123"},
    )
    assert resp.status_code == 400
    assert resp.json()["detail"] == "Mật khẩu hiện tại không đúng"


def test_new_same_as_current_is_400(client):
    token = _login(client)
    resp = client.post(
        "/api/auth/change-password",
        headers=_auth(token),
        json={"current_password": "admin123", "new_password": "admin123"},
    )
    assert resp.status_code == 400
    assert resp.json()["detail"] == "Mật khẩu mới phải khác mật khẩu hiện tại"


def test_weak_new_password_is_422(client):
    token = _login(client)
    # Too short.
    assert client.post(
        "/api/auth/change-password",
        headers=_auth(token),
        json={"current_password": "admin123", "new_password": "ab1"},
    ).status_code == 422
    # Long enough but no digit.
    assert client.post(
        "/api/auth/change-password",
        headers=_auth(token),
        json={"current_password": "admin123", "new_password": "onlyletters"},
    ).status_code == 422


def test_change_password_requires_auth(client):
    resp = client.post(
        "/api/auth/change-password",
        json={"current_password": "admin123", "new_password": "newpass123"},
    )
    assert resp.status_code == 401
