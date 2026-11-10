"""Magic-link authentication."""

from firebrief.auth.email import EmailSender, NullEmailSender, RecordingEmailSender
from firebrief.auth.service import (
    MAGIC_LINK_TTL,
    SESSION_TTL,
    AuthContext,
    AuthError,
    LinkNotUsable,
    LoginResult,
    login_with_magic_link,
    request_magic_link,
    resolve_session,
    revoke_session,
    revoke_user_sessions,
)
from firebrief.auth.tokens import InvalidToken, hash_token, new_token, tenant_from_token

__all__ = [
    "MAGIC_LINK_TTL",
    "SESSION_TTL",
    "AuthContext",
    "AuthError",
    "EmailSender",
    "InvalidToken",
    "LinkNotUsable",
    "LoginResult",
    "NullEmailSender",
    "RecordingEmailSender",
    "hash_token",
    "login_with_magic_link",
    "new_token",
    "request_magic_link",
    "resolve_session",
    "revoke_session",
    "revoke_user_sessions",
    "tenant_from_token",
]
