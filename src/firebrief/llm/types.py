"""Provider-independent request and response types."""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import StrEnum


class Role(StrEnum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"


@dataclass(frozen=True, slots=True)
class Message:
    role: Role
    content: str


@dataclass(frozen=True, slots=True)
class LLMRequest:
    model: str
    messages: tuple[Message, ...]
    max_tokens: int = 1024
    temperature: float = 0.0
    timeout_s: float = 30.0

    def __post_init__(self) -> None:
        if not self.messages:
            raise ValueError("a request needs at least one message")
        if self.max_tokens <= 0:
            raise ValueError("max_tokens must be positive")
        if not 0.0 <= self.temperature <= 2.0:
            raise ValueError("temperature must be between 0 and 2")

    def with_model(self, model: str) -> LLMRequest:
        return replace(self, model=model)

    def prompt_text(self) -> str:
        return "\n".join(message.content for message in self.messages)


@dataclass(frozen=True, slots=True)
class Usage:
    input_tokens: int
    output_tokens: int

    def __post_init__(self) -> None:
        if self.input_tokens < 0 or self.output_tokens < 0:
            raise ValueError("token counts must not be negative")


@dataclass(frozen=True, slots=True)
class LLMResponse:
    text: str
    usage: Usage
    model: str
    provider: str
    latency_ms: int = 0
    finish_reason: str | None = None
    """Why the provider stopped, when it says: `max_tokens` means truncated."""
