"""Production secret guard (feat-012, spec-03-auth-hardening).

`assert_secure_config` must refuse to boot in production with an insecure JWT secret, and be
a no-op in development. Settings are built with explicit kwargs (highest precedence in
pydantic-settings) so these checks ignore the ambient env / .env file.
"""
from __future__ import annotations

import pytest

from app.config import (
    INSECURE_DEFAULT_JWT_SECRET,
    MIN_JWT_SECRET_LEN,
    Settings,
    assert_secure_config,
)

STRONG_SECRET = "x" * MIN_JWT_SECRET_LEN  # exactly at the floor, non-default


def test_production_empty_secret_fails():
    s = Settings(app_env="production", jwt_secret="")
    with pytest.raises(RuntimeError, match="JWT_SECRET"):
        assert_secure_config(s)


def test_production_default_secret_fails():
    s = Settings(app_env="production", jwt_secret=INSECURE_DEFAULT_JWT_SECRET)
    with pytest.raises(RuntimeError, match="JWT_SECRET"):
        assert_secure_config(s)


def test_production_short_secret_fails():
    s = Settings(app_env="production", jwt_secret="x" * (MIN_JWT_SECRET_LEN - 1))
    with pytest.raises(RuntimeError, match="JWT_SECRET"):
        assert_secure_config(s)


def test_production_strong_secret_passes():
    s = Settings(app_env="production", jwt_secret=STRONG_SECRET)
    assert_secure_config(s)  # must not raise


def test_development_default_secret_passes():
    # Zero-config local: the dev default still boots when APP_ENV is not production.
    s = Settings(app_env="development", jwt_secret=INSECURE_DEFAULT_JWT_SECRET)
    assert_secure_config(s)  # must not raise


def test_production_is_case_insensitive():
    s = Settings(app_env="Production", jwt_secret=INSECURE_DEFAULT_JWT_SECRET)
    with pytest.raises(RuntimeError):
        assert_secure_config(s)
