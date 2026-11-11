"""A sliding-window limiter backed by a sorted set per key.

Not atomic: two concurrent requests can both observe a count below the limit and both be
allowed. For abuse protection that overshoot is acceptable and is recorded in the docs;
making it exact needs a Lua script, which is worth doing only if the overshoot matters.
"""

from __future__ import annotations

import time
import uuid
from collections.abc import Awaitable
from dataclasses import dataclass
from typing import Any, Protocol

from firebrief.ratelimit.limiter import Decision, Limit


class RedisClient(Protocol):
    def zremrangebyscore(self, key: str, minimum: float, maximum: float) -> Awaitable[Any]: ...
    def zcard(self, key: str) -> Awaitable[Any]: ...
    def zrange(
        self, key: str, start: int, end: int, *, withscores: bool = False
    ) -> Awaitable[Any]: ...
    def zadd(self, key: str, mapping: dict[str, float]) -> Awaitable[Any]: ...
    def expire(self, key: str, seconds: int) -> Awaitable[Any]: ...


@dataclass
class RedisLimiter:
    client: RedisClient
    clock: Any = time.time

    async def check(self, key: str, limit: Limit) -> Decision:
        now = float(self.clock())
        window_start = now - limit.window_seconds

        await self.client.zremrangebyscore(key, 0, window_start)
        count = int(await self.client.zcard(key))

        if count >= limit.max_events:
            oldest = await self.client.zrange(key, 0, 0, withscores=True)
            first = float(oldest[0][1]) if oldest else now
            retry = int(first + limit.window_seconds - now) + 1
            return Decision(allowed=False, remaining=0, retry_after_seconds=max(retry, 1))

        await self.client.zadd(key, {uuid.uuid4().hex: now})
        await self.client.expire(key, limit.window_seconds)
        return Decision(allowed=True, remaining=limit.max_events - count - 1)
