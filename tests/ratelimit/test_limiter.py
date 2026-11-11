from __future__ import annotations

import pytest

from firebrief.ratelimit import InMemoryLimiter, Limit, RedisLimiter, key_for


def test_a_key_reveals_nothing_about_its_value() -> None:
    key = key_for("link:email", "Ada@Alpha.Test")

    assert "ada" not in key.lower()
    assert "alpha" not in key.lower()
    assert key.startswith("rl:link:email:")


def test_the_same_value_normalised_gives_the_same_key() -> None:
    assert key_for("link:email", " A@Alpha.Test ") == key_for("link:email", "a@alpha.test")


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
    fakeredis = pytest.importorskip("fakeredis.aioredis")
    client = fakeredis.FakeRedis()
    now = [1000.0]
    limiter = RedisLimiter(client=client, clock=lambda: now[0])
    limit = Limit(max_events=2, window_seconds=60)

    assert (await limiter.check("k", limit)).allowed
    assert (await limiter.check("k", limit)).allowed
    refused = await limiter.check("k", limit)
    assert not refused.allowed

    now[0] = 1061.0
    assert (await limiter.check("k", limit)).allowed
