"""API configuration. Nothing here has a credential or a database default."""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="FIREBRIEF_", env_file=".env", extra="ignore")

    session_cookie: str = "firebrief_session"
    cookie_secure: bool = True
    allowed_origins: tuple[str, ...] = ()
    link_email_limit: int = 5
    link_ip_limit: int = 20
    link_window_seconds: int = 900
    answer_user_limit: int = 60
    answer_window_seconds: int = 3600
    trust_forwarded_for: bool = False
    """Only true behind a proxy that overwrites `X-Forwarded-For`."""
    """Extra origins allowed to POST with a session cookie, beyond the request's own."""
