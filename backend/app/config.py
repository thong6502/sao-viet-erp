"""Application configuration.

Cross-cutting concern loaded once from the environment (never hard-coded secrets;
see docs/SECURITY.md). `DATABASE_URL` selects SQLite (local/test) or Postgres
(Docker/prod) against the same SQL layer.
"""
from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "GAN App"

    # SQLite by default so the app + tests run with zero external services.
    # docker-compose overrides this to the Postgres service URL.
    database_url: str = "sqlite:///./dev.db"

    # --- Auth / JWT --------------------------------------------------------
    # JWT_SECRET MUST be overridden in any real deployment via the environment.
    jwt_secret: str = "dev-insecure-secret-change-me"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60

    # --- Seed user (no self-registration this sprint) ----------------------
    seed_admin_email: str = "admin@example.com"
    seed_admin_password: str = "admin123"
    seed_admin_name: str = "Admin"

    # Initial password set on HR-created accounts (no invite email this sprint).
    # MUST be changed by the user in a real deployment (docs/SECURITY.md).
    default_user_password: str = "password123"

    # --- CORS --------------------------------------------------------------
    # Comma-separated list of allowed frontend origins.
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
