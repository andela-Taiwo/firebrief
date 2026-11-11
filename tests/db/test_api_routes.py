from __future__ import annotations

import logging
from datetime import UTC, date, datetime

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from firebrief.answer import FixedJudge
from firebrief.api import Settings, create_app
from firebrief.auth import RecordingEmailSender
from firebrief.budget import (
    BudgetService,
    InMemoryLedger,
    Limit,
    LimitBook,
    ModelPrice,
    Period,
    PriceTable,
    ScopeType,
)
from firebrief.ingest import SourceDocument, ingest
from firebrief.ingest.embed import BagOfWordsEmbedder
from firebrief.ingest.store_embed import embed_version
from firebrief.llm import FakeProvider, Provider
from firebrief.ratelimit import InMemoryLimiter, Limiter
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


MODEL = "claude-sonnet-4-5-20250929"


def make_budget(limit: int = 100_000_000) -> BudgetService:
    return BudgetService(
        ledger=InMemoryLedger(),
        limits=LimitBook([Limit(ScopeType.USER, USER_A, Period.DAILY, limit)]),
        prices=PriceTable("GBP", {MODEL: ModelPrice(3_000_000, 15_000_000)}),
    )


@pytest.fixture
def app(app_engine: AsyncEngine):
    return create_app(
        engine=app_engine,
        embedder=BagOfWordsEmbedder(),
        provider=FakeProvider(text=f'The limit is thirty metres: "{DEAD_ENDS}" [1]'),
        judge=FixedJudge(),
        budget=make_budget(),
        limiter=InMemoryLimiter(),
        sender=RecordingEmailSender(),
        settings=Settings(cookie_secure=False, allowed_origins=("http://test",)),
    )


@pytest.fixture
async def client(app):  # type: ignore[no-untyped-def]
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        headers={"origin": "http://test"},
    ) as http:
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


async def test_asking_for_a_link_does_not_reveal_whether_the_address_exists(
    app, client, seeded
) -> None:  # type: ignore[no-untyped-def]
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
    caplog.set_level(logging.DEBUG)

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


def make_app(
    engine: AsyncEngine,
    *,
    provider: Provider | None = None,
    budget: BudgetService | None = None,
    limiter: Limiter | None = None,
    settings: Settings | None = None,
) -> FastAPI:
    return create_app(
        engine=engine,
        embedder=BagOfWordsEmbedder(),
        provider=provider or FakeProvider(text=f'The limit is thirty metres: "{DEAD_ENDS}" [1]'),
        judge=FixedJudge(),
        budget=budget or make_budget(),
        limiter=limiter or InMemoryLimiter(),
        sender=RecordingEmailSender(),
        settings=settings or Settings(cookie_secure=False),
    )


async def test_a_same_origin_post_passes_with_no_extra_configuration(app_engine) -> None:  # type: ignore[no-untyped-def]
    """The request's own origin is always allowed; empty settings do not mean "nothing"."""
    app = make_app(app_engine)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test", headers={"origin": "http://test"}
    ) as http:
        response = await http.post(
            "/v1/auth/magic-link", json={"tenant_id": TENANT_A, "email": "a@alpha.test"}
        )

    assert response.status_code == 202


async def test_a_post_without_origin_or_referer_is_refused(app_engine, seeded) -> None:  # type: ignore[no-untyped-def]
    app = make_app(app_engine)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
        response = await http.post(
            "/v1/auth/magic-link", json={"tenant_id": TENANT_A, "email": "a@alpha.test"}
        )

    assert response.status_code == 403


async def test_the_client_cannot_choose_the_request_id(client) -> None:  # type: ignore[no-untyped-def]
    supplied = "x" * 100

    response = await client.post(
        "/v1/auth/magic-link",
        json={"tenant_id": TENANT_A, "email": "a@alpha.test"},
        headers={"x-request-id": supplied},
    )

    assert response.headers["x-request-id"] != supplied
    assert len(response.headers["x-request-id"]) == 32


async def test_reusing_a_client_request_id_does_not_reuse_the_server_id(client) -> None:  # type: ignore[no-untyped-def]
    payload = {"tenant_id": TENANT_A, "email": "a@alpha.test"}

    first = await client.post("/v1/auth/magic-link", json=payload, headers={"x-request-id": "abc"})
    second = await client.post("/v1/auth/magic-link", json=payload, headers={"x-request-id": "abc"})

    assert first.headers["x-request-id"] != second.headers["x-request-id"]


async def test_a_garbage_token_is_a_bad_request(client, seeded) -> None:  # type: ignore[no-untyped-def]
    response = await client.post("/v1/auth/verify", json={"token": "not-a-real-token"})

    assert response.status_code == 400


async def test_the_cookie_is_secure_when_configured(app_engine, seeded) -> None:  # type: ignore[no-untyped-def]
    app = make_app(app_engine, settings=Settings(cookie_secure=True))
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test", headers={"origin": "http://test"}
    ) as http:
        await http.post(
            "/v1/auth/magic-link", json={"tenant_id": TENANT_A, "email": "a@alpha.test"}
        )
        token = app.state.sender.sent[-1][1]
        response = await http.post("/v1/auth/verify", json={"token": token})

    cookie = response.headers["set-cookie"]
    assert "Secure" in cookie
    assert cookie.startswith("__Host-")


async def test_a_refusal_is_a_200_with_a_reason_and_details(
    app_engine, seeded, owner_engine
) -> None:  # type: ignore[no-untyped-def]
    await _corpus(owner_engine)
    app = make_app(
        app_engine,
        provider=FakeProvider(
            text='Dead ends are ten metres: "Dead ends must be limited to ten metres." [1]'
        ),
    )
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test", headers={"origin": "http://test"}
    ) as http:
        await http.post(
            "/v1/auth/magic-link", json={"tenant_id": TENANT_A, "email": "a@alpha.test"}
        )
        await http.post("/v1/auth/verify", json={"token": app.state.sender.sent[-1][1]})
        response = await http.post("/v1/answers", json={"question": "How long can a dead end be?"})

    assert response.status_code == 200
    body = response.json()
    assert body["answer"] is None
    assert body["refusal"]["reason"] == "unverified"
    assert body["refusal"]["message"]
    assert body["refusal"]["details"]


async def test_exceeding_the_budget_is_refused_over_http(app_engine, seeded, owner_engine) -> None:  # type: ignore[no-untyped-def]
    await _corpus(owner_engine)
    app = make_app(app_engine, budget=make_budget(limit=1))
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test", headers={"origin": "http://test"}
    ) as http:
        await http.post(
            "/v1/auth/magic-link", json={"tenant_id": TENANT_A, "email": "a@alpha.test"}
        )
        await http.post("/v1/auth/verify", json={"token": app.state.sender.sent[-1][1]})
        response = await http.post("/v1/answers", json={"question": "How long can a dead end be?"})

    assert response.status_code == 429
    assert response.json()["refusal"]["reason"] == "budget_exhausted"


async def test_cited_sources_carry_their_verified_quotes(app, client, seeded, owner_engine) -> None:  # type: ignore[no-untyped-def]
    await _corpus(owner_engine)
    await _login(app, client)

    body = (
        await client.post("/v1/answers", json={"question": "How long can a dead end be?"})
    ).json()

    cited = [source for source in body["sources"] if source["cited"]]
    assert cited, "the answer cites a source"
    assert cited[0]["quotes"][0]["text"] == DEAD_ENDS
    assert isinstance(cited[0]["quotes"][0]["start"], int)


async def test_readiness_checks_the_database_and_the_role(app, client) -> None:  # type: ignore[no-untyped-def]
    response = await client.get("/ready")

    assert response.status_code == 200


def test_a_judge_is_required(app_engine) -> None:  # type: ignore[no-untyped-def]
    """No default: a deployment that forgets the judge must not start checking only existence."""
    with pytest.raises(TypeError, match="judge"):
        create_app(  # type: ignore[call-arg]
            engine=app_engine,
            embedder=BagOfWordsEmbedder(),
            provider=FakeProvider(),
            budget=make_budget(),
            limiter=InMemoryLimiter(),
            sender=RecordingEmailSender(),
        )


async def test_startup_refuses_a_role_that_can_bypass_rls(owner_engine) -> None:  # type: ignore[no-untyped-def]
    """The owner is a superuser here; a deployment must not start in that state."""
    from asgi_lifespan import LifespanManager

    app = make_app(owner_engine)

    with pytest.raises(Exception, match="superuser"):
        async with LifespanManager(app):
            pass


async def test_a_lookalike_referer_is_refused(app_engine, seeded) -> None:  # type: ignore[no-untyped-def]
    app = make_app(app_engine)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
        response = await http.post(
            "/v1/auth/magic-link",
            json={"tenant_id": TENANT_A, "email": "a@alpha.test"},
            headers={"referer": "http://test.evil.example/login"},
        )

    assert response.status_code == 403


async def test_a_form_encoded_post_is_refused(app_engine, seeded) -> None:  # type: ignore[no-untyped-def]
    app = make_app(app_engine)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test", headers={"origin": "http://test"}
    ) as http:
        response = await http.post(
            "/v1/auth/magic-link", data={"tenant_id": TENANT_A, "email": "a@alpha.test"}
        )

    assert response.status_code == 403
    assert response.json()["detail"] == "content type must be application/json"


async def test_a_middleware_refusal_carries_the_security_headers(app_engine, seeded) -> None:  # type: ignore[no-untyped-def]
    app = make_app(app_engine)
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        headers={"origin": "http://evil.test"},
    ) as http:
        response = await http.post(
            "/v1/auth/magic-link", json={"tenant_id": TENANT_A, "email": "a@alpha.test"}
        )

    assert response.status_code == 403
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-request-id"]


async def test_a_refusal_exposes_no_cited_sources_or_quotes(
    app_engine, seeded, owner_engine
) -> None:  # type: ignore[no-untyped-def]
    await _corpus(owner_engine)
    app = make_app(
        app_engine,
        provider=FakeProvider(
            text='Dead ends are ten metres: "Dead ends must be limited to ten metres." [1]'
        ),
    )
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test", headers={"origin": "http://test"}
    ) as http:
        await http.post(
            "/v1/auth/magic-link", json={"tenant_id": TENANT_A, "email": "a@alpha.test"}
        )
        await http.post("/v1/auth/verify", json={"token": app.state.sender.sent[-1][1]})
        body = (
            await http.post("/v1/answers", json={"question": "How long can a dead end be?"})
        ).json()

    assert body["answer"] is None
    assert body["sources"], "the evidence considered is still listed"
    assert not any(source["cited"] for source in body["sources"])
    assert all(source["quotes"] == [] for source in body["sources"])


async def test_a_partly_verified_refusal_still_exposes_no_quotes(
    app_engine, seeded, owner_engine
) -> None:  # type: ignore[no-untyped-def]
    """One good quote and one bad claim: the answer is withheld, so nothing is highlighted."""
    await _corpus(owner_engine)
    app = make_app(
        app_engine,
        provider=FakeProvider(
            text=(
                f'Dead ends are capped: "{DEAD_ENDS}" [1] '
                'and doors are ten metres: "Doors must be ten metres wide." [1]'
            )
        ),
    )
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test", headers={"origin": "http://test"}
    ) as http:
        await http.post(
            "/v1/auth/magic-link", json={"tenant_id": TENANT_A, "email": "a@alpha.test"}
        )
        await http.post("/v1/auth/verify", json={"token": app.state.sender.sent[-1][1]})
        body = (
            await http.post("/v1/answers", json={"question": "How long can a dead end be?"})
        ).json()

    assert body["answer"] is None
    assert not any(source["cited"] for source in body["sources"])
    assert all(source["quotes"] == [] for source in body["sources"])


async def test_too_many_link_requests_for_one_address_is_refused(app_engine, seeded) -> None:  # type: ignore[no-untyped-def]
    app = make_app(app_engine, settings=Settings(link_email_limit=2, link_ip_limit=100))
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test", headers={"origin": "http://test"}
    ) as http:
        payload = {"tenant_id": TENANT_A, "email": "a@alpha.test"}
        assert (await http.post("/v1/auth/magic-link", json=payload)).status_code == 202
        assert (await http.post("/v1/auth/magic-link", json=payload)).status_code == 202
        refused = await http.post("/v1/auth/magic-link", json=payload)

    assert refused.status_code == 429
    assert int(refused.headers["retry-after"]) >= 1
    assert refused.json()["detail"] == "too many requests"


async def test_too_many_link_requests_from_one_ip_is_refused(app_engine, seeded) -> None:  # type: ignore[no-untyped-def]
    app = make_app(app_engine, settings=Settings(link_email_limit=100, link_ip_limit=2))
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test", headers={"origin": "http://test"}
    ) as http:
        for index in range(2):
            payload = {"tenant_id": TENANT_A, "email": f"user{index}@alpha.test"}
            assert (await http.post("/v1/auth/magic-link", json=payload)).status_code == 202
        refused = await http.post(
            "/v1/auth/magic-link", json={"tenant_id": TENANT_A, "email": "third@alpha.test"}
        )

    assert refused.status_code == 429


async def test_answers_are_limited_per_user(app_engine, seeded, owner_engine) -> None:  # type: ignore[no-untyped-def]
    await _corpus(owner_engine)
    app = make_app(app_engine, settings=Settings(answer_user_limit=1, cookie_secure=False))
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test", headers={"origin": "http://test"}
    ) as http:
        await http.post(
            "/v1/auth/magic-link", json={"tenant_id": TENANT_A, "email": "a@alpha.test"}
        )
        await http.post("/v1/auth/verify", json={"token": app.state.sender.sent[-1][1]})
        first = await http.post("/v1/answers", json={"question": "How long can a dead end be?"})
        second = await http.post("/v1/answers", json={"question": "How long can a dead end be?"})

    assert first.status_code == 200
    assert second.status_code == 429


async def test_an_unavailable_limiter_refuses_rather_than_allowing(app_engine, seeded) -> None:  # type: ignore[no-untyped-def]
    class Broken:
        async def check(self, key, limit):  # type: ignore[no-untyped-def]
            raise RuntimeError("redis down")

    app = make_app(app_engine, limiter=Broken())
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test", headers={"origin": "http://test"}
    ) as http:
        response = await http.post(
            "/v1/auth/magic-link", json={"tenant_id": TENANT_A, "email": "a@alpha.test"}
        )

    assert response.status_code == 503


async def test_a_spoofed_forwarded_for_does_not_choose_the_bucket(app_engine, seeded) -> None:  # type: ignore[no-untyped-def]
    """Only the rightmost hop is trusted; the leftmost is whatever the caller typed."""
    app = make_app(
        app_engine,
        settings=Settings(
            link_ip_limit=1, link_email_limit=100, trusted_proxy_hops=1, cookie_secure=False
        ),
    )
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test", headers={"origin": "http://test"}
    ) as http:
        payload = {"tenant_id": TENANT_A, "email": "a@alpha.test"}
        first = await http.post(
            "/v1/auth/magic-link", json=payload, headers={"x-forwarded-for": "1.1.1.1, 9.9.9.9"}
        )
        spoofed = await http.post(
            "/v1/auth/magic-link", json=payload, headers={"x-forwarded-for": "2.2.2.2, 9.9.9.9"}
        )

    assert first.status_code == 202
    assert spoofed.status_code == 429, "rotating the client-supplied entry must not help"


async def test_a_refused_ip_does_not_consume_the_address_quota(app_engine, seeded) -> None:  # type: ignore[no-untyped-def]
    app = make_app(
        app_engine,
        settings=Settings(
            link_ip_limit=1, link_email_limit=2, trusted_proxy_hops=1, cookie_secure=False
        ),
    )
    payload = {"tenant_id": TENANT_A, "email": "a@alpha.test"}

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test", headers={"origin": "http://test"}
    ) as http:
        first = await http.post(
            "/v1/auth/magic-link", json=payload, headers={"x-forwarded-for": "1.1.1.1"}
        )
        blocked = await http.post(
            "/v1/auth/magic-link", json=payload, headers={"x-forwarded-for": "1.1.1.1"}
        )
        other_ip = await http.post(
            "/v1/auth/magic-link", json=payload, headers={"x-forwarded-for": "2.2.2.2"}
        )
        exhausted = await http.post(
            "/v1/auth/magic-link", json=payload, headers={"x-forwarded-for": "3.3.3.3"}
        )

    assert first.status_code == 202
    assert blocked.status_code == 429
    assert other_ip.status_code == 202, "the blocked request must not have spent the address quota"
    assert exhausted.status_code == 429


async def test_production_refuses_to_start_without_a_proxy_setup(app_engine) -> None:  # type: ignore[no-untyped-def]
    from asgi_lifespan import LifespanManager

    app = make_app(app_engine, settings=Settings(environment="production", cookie_secure=True))

    with pytest.raises(RuntimeError, match="trusted_proxy_hops"):
        async with LifespanManager(app):
            pass


async def test_allowed_requests_report_the_remaining_budget(app_engine, seeded) -> None:  # type: ignore[no-untyped-def]
    app = make_app(app_engine, settings=Settings(link_email_limit=2, cookie_secure=False))
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test", headers={"origin": "http://test"}
    ) as http:
        response = await http.post(
            "/v1/auth/magic-link", json={"tenant_id": TENANT_A, "email": "a@alpha.test"}
        )

    assert response.headers["ratelimit-limit"] == "2"
    assert response.headers["ratelimit-remaining"] == "1"
    assert int(response.headers["ratelimit-reset"]) > 0


def test_an_unknown_environment_fails_validation() -> None:
    """A typo must fail loudly, not silently disable the production checks."""
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        Settings(environment="prod")  # type: ignore[arg-type]


async def test_ipv6_addresses_in_one_slash_64_share_a_bucket(app_engine, seeded) -> None:  # type: ignore[no-untyped-def]
    app = make_app(
        app_engine,
        settings=Settings(
            link_ip_limit=1, link_email_limit=100, trusted_proxy_hops=1, cookie_secure=False
        ),
    )
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test", headers={"origin": "http://test"}
    ) as http:
        payload = {"tenant_id": TENANT_A, "email": "a@alpha.test"}
        first = await http.post(
            "/v1/auth/magic-link", json=payload, headers={"x-forwarded-for": "2001:db8:0:1::1"}
        )
        same_64 = await http.post(
            "/v1/auth/magic-link", json=payload, headers={"x-forwarded-for": "2001:db8:0:1::2"}
        )
        other_64 = await http.post(
            "/v1/auth/magic-link", json=payload, headers={"x-forwarded-for": "2001:db8:0:2::1"}
        )

    assert first.status_code == 202
    assert same_64.status_code == 429, "one /64 is one user"
    assert other_64.status_code == 202


async def test_a_refusal_carries_the_rate_limit_headers(app_engine, seeded) -> None:  # type: ignore[no-untyped-def]
    app = make_app(app_engine, settings=Settings(link_email_limit=1, cookie_secure=False))
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test", headers={"origin": "http://test"}
    ) as http:
        payload = {"tenant_id": TENANT_A, "email": "a@alpha.test"}
        await http.post("/v1/auth/magic-link", json=payload)
        refused = await http.post("/v1/auth/magic-link", json=payload)

    assert refused.status_code == 429
    assert refused.headers["ratelimit-remaining"] == "0"
    assert int(refused.headers["retry-after"]) >= 1


async def test_the_tighter_of_two_limits_sets_the_headers(app_engine, seeded) -> None:  # type: ignore[no-untyped-def]
    app = make_app(
        app_engine, settings=Settings(link_email_limit=20, link_ip_limit=2, cookie_secure=False)
    )
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test", headers={"origin": "http://test"}
    ) as http:
        response = await http.post(
            "/v1/auth/magic-link", json={"tenant_id": TENANT_A, "email": "a@alpha.test"}
        )

    assert response.headers["ratelimit-limit"] == "2"
    assert response.headers["ratelimit-remaining"] == "1"


async def test_production_requires_a_long_secret(app_engine) -> None:  # type: ignore[no-untyped-def]
    from asgi_lifespan import LifespanManager

    app = make_app(
        app_engine,
        settings=Settings(
            environment="production", trusted_proxy_hops=1, rate_limit_secret="short"
        ),
    )

    with pytest.raises(RuntimeError, match="32 characters"):
        async with LifespanManager(app):
            pass
