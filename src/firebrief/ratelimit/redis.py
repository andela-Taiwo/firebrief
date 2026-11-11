"""A sliding-window limiter backed by a sorted set per key.

The whole check is one `MULTI` round trip: add the candidate, drop the events that fell out
of the window, count, and refresh the expiry. The count includes the candidate, so a
request that is over the limit is rolled back by removing its own member. That makes the
boundary exact under parallel requests rather than approximate.

The clock is the application's, so two instances with skewed clocks see slightly different
windows. Accepting that keeps the implementation one round trip; fixing it needs a Lua
script that reads Redis `TIME`.
"""

from __future__ import annotations

import time
import uuid
from collections.abc import Awaitable
from dataclasses import dataclass, field
from typing import Any, Protocol

from firebrief.ratelimit.limiter import Decision, Limit


class RedisClient(Protocol):
    def pipeline(self, transaction: bool = True) -> Any: ...
    def zrem(self, key: str, *members: str) -> Awaitable[Any]: ...
    def zrange(
        self, key: str, start: int, end: int, *, withscores: bool = False
    ) -> Awaitable[Any]: ...


@dataclass
class RedisLimiter:
    client: RedisClient
    clock: Any = field(default=time.time)

    async def check(self, key: str, limit: Limit) -> Decision:
        now = float(self.clock())
        window_start = now - limit.window_seconds
        member = uuid.uuid4().hex

        pipeline = self.client.pipeline(transaction=True)
        pipeline.zadd(key, {member: now})
        pipeline.zremrangebyscore(key, 0, window_start)
        pipeline.zcard(key)
        pipeline.expire(key, limit.window_seconds)
        added, _, count, _ = await pipeline.execute()

        if added is None:  # pragma: no cover - defensive: the pipeline always answers
            raise RuntimeError("the limiter pipeline returned nothing")

        if int(count) > limit.max_events:
            await self.client.zrem(key, member)
            oldest = await self.client.zrange(key, 0, 0, withscores=True)
            first = float(oldest[0][1]) if oldest else now
            retry = int(first + limit.window_seconds - now) + 1
            return Decision(
                allowed=False,
                remaining=0,
                limit=limit.max_events,
                retry_after_seconds=max(retry, 1),
            )

        return Decision(
            allowed=True,
            remaining=limit.max_events - int(count),
            limit=limit.max_events,
        )
