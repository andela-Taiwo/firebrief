from __future__ import annotations

import logging
from datetime import UTC, date, datetime

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from firebrief.answer import FixedJudge
from firebrief.api import Settings, create_app
from firebrief.auth import RecordingEmailSender
from firebrief.ingest import SourceDocument, ingest
from firebrief.ingest.embed import BagOfWordsEmbedder
from firebrief.ingest.store_embed import embed_version
from firebrief.llm import FakeProvider
from tests.db.data import RETRIEVAL_HTML, TENANT_A, USER_A


async def _corpus(engine: AsyncEngine) -> None:
    embedder = BagOfWordsEmbedder()
    document = SourceDocument(
        slug="api-corpus",
        title="Fire safety in flats",
        source_url="https://www.gov.uk/api-fixture",
        html=RETRIEVAL_HTML,
        licence="OGL-3.0",
        edition="2019",
        fetched_at=datetime.now(UTC),
        effective_from=date(2019, 6, 1),
    )
    async with AsyncSessionLocal(engine) as session, session.begin():
        stored = await ingest(session, document)
    async with AsyncSessionLocal(engine) as session, session.begin():
        await embed_version(session, stored.version_id, embedder)


def AsyncSessionLocal(engine: AsyncEngine) -> AsyncSession:
    return AsyncSession(engine)


DEAD_ENDS = "Dead ends must be limited in length to thirty metres."


@pytest.fixture
def app(app_engine: AsyncEngine):
    return create_app(
        engine=app_engine,
        embedder=BagOfWordsEmbedder(),
        provider=FakeProvider(text=f'The limit is thirty metres: "{DEAD_ENDS}" [1]'),
        judge=FixedJudge(),
        sender=RecordingEmailSender(),
        settings=Settings(cookie_secure=False, allowed_origins=("http://test",)),
    )


@pytest.fixture
async def client(app):  # type: ignore[no-untyped-def]
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
        yield http


async def _login(app, client) -> None:  # type: ignore[no-untyped-def]
    sender = app.state.sender
    await client.post("/v1/auth/magic-link", json={"tenant_id": TENANT_A, "email": "a@alpha.test"})
    token = sender.sent[-1][1]
    response = await client.post("/v1/auth/verify", json={"token": token})
    assert response.status_code == 200


async def test_health_is_public(client) -> None:  # type: ignore[no-untyped-def]
    response = await client.get("/health")

    assert response.status_code == 200


async def test_asking_for_a_link_does_not_reveal_whether_the_address_exists(app, client) -> None:  # type: ignore[no-untyped-def]
    known = await client.post(
        "/v1/auth/magic-link", json={"tenant_id": TENANT_A, "email": "a@alpha.test"}
    )
    unknown = await client.post(
        "/v1/auth/magic-link", json={"tenant_id": TENANT_A, "email": "nobody@alpha.test"}
    )

    assert known.status_code == unknown.status_code == 202
    assert known.json() == unknown.json()
    assert len(app.state.sender.sent) == 1


async def test_verifying_sets_an_httponly_cookie_and_me_returns_the_context(
    app, client, seeded
) -> None:  # type: ignore[no-untyped-def]
    await _login(app, client)

    cookie = client.cookies.get("firebrief_session")
    assert cookie
    me = await client.get("/v1/auth/me")

    assert me.status_code == 200
    assert me.json()["tenant_id"] == TENANT_A
    assert me.json()["user_id"] == USER_A


async def test_an_answer_needs_a_session(client, seeded) -> None:  # type: ignore[no-untyped-def]
    response = await client.post("/v1/answers", json={"question": "How long can a dead end be?"})

    assert response.status_code == 401


async def test_an_answer_is_returned_with_sources_and_a_request_id(
    app, client, seeded, owner_engine
) -> None:  # type: ignore[no-untyped-def]
    await _corpus(owner_engine)
    await _login(app, client)

    response = await client.post("/v1/answers", json={"question": "How long can a dead end be?"})

    assert response.status_code == 200
    body = response.json()
    assert body["answer"].startswith("The limit is thirty metres")
    assert body["refusal"] is None
    assert body["sources"][0]["heading"].endswith("Escape routes")
    assert body["request_id"]
    assert response.headers["x-request-id"] == body["request_id"]


async def test_the_question_never_appears_in_the_log(
    app, client, seeded, owner_engine, caplog
) -> None:  # type: ignore[no-untyped-def]
    await _corpus(owner_engine)
    await _login(app, client)
    caplog.set_level(logging.INFO, logger="firebrief.api")

    await client.post(
        "/v1/answers",
        json={"question": "I am ada@example.com, how long can a dead end be?"},
    )

    assert "ada@example.com" not in caplog.text
    assert "/v1/answers" in caplog.text


async def test_a_cross_origin_post_is_refused(app, client, seeded) -> None:  # type: ignore[no-untyped-def]
    response = await client.post(
        "/v1/auth/magic-link",
        json={"tenant_id": TENANT_A, "email": "a@alpha.test"},
        headers={"origin": "http://evil.test"},
    )

    assert response.status_code == 403


async def test_logging_out_ends_the_session(app, client, seeded) -> None:  # type: ignore[no-untyped-def]
    await _login(app, client)

    assert (await client.post("/v1/auth/logout")).status_code == 204
    assert (await client.get("/v1/auth/me")).status_code == 401


async def test_the_session_cookie_is_locked_down(app, client, seeded) -> None:  # type: ignore[no-untyped-def]
    sender = app.state.sender
    await client.post("/v1/auth/magic-link", json={"tenant_id": TENANT_A, "email": "a@alpha.test"})
    response = await client.post("/v1/auth/verify", json={"token": sender.sent[-1][1]})

    cookie = response.headers["set-cookie"]

    assert "HttpOnly" in cookie
    assert "SameSite=lax" in cookie
    assert "Path=/" in cookie
