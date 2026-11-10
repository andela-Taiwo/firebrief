"""A scripted provider for tests and offline evaluation runs.

No API keys, no network, no flakiness. This is the fake at the network boundary
that keeps the suite deterministic.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from firebrief.llm.errors import LLMError
from firebrief.llm.types import LLMRequest, LLMResponse, Usage


@dataclass
class FakeProvider:
    name: str = "fake"
    text: str = "A scripted answer."
    usage: Usage = field(default_factory=lambda: Usage(10, 5))
    model: str = "fake-1"
    finish_reason: str | None = "stop"
    failures: tuple[LLMError | None, ...] = ()
    calls: list[LLMRequest] = field(default_factory=list)

    async def complete(self, request: LLMRequest) -> LLMResponse:
        self.calls.append(request)
        index = len(self.calls) - 1
        failure = self.failures[index] if index < len(self.failures) else None
        if failure is not None:
            raise failure
        return LLMResponse(
            text=self.text,
            usage=self.usage,
            model=self.model,
            provider=self.name,
            latency_ms=0,
            finish_reason=self.finish_reason,
        )
