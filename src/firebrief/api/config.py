"""API configuration. Nothing here has a credential or a database default."""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict

# Not a credential: a sentinel that production refuses to start with.
DEVELOPMENT_SECRET = "development-only"  # noqa: S105


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="FIREBRIEF_", env_file=".env", extra="ignore")

    environment: str = "development"
    session_cookie: str = "firebrief_session"
    cookie_secure: bool = True

    allowed_origins: tuple[str, ...] = ()
    """Extra origins allowed to POST with a session cookie, beyond the request's own."""

    rate_limit_secret: str = DEVELOPMENT_SECRET
    """Keys the limiter's HMAC. Rotating it resets every counter."""

    trusted_proxy_hops: int = 0
    """How many proxies append to `X-Forwarded-For`. Zero means ignore the header."""

    client_ip_header: str | None = None
    """A platform header that carries the client address, e.g. `fly-client-ip`."""

    link_email_limit: int = 5
    link_ip_limit: int = 20
    link_window_seconds: int = 900
    verify_ip_limit: int = 60
    answer_user_limit: int = 60
    answer_window_seconds: int = 3600
