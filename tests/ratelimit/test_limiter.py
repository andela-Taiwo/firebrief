from __future__ import annotations

from typing import cast

import pytest

from firebrief.ratelimit import InMemoryLimiter, Limit, RedisClient, RedisLimiter, key_for


def test_a_key_changes_with_the_secret() -> None:
    """A plain hash could be reversed by hashing a guess; an HMAC cannot."""
    first = key_for("link:email", "ada@alpha.test", "secret-one")
    second = key_for("link:email", "ada@alpha.test", "secret-two")

    assert first != second
    assert "ada" not in first


def test_the_same_value_normalised_gives_the_same_key() -> None:
    assert key_for("link:email", " A@Alpha.Test ", "s") == key_for(
        "link:email", "a@alpha.test", "s"
    )


async def test_the_memory_limiter_allows_up_to_the_limit() -> None:
    now = [0.0]
    limiter = InMemoryLimiter(clock=lambda: now[0])
    limit = Limit(max_events=2, window_seconds=60)

    first = await limiter.check("k", limit)
    second = await limiter.check("k", limit)
    third = await limiter.check("k", limit)

    assert first.allowed
    assert second.allowed
    assert not third.allowed
    assert third.retry_after_seconds >= 1


async def test_the_window_slides() -> None:
    now = [0.0]
    limiter = InMemoryLimiter(clock=lambda: now[0])
    limit = Limit(max_events=1, window_seconds=60)

    assert (await limiter.check("k", limit)).allowed
    now[0] = 30.0
    assert not (await limiter.check("k", limit)).allowed
    now[0] = 61.0
    assert (await limiter.check("k", limit)).allowed


async def test_keys_are_independent() -> None:
    limiter = InMemoryLimiter(clock=lambda: 0.0)
    limit = Limit(max_events=1, window_seconds=60)

    assert (await limiter.check("a", limit)).allowed
    assert (await limiter.check("b", limit)).allowed


@pytest.mark.parametrize(
    ("events", "window"),
    [(0, 60), (-1, 60), (1, 0), (1, -5)],
)
def test_a_nonsense_limit_is_refused(events: int, window: int) -> None:
    with pytest.raises(ValueError):
        Limit(max_events=events, window_seconds=window)


async def test_the_redis_limiter_counts_in_a_sorted_set() -> None:
    import fakeredis

    client = fakeredis.aioredis.FakeRedis()
    now = [1000.0]
    limiter = RedisLimiter(client=cast(RedisClient, client), clock=lambda: now[0])
    limit = Limit(max_events=2, window_seconds=60)

    assert (await limiter.check("k", limit)).allowed
    assert (await limiter.check("k", limit)).allowed
    refused = await limiter.check("k", limit)
    assert not refused.allowed

    now[0] = 1061.0
    assert (await limiter.check("k", limit)).allowed


async def test_the_redis_limiter_is_exact_under_parallel_requests() -> None:
    """Ten concurrent checks with a limit of two: at most two may be allowed."""
    import asyncio

    import fakeredis

    client = fakeredis.aioredis.FakeRedis()
    limiter = RedisLimiter(client=cast(RedisClient, client), clock=lambda: 1000.0)
    limit = Limit(max_events=2, window_seconds=60)

    decisions = await asyncio.gather(*[limiter.check("k", limit) for _ in range(10)])

    assert sum(1 for decision in decisions if decision.allowed) <= 2
