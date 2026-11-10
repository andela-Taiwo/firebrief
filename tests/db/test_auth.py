from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime, timedelta

import pytest
import sqlalchemy as sa
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncEngine

from firebrief.auth import (
    LinkNotUsable,
    RecordingEmailSender,
    hash_token,
    login_with_magic_link,
    request_magic_link,
    resolve_session,
    revoke_session,
)
from tests.db.data import TENANT_A, TENANT_B, USER_A, USER_B

NOW = datetime(2026, 11, 10, 12, 0, tzinfo=UTC)


async def _count(engine: AsyncEngine, statement: str, **params: object) -> int:
    async with engine.connect() as connection:
        return int((await connection.execute(sa.text(statement), params)).scalar_one())


async def _request(engine: AsyncEngine, sender: RecordingEmailSender, **kwargs) -> None:  # type: ignore[no-untyped-def]
    await request_magic_link(
        engine,
        tenant_id=uuid.UUID(TENANT_A),
        email="a@alpha.test",
        sender=sender,
        now=NOW,
        **kwargs,
    )


async def test_a_request_stores_a_hash_and_sends_a_token(seeded, app_engine, owner_engine) -> None:
    sender = RecordingEmailSender()

    await _request(app_engine, sender)

    assert len(sender.sent) == 1
    to, token = sender.sent[0]
    assert to == "a@alpha.test"
    async with owner_engine.connect() as connection:
        stored = (
            await connection.execute(
                sa.text("select token_hash from auth_magic_links where token_hash = :h"),
                {"h": hash_token(token)},
            )
        ).scalar_one()
    assert stored == hash_token(token)
    assert token.split(".", 1)[1] not in stored, "the secret must not be recoverable"


async def test_an_unknown_address_stores_nothing_and_sends_nothing(
    seeded, app_engine, owner_engine
) -> None:
    sender = RecordingEmailSender()
    before = await _count(owner_engine, "select count(*) from auth_magic_links")

    await request_magic_link(
        app_engine,
        tenant_id=uuid.UUID(TENANT_A),
        email="nobody@alpha.test",
        sender=sender,
        now=NOW,
    )

    assert sender.sent == []
    assert await _count(owner_engine, "select count(*) from auth_magic_links") == before


async def test_a_valid_link_creates_a_session_with_tenant_and_role(seeded, app_engine) -> None:
    sender = RecordingEmailSender()
    await _request(app_engine, sender)
    _, token = sender.sent[0]

    result = await login_with_magic_link(app_engine, token, now=NOW)

    assert result.context.tenant_id == uuid.UUID(TENANT_A)
    assert result.context.user_id == uuid.UUID(USER_A)
    assert result.context.role == "owner"
    assert (await resolve_session(app_engine, result.session_token, now=NOW)) == result.context


async def test_a_link_cannot_be_used_twice(seeded, app_engine) -> None:
    sender = RecordingEmailSender()
    await _request(app_engine, sender)
    _, token = sender.sent[0]
    await login_with_magic_link(app_engine, token, now=NOW)

    with pytest.raises(LinkNotUsable):
        await login_with_magic_link(app_engine, token, now=NOW)


async def test_an_expired_link_is_refused(seeded, app_engine) -> None:
    sender = RecordingEmailSender()
    await _request(app_engine, sender)
    _, token = sender.sent[0]

    with pytest.raises(LinkNotUsable):
        await login_with_magic_link(app_engine, token, now=NOW + timedelta(minutes=20))


async def test_a_revoked_session_no_longer_resolves(seeded, app_engine) -> None:
    sender = RecordingEmailSender()
    await _request(app_engine, sender)
    _, token = sender.sent[0]
    result = await login_with_magic_link(app_engine, token, now=NOW)

    await revoke_session(app_engine, result.session_token, now=NOW)

    assert await resolve_session(app_engine, result.session_token, now=NOW) is None


async def test_an_expired_session_no_longer_resolves(seeded, app_engine) -> None:
    sender = RecordingEmailSender()
    await _request(app_engine, sender)
    _, token = sender.sent[0]
    result = await login_with_magic_link(app_engine, token, now=NOW)

    later = NOW + timedelta(hours=13)
    assert await resolve_session(app_engine, result.session_token, now=later) is None


@pytest.mark.parametrize("token", ["", "garbage", "018f0000-0000-7000-8000-000000000001.short"])
async def test_a_malformed_session_token_resolves_to_nothing(app_engine, token: str) -> None:
    assert await resolve_session(app_engine, token, now=NOW) is None


async def test_auth_rows_cannot_be_deleted_by_the_runtime_role(seeded, app_engine) -> None:
    """Sessions are revoked, not deleted; the grant enforces it."""
    with pytest.raises(DBAPIError, match="permission denied"):
        async with app_engine.begin() as connection:
            await connection.execute(sa.text("delete from auth_sessions"))


async def test_two_concurrent_logins_with_one_link_produce_one_session(
    seeded, app_engine, owner_engine
) -> None:
    """The claim is one statement: two readers of the same link cannot both win."""
    sender = RecordingEmailSender()
    await _request(app_engine, sender)
    _, token = sender.sent[0]

    before = await _count(owner_engine, "select count(*) from auth_sessions")
    results = await asyncio.gather(
        login_with_magic_link(app_engine, token, now=NOW),
        login_with_magic_link(app_engine, token, now=NOW),
        return_exceptions=True,
    )

    successes = [result for result in results if not isinstance(result, Exception)]
    assert len(successes) == 1
    assert await _count(owner_engine, "select count(*) from auth_sessions") == before + 1


async def test_a_mixed_case_email_can_log_in(seeded, app_engine) -> None:
    sender = RecordingEmailSender()

    await request_magic_link(
        app_engine,
        tenant_id=uuid.UUID(TENANT_A),
        email="A@Alpha.Test",
        sender=sender,
        now=NOW,
    )

    assert len(sender.sent) == 1
    result = await login_with_magic_link(app_engine, sender.sent[0][1], now=NOW)
    assert result.context.user_id == uuid.UUID(USER_A)


async def test_two_users_cannot_differ_only_by_email_case(seeded, owner_engine) -> None:
    """The unique index is on lower(email), so this insert must fail."""
    with pytest.raises(DBAPIError):
        async with owner_engine.begin() as connection:
            await connection.execute(
                sa.text(
                    "insert into users (id, tenant_id, email, name) "
                    "values (gen_random_uuid(), :t, 'A@ALPHA.TEST', 'Duplicate')"
                ),
                {"t": TENANT_A},
            )


async def test_a_row_cannot_point_at_another_tenants_user(seeded, owner_engine) -> None:
    """The composite key carries the tenant, because RI checks bypass RLS."""
    with pytest.raises(DBAPIError):
        async with owner_engine.begin() as connection:
            await connection.execute(
                sa.text(
                    "insert into auth_sessions "
                    "(id, tenant_id, user_id, token_hash, expires_at) "
                    "values (gen_random_uuid(), :t, :u, 'x', now() + interval '1 hour')"
                ),
                {"t": TENANT_A, "u": USER_B},
            )


async def test_a_session_from_another_tenant_cannot_be_reused(seeded, app_engine) -> None:
    """Take a valid session and swap the tenant prefix: it must not resolve."""
    sender = RecordingEmailSender()
    await _request(app_engine, sender)
    _, token = sender.sent[0]
    result = await login_with_magic_link(app_engine, token, now=NOW)
    secret = result.session_token.split(".", 1)[1]

    forged = f"{TENANT_B}.{secret}"

    assert await resolve_session(app_engine, forged, now=NOW) is None


async def test_two_links_issued_means_only_the_newest_works(seeded, app_engine) -> None:
    sender = RecordingEmailSender()
    await _request(app_engine, sender)
    first = sender.sent[0][1]
    await _request(app_engine, sender)
    second = sender.sent[1][1]

    await login_with_magic_link(app_engine, second, now=NOW)

    with pytest.raises(LinkNotUsable):
        await login_with_magic_link(app_engine, first, now=NOW)


async def test_a_session_stops_resolving_when_membership_is_removed(
    seeded, app_engine, owner_engine
) -> None:
    sender = RecordingEmailSender()
    await _request(app_engine, sender)
    result = await login_with_magic_link(app_engine, sender.sent[0][1], now=NOW)

    async with owner_engine.begin() as connection:
        await connection.execute(
            sa.text("delete from memberships where tenant_id = :t"), {"t": TENANT_A}
        )

    assert await resolve_session(app_engine, result.session_token, now=NOW) is None


async def test_the_runtime_role_cannot_extend_an_expiry(seeded, app_engine) -> None:
    with pytest.raises(DBAPIError, match="permission denied"):
        async with app_engine.begin() as connection:
            await connection.execute(
                sa.text("update auth_magic_links set expires_at = now() + interval '10 years'")
            )


async def test_revoking_a_malformed_token_is_a_no_op(app_engine) -> None:
    await revoke_session(app_engine, "not-a-token", now=NOW)
