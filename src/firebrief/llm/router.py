"""Retries, backoff and failover across providers.

The router is the only place that knows about more than one provider. It retries
retryable failures on the same provider, honours `Retry-After`, and then fails
over to the next route. Non-retryable failures skip straight to the next route,
because repeating a request that was rejected for its content wastes money.
"""

from __future__ import annotations

import asyncio
import random
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, field

from firebrief.llm.base import Provider
from firebrief.llm.errors import AllProvidersFailed, LLMError
from firebrief.llm.types import LLMRequest, LLMResponse

Sleep = Callable[[float], Awaitable[None]]


@dataclass(frozen=True, slots=True)
class Route:
    provider: Provider
    model_map: Mapping[str, str] = field(default_factory=dict)

    def resolve(self, model: str) -> str:
        return self.model_map.get(model, model)


@dataclass
class Router:
    routes: Sequence[Route]
    max_attempts: int = 3
    base_delay_s: float = 0.5
    max_delay_s: float = 8.0
    sleep: Sleep = asyncio.sleep
    rng: random.Random = field(default_factory=random.Random)
    delays: list[float] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.routes:
            raise ValueError("a router needs at least one route")
        if self.max_attempts < 1:
            raise ValueError("max_attempts must be at least 1")
        if self.base_delay_s <= 0 or self.max_delay_s < self.base_delay_s:
            raise ValueError("invalid delay configuration")

    async def complete(self, request: LLMRequest) -> LLMResponse:
        last_error: LLMError | None = None
        for route in self.routes:
            attempt_request = request.with_model(route.resolve(request.model))
            for attempt in range(self.max_attempts):
                try:
                    return await route.provider.complete(attempt_request)
                except LLMError as exc:
                    last_error = exc
                    if not exc.retryable or attempt == self.max_attempts - 1:
                        break
                    delay = self._delay(attempt, exc)
                    self.delays.append(delay)
                    await self.sleep(delay)
        raise AllProvidersFailed(
            f"every route failed: {len(self.routes)} provider(s), "
            f"{self.max_attempts} attempt(s) each",
            last_error,
        )

    def _delay(self, attempt: int, error: LLMError) -> float:
        if error.retry_after_s is not None:
            return min(error.retry_after_s, self.max_delay_s)
        backoff = self.base_delay_s * (2**attempt)
        jitter = 0.5 + self.rng.random() * 0.5
        return min(backoff * jitter, self.max_delay_s)
