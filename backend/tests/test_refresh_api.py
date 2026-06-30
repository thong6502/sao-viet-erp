"""Refresh/logout endpoints + httpOnly cookie (feat-015, spec-03-auth-hardening).

Drives the real app via the TestClient cookie jar: login sets the cookie, refresh rotates
it, reuse/garbage/expired/locked are rejected, and logout revokes + clears it.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.db import SessionLocal
from app.repositories.refresh_token_repo import RefreshTokenRepository
from app.repositories.user_repo import UserRepository
from app.security import hash_refresh_token


def _set_cookie_headers(resp) -> list[str]:
    return [h for h in resp.headers.get_list("set-cookie") if h.startswith("refresh_token=")]


def _cookie_value(resp) -> str | None:
    for h in _set_cookie_headers(resp):
        return h.split("refresh_token=", 1)[1].split(";", 1)[0]
    return None


def test_login_sets_httponly_refresh_cookie_and_access_token(client, seed_credentials):
    resp = client.post("/api/auth/login", json=seed_credentials)
    assert resp.status_code == 200
    assert resp.json()["access_token"]
    headers = _set_cookie_headers(resp)
    assert headers, "login must set a refresh_token cookie"
    cookie = headers[0]
    assert "HttpOnly" in cookie
    assert "Path=/api/auth" in cookie
    assert _cookie_value(resp)  # non-empty


def test_refresh_returns_new_access_and_rotates_cookie(client, seed_credentials):
    login = client.post("/api/auth/login", json=seed_credentials)
    raw1 = _cookie_value(login)

    r = client.post("/api/auth/refresh")  # jar sends the current cookie
    assert r.status_code == 200
    assert r.json()["access_token"]
    raw2 = _cookie_value(r)
    assert raw2 and raw2 != raw1  # rotated


def test_reusing_pre_rotation_cookie_is_401(client, seed_credentials):
    login = client.post("/api/auth/login", json=seed_credentials)
    raw1 = _cookie_value(login)
    client.post("/api/auth/refresh")  # rotates raw1 away

    reuse = client.post("/api/auth/refresh", cookies={"refresh_token": raw1})
    assert reuse.status_code == 401


def test_missing_cookie_is_401(client):
    resp = client.post("/api/auth/refresh")
    assert resp.status_code == 401


def test_garbage_cookie_is_401_not_500(client):
    resp = client.post("/api/auth/refresh", cookies={"refresh_token": "not-a-real-token"})
    assert resp.status_code == 401


def test_expired_refresh_is_401(client, seed_credentials):
    # Seed an already-expired refresh row with a known raw value, then present it.
    client.post("/api/auth/login", json=seed_credentials)  # ensures admin seeded
    session = SessionLocal()
    try:
        admin = UserRepository(session).get_by_username(seed_credentials["username"])
        RefreshTokenRepository(session).create(
            user_id=admin.id,
            token_hash=hash_refresh_token("expired-raw"),
            family_id="fam-x",
            expires_at=datetime.now(timezone.utc) - timedelta(seconds=1),
        )
    finally:
        session.close()
    resp = client.post("/api/auth/refresh", cookies={"refresh_token": "expired-raw"})
    assert resp.status_code == 401


def test_logout_revokes_and_clears_cookie(client, seed_credentials):
    client.post("/api/auth/login", json=seed_credentials)
    out = client.post("/api/auth/logout")
    assert out.status_code == 204
    # Cookie cleared (Max-Age=0 / expired) in the response.
    assert _set_cookie_headers(out), "logout must clear the refresh cookie"
    # A subsequent refresh with the (now revoked) cookie still in the jar fails.
    again = client.post("/api/auth/refresh")
    assert again.status_code == 401


def test_logout_without_cookie_is_204(client):
    resp = client.post("/api/auth/logout")
    assert resp.status_code == 204


def test_refresh_for_locked_user_is_401(client, seed_credentials):
    client.post("/api/auth/login", json=seed_credentials)
    session = SessionLocal()
    try:
        users = UserRepository(session)
        admin = users.get_by_username(seed_credentials["username"])
        users.set_active(admin, False)
    finally:
        session.close()
    resp = client.post("/api/auth/refresh")
    assert resp.status_code == 401
    # Restore so other tests in the shared in-memory DB are unaffected.
    session = SessionLocal()
    try:
        users = UserRepository(session)
        users.set_active(users.get_by_username(seed_credentials["username"]), True)
    finally:
        session.close()
