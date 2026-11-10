"""API configuration. Everything with a default is a development default."""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="FIREBRIEF_", env_file=".env", extra="ignore")

    database_url: str = (
        "postgresql+asyncpg://firebrief:firebrief_dev@127.0.0.1:55433/firebrief_test"
    )
    session_cookie: str = "firebrief_session"
    cookie_secure: bool = True
    allowed_origins: tuple[str, ...] = ()
    """Origins allowed to POST with a session cookie. Empty means same-origin only."""
