"""Login tokens.

A token is `<tenant-id>.<random>`. The tenant id is not a secret: it lets verification open
the right tenant session before any query, so row-level security is never bypassed. The
random part is the secret, and only its hash is stored.
"""

from __future__ import annotations

import hashlib
import re
import secrets
import uuid

TOKEN_BYTES = 32
TOKEN_PATTERN = re.compile(
    r"^(?P<tenant>[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})\."
    r"(?P<secret>[A-Za-z0-9_-]{20,})$"
)


class InvalidToken(Exception):
    """The token is not in the expected shape."""


def new_token(tenant_id: uuid.UUID) -> str:
    return f"{tenant_id}.{secrets.token_urlsafe(TOKEN_BYTES)}"


def tenant_from_token(token: str) -> uuid.UUID:
    match = TOKEN_PATTERN.match(token)
    if match is None:
        raise InvalidToken("token is not in the expected form")
    return uuid.UUID(match.group("tenant"))


def hash_token(token: str) -> str:
    """What may be stored. A database read cannot mint a session from it."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
