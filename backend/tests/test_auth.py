"""Auth feature tests (feat-002, spec-0001): login by username + /me against a seeded user."""
from __future__ import annotations


def test_health_ok(client):
    resp = client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_login_success_returns_token_and_user(client, seed_credentials):
    resp = client.post("/api/auth/login", json=seed_credentials)
    assert resp.status_code == 200
    body = resp.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"]  # non-empty
    assert body["user"]["username"] == seed_credentials["username"]
    # Email was removed entirely (spec-0001) — it must not appear on the auth surface.
    assert "email" not in body["user"]
    assert "password" not in body["user"]
    assert "password_hash" not in body["user"]


def test_login_wrong_password_is_401_generic(client, seed_credentials):
    resp = client.post(
        "/api/auth/login",
        json={"username": seed_credentials["username"], "password": "nope"},
    )
    assert resp.status_code == 401
    assert resp.json()["detail"] == "Tên đăng nhập hoặc mật khẩu không đúng"


def test_login_unknown_user_is_401_generic(client):
    resp = client.post(
        "/api/auth/login",
        json={"username": "ghost", "password": "whatever"},
    )
    assert resp.status_code == 401
    # Same message as wrong-password: no user enumeration.
    assert resp.json()["detail"] == "Tên đăng nhập hoặc mật khẩu không đúng"


def test_login_blank_username_is_422(client):
    resp = client.post(
        "/api/auth/login",
        json={"username": "", "password": "x"},
    )
    assert resp.status_code == 422


def test_me_with_valid_token_returns_user(client, seed_credentials):
    token = client.post("/api/auth/login", json=seed_credentials).json()["access_token"]
    resp = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert resp.json()["username"] == seed_credentials["username"]


def test_me_without_token_is_401(client):
    resp = client.get("/api/auth/me")
    assert resp.status_code == 401


def test_me_with_garbage_token_is_401(client):
    resp = client.get("/api/auth/me", headers={"Authorization": "Bearer not.a.jwt"})
    assert resp.status_code == 401
