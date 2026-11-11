"""API configuration. Nothing here has a credential or a database default."""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="FIREBRIEF_", env_file=".env", extra="ignore")

    session_cookie: str = "firebrief_session"
    cookie_secure: bool = True
    allowed_origins: tuple[str, ...] = ()
    """Extra origins allowed to POST with a session cookie, beyond the request's own."""
