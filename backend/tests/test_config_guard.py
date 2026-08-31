"""Production secret guard (feat-012, spec-03-auth-hardening).

`assert_secure_config` must refuse to boot in production with an insecure JWT secret, and be
a no-op in development. Settings are built with explicit kwargs (highest precedence in
pydantic-settings) so these checks ignore the ambient env / .env file.
"""
from __future__ import annotations

import pytest

from app.config import (
    INSECURE_DEFAULT_JWT_SECRET,
    MIN_BCRYPT_ROUNDS,
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
    # `bcrypt_rounds` phải khai TAY: conftest đặt BCRYPT_ROUNDS=4 cho cả tiến trình test, mà
    # production thì cấm dưới sàn — không khai thì test này đo nhầm cái guard bcrypt.
    s = Settings(app_env="production", jwt_secret=STRONG_SECRET, bcrypt_rounds=MIN_BCRYPT_ROUNDS)
    assert_secure_config(s)  # must not raise


def test_production_bcrypt_rounds_thap_thi_khong_khoi_dong():
    """Bộ test chạy bcrypt 4 vòng cho nhanh — production lỡ nhặt phải cấu hình đó thì phải CHẾT
    ngay lúc khởi động, chứ không phải lặng lẽ băm mật khẩu thật bằng 4 vòng."""
    s = Settings(
        app_env="production", jwt_secret=STRONG_SECRET, bcrypt_rounds=MIN_BCRYPT_ROUNDS - 1
    )
    with pytest.raises(RuntimeError, match="BCRYPT_ROUNDS"):
        assert_secure_config(s)


def test_development_bcrypt_rounds_thap_van_chay():
    s = Settings(app_env="development", jwt_secret=INSECURE_DEFAULT_JWT_SECRET, bcrypt_rounds=4)
    assert_secure_config(s)  # must not raise


def test_development_default_secret_passes():
    # Zero-config local: the dev default still boots when APP_ENV is not production.
    s = Settings(app_env="development", jwt_secret=INSECURE_DEFAULT_JWT_SECRET)
    assert_secure_config(s)  # must not raise


def test_production_is_case_insensitive():
    s = Settings(app_env="Production", jwt_secret=INSECURE_DEFAULT_JWT_SECRET)
    with pytest.raises(RuntimeError):
        assert_secure_config(s)
