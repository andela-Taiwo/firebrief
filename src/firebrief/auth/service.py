"""Magic-link login and session resolution.

Every function takes an engine and opens a tenant session from the token or the caller's
tenant id. There is no code path here that queries across tenants.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, cast

from sqlalchemy import func, select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncEngine

from firebrief.auth.email import EmailSender
from firebrief.auth.tokens import InvalidToken, hash_token, new_token, tenant_from_token
from firebrief.db.models import AuthMagicLink, AuthSession, Membership, User
from firebrief.db.session import tenant_session

MAGIC_LINK_TTL = timedelta(minutes=15)
MAX_OPEN_LINKS = 3
SESSION_TTL = timedelta(hours=12)


class AuthError(Exception):
    """Base class for authentication failures."""


class LinkNotUsable(AuthError):
    """The link is unknown, expired, or already used."""


@dataclass(frozen=True, slots=True)
class AuthContext:
    tenant_id: uuid.UUID
    user_id: uuid.UUID
    role: str


@dataclass(frozen=True, slots=True)
class LoginResult:
    session_token: str
    context: AuthContext


def _now(now: datetime | None) -> datetime:
    return now or datetime.now(UTC)


def normalise_email(email: str) -> str:
    """Addresses are matched case-insensitively, so they are stored that way too."""
    return email.strip().lower()


async def request_magic_link(
    engine: AsyncEngine,
    *,
    tenant_id: uuid.UUID,
    email: str,
    sender: EmailSender,
    now: datetime | None = None,
) -> None:
    """Send a link if the address belongs to this tenant, and say nothing either way."""
    moment = _now(now)
    async with tenant_session(engine, tenant_id) as session:
        user = await session.scalar(
            select(User).where(func.lower(User.email) == normalise_email(email))
        )
        if user is None:
            return

        # Cap outstanding links: an old email must not stay usable for ever.
        open_links = (
            await session.scalars(
                select(AuthMagicLink)
                .where(AuthMagicLink.user_id == user.id, AuthMagicLink.consumed_at.is_(None))
                .order_by(AuthMagicLink.created_at)
            )
        ).all()
        for stale in open_links[: max(0, len(open_links) - MAX_OPEN_LINKS + 1)]:
            await session.execute(
                update(AuthMagicLink).where(AuthMagicLink.id == stale.id).values(consumed_at=moment)
            )

        token = new_token(tenant_id)
        session.add(
            AuthMagicLink(
                tenant_id=tenant_id,
                user_id=user.id,
                token_hash=hash_token(token),
                expires_at=moment + MAGIC_LINK_TTL,
            )
        )
        await session.flush()
    await sender.send_magic_link(to=email, token=token)


async def login_with_magic_link(
    engine: AsyncEngine, token: str, *, now: datetime | None = None
) -> LoginResult:
    moment = _now(now)
    tenant_id = tenant_from_token(token)

    async with tenant_session(engine, tenant_id) as session:
        link = await session.scalar(
            select(AuthMagicLink).where(AuthMagicLink.token_hash == hash_token(token))
        )
        if link is None:
            raise LinkNotUsable("this link cannot be used")

        # One statement both checks and claims: unused, unexpired, and marked used.
        # Two concurrent consumptions cannot both see a rowcount of 1.
        claimed = await session.execute(
            update(AuthMagicLink)
            .where(
                AuthMagicLink.id == link.id,
                AuthMagicLink.consumed_at.is_(None),
                AuthMagicLink.expires_at > moment,
            )
            .values(consumed_at=moment)
        )
        if cast(CursorResult[Any], claimed).rowcount != 1:
            raise LinkNotUsable("this link cannot be used")

        role = await session.scalar(
            select(Membership.role).where(
                Membership.tenant_id == tenant_id, Membership.user_id == link.user_id
            )
        )
        if role is None:
            raise LinkNotUsable("this link cannot be used")

        # Any other open link for this user stops working once one is used.
        await session.execute(
            update(AuthMagicLink)
            .where(
                AuthMagicLink.user_id == link.user_id,
                AuthMagicLink.id != link.id,
                AuthMagicLink.consumed_at.is_(None),
            )
            .values(consumed_at=moment)
        )

        session_token = new_token(tenant_id)
        session.add(
            AuthSession(
                tenant_id=tenant_id,
                user_id=link.user_id,
                token_hash=hash_token(session_token),
                expires_at=moment + SESSION_TTL,
            )
        )
        await session.flush()

    return LoginResult(
        session_token=session_token,
        context=AuthContext(tenant_id=tenant_id, user_id=link.user_id, role=role),
    )


async def resolve_session(
    engine: AsyncEngine, token: str, *, now: datetime | None = None
) -> AuthContext | None:
    moment = _now(now)
    try:
        tenant_id = tenant_from_token(token)
    except Exception:
        return None

    async with tenant_session(engine, tenant_id) as session:
        stored = await session.scalar(
            select(AuthSession).where(AuthSession.token_hash == hash_token(token))
        )
        if stored is None or stored.revoked_at is not None or stored.expires_at <= moment:
            return None
        role = await session.scalar(
            select(Membership.role).where(
                Membership.tenant_id == tenant_id, Membership.user_id == stored.user_id
            )
        )
        if role is None:
            return None
        return AuthContext(tenant_id=tenant_id, user_id=stored.user_id, role=role)


async def revoke_session(engine: AsyncEngine, token: str, *, now: datetime | None = None) -> None:
    moment = _now(now)
    try:
        tenant_id = tenant_from_token(token)
    except InvalidToken:
        return  # revoking something that is not a token is a no-op, not an error
    async with tenant_session(engine, tenant_id) as session:
        await session.execute(
            update(AuthSession)
            .where(AuthSession.token_hash == hash_token(token), AuthSession.revoked_at.is_(None))
            .values(revoked_at=moment)
        )
