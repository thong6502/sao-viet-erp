"""Application configuration.

Cross-cutting concern loaded once from the environment (never hard-coded secrets;
see docs/SECURITY.md). `DATABASE_URL` selects SQLite (local/test) or Postgres
(Docker/prod) against the same SQL layer.
"""
from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict

# The well-known dev default. Convenient for zero-config local runs, but it is public
# (it lives in source/examples) so it must never sign tokens in production.
INSECURE_DEFAULT_JWT_SECRET = "dev-insecure-secret-change-me"

# A real signing secret must be hard to guess. 32 random chars is the floor.
MIN_JWT_SECRET_LEN = 32


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "GAN App"

    # Deployment environment. "production" turns on the strict secret guard below;
    # "development" (default) keeps zero-config local runs working.
    app_env: str = "development"

    # SQLite by default so the app + tests run with zero external services.
    # docker-compose overrides this to the Postgres service URL.
    database_url: str = "sqlite:///./dev.db"

    # --- Auth / JWT --------------------------------------------------------
    # JWT_SECRET MUST be overridden in any real deployment via the environment.
    jwt_secret: str = INSECURE_DEFAULT_JWT_SECRET
    jwt_algorithm: str = "HS256"
    # Short-lived: a stale access token is refreshed silently via the refresh cookie
    # (spec-03). Keep small so a revoked session's window is short.
    access_token_expire_minutes: int = 15
    # Long-lived refresh token (httpOnly cookie); rotated on every refresh (spec-03).
    refresh_token_expire_days: int = 7

    # --- Seed user (no self-registration this spec) ----------------------
    seed_admin_email: str = "admin@example.com"
    seed_admin_password: str = "admin123"
    seed_admin_name: str = "Admin"

    # Initial password set on HR-created accounts (no invite email this spec).
    # MUST be changed by the user in a real deployment (docs/SECURITY.md).
    default_user_password: str = "password123"

    # --- CORS --------------------------------------------------------------
    # Comma-separated list of allowed frontend origins.
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def is_production(self) -> bool:
        return self.app_env.strip().lower() == "production"


def assert_secure_config(s: Settings) -> None:
    """Fail fast in production when the JWT secret is insecure.

    Raises RuntimeError (so the process refuses to start) when `app_env` is production and
    `jwt_secret` is empty, the known public default, or shorter than `MIN_JWT_SECRET_LEN`.
    In development this is a no-op, so a fresh clone runs with zero configuration.
    """
    if not s.is_production:
        return

    secret = s.jwt_secret or ""
    if secret in ("", INSECURE_DEFAULT_JWT_SECRET) or len(secret) < MIN_JWT_SECRET_LEN:
        raise RuntimeError(
            "Refusing to start: APP_ENV=production requires a strong JWT_SECRET. "
            f"Set JWT_SECRET in the environment to a random string of at least "
            f"{MIN_JWT_SECRET_LEN} characters "
            '(e.g. `python -c "import secrets; print(secrets.token_urlsafe(48))"`).'
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
