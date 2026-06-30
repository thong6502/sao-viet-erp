"""Short access token + token_version hard-revoke (feat-013, spec-03-auth-hardening).

A valid access token works; an expired one is rejected; and bumping the user's
token_version immediately kills a previously-issued (still-unexpired) token.
"""
from __future__ import annotations

import time

import jwt

from app.config import settings
from app.db import SessionLocal
from app.repositories.user_repo import UserRepository


def test_current_token_works(client, seed_credentials):
    token = client.post("/api/auth/login", json=seed_credentials).json()["access_token"]
    resp = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200


def test_access_token_embeds_tv_claim(client, seed_credentials):
    token = client.post("/api/auth/login", json=seed_credentials).json()["access_token"]
    claims = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    assert claims["tv"] == 0  # seeded admin starts at token_version 0


def test_expired_access_token_is_401(client):
    now = int(time.time())
    expired = jwt.encode(
        {"sub": "1", "tv": 0, "iat": now - 3600, "exp": now - 1800},
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )
    resp = client.get("/api/auth/me", headers={"Authorization": f"Bearer {expired}"})
    assert resp.status_code == 401


def test_bumped_token_version_rejects_old_token(client, seed_credentials):
    token = client.post("/api/auth/login", json=seed_credentials).json()["access_token"]
    # Sanity: the token is currently accepted.
    assert client.get(
        "/api/auth/me", headers={"Authorization": f"Bearer {token}"}
    ).status_code == 200

    # Hard-revoke: bump the admin's token_version (logout-all / lock).
    session = SessionLocal()
    try:
        users = UserRepository(session)
        admin = users.get_by_username(seed_credentials["username"])
        users.bump_token_version(admin)
    finally:
        session.close()

    # The previously-issued token now carries a stale tv -> rejected.
    resp = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 401

    # A fresh login mints a token at the new version and works again.
    new_token = client.post("/api/auth/login", json=seed_credentials).json()["access_token"]
    assert client.get(
        "/api/auth/me", headers={"Authorization": f"Bearer {new_token}"}
    ).status_code == 200
