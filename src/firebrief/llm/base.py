"""The one interface every model call goes through."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from firebrief.llm.types import LLMRequest, LLMResponse


@runtime_checkable
class Provider(Protocol):
    name: str

    async def complete(self, request: LLMRequest) -> LLMResponse: ...
