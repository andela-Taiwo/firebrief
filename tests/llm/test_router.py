from __future__ import annotations

import random

import pytest

from firebrief.llm.errors import (
    AllProvidersFailed,
    ProviderClientError,
    ProviderRateLimited,
    ProviderServerError,
)
from firebrief.llm.fake import FakeProvider
from firebrief.llm.router import Route, Router
from firebrief.llm.types import LLMRequest, Message, Role


def request_for() -> LLMRequest:
    return LLMRequest(model="logical", messages=(Message(Role.USER, "Hi"),), max_tokens=32)


class Sleeper:
    def __init__(self) -> None:
        self.delays: list[float] = []

    async def __call__(self, delay: float) -> None:
        self.delays.append(delay)


def router_for(*providers: FakeProvider, max_attempts: int = 3) -> tuple[Router, Sleeper]:
    sleeper = Sleeper()
    router = Router(
        routes=[Route(provider=provider) for provider in providers],
        max_attempts=max_attempts,
        sleep=sleeper,
        rng=random.Random(0),
    )
    return router, sleeper


async def test_retries_the_same_provider_then_succeeds() -> None:
    provider = FakeProvider(failures=(ProviderServerError("boom"), None))
    router, sleeper = router_for(provider)

    response = await router.complete(request_for())

    assert response.provider == "fake"
    assert len(provider.calls) == 2
    assert len(sleeper.delays) == 1
    assert 0.25 <= sleeper.delays[0] <= 0.5


async def test_honours_retry_after() -> None:
    provider = FakeProvider(failures=(ProviderRateLimited("slow down", retry_after_s=2.0), None))
    router, sleeper = router_for(provider)

    await router.complete(request_for())

    assert sleeper.delays == [2.0]


async def test_fails_over_to_the_next_provider() -> None:
    primary = FakeProvider(name="primary", failures=(ProviderServerError("down"),) * 3)
    secondary = FakeProvider(name="secondary")
    router, _ = router_for(primary, secondary, max_attempts=3)

    response = await router.complete(request_for())

    assert response.provider == "secondary"
    assert len(primary.calls) == 3
    assert len(secondary.calls) == 1


async def test_non_retryable_error_skips_to_the_next_provider() -> None:
    primary = FakeProvider(name="primary", failures=(ProviderClientError("bad", status=400),))
    secondary = FakeProvider(name="secondary")
    router, sleeper = router_for(primary, secondary)

    response = await router.complete(request_for())

    assert response.provider == "secondary"
    assert len(primary.calls) == 1
    assert sleeper.delays == []


async def test_gives_up_after_every_route() -> None:
    primary = FakeProvider(name="primary", failures=(ProviderServerError("down"),) * 3)
    secondary = FakeProvider(name="secondary", failures=(ProviderServerError("down"),) * 3)
    router, _ = router_for(primary, secondary, max_attempts=3)

    with pytest.raises(AllProvidersFailed) as raised:
        await router.complete(request_for())

    assert raised.value.last_error is not None
    assert raised.value.last_error.status is None
    assert len(secondary.calls) == 3


async def test_model_is_mapped_per_route() -> None:
    provider = FakeProvider()
    router = Router(
        routes=[Route(provider=provider, model_map={"logical": "provider-id"})],
        sleep=Sleeper(),
    )

    await router.complete(request_for())

    assert provider.calls[0].model == "provider-id"


def test_router_rejects_empty_configuration() -> None:
    with pytest.raises(ValueError):
        Router(routes=[])
    with pytest.raises(ValueError):
        Router(routes=[Route(provider=FakeProvider())], max_attempts=0)
