"""An in-process limiter, for tests and for a single-process development server."""

from __future__ import annotations

import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field

from firebrief.ratelimit.limiter import Decision, Limit


@dataclass
class InMemoryLimiter:
    clock: Callable[[], float] = time.monotonic
    events: dict[str, deque[float]] = field(default_factory=dict)

    async def check(self, key: str, limit: Limit) -> Decision:
        now = self.clock()
        window_start = now - limit.window_seconds
        seen = self.events.setdefault(key, deque())
        while seen and seen[0] <= window_start:
            seen.popleft()

        if len(seen) >= limit.max_events:
            retry = int(seen[0] + limit.window_seconds - now) + 1
            return Decision(allowed=False, remaining=0, retry_after_seconds=max(retry, 1))

        seen.append(now)
        return Decision(allowed=True, remaining=limit.max_events - len(seen))
