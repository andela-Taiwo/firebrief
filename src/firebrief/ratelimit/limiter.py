"""Rate limiting.

Three limits, because they fail in different ways: a single address can be bombed, a
single IP can rotate addresses, and one user can spend the whole budget on answers.

Keys are hashed, so the store holds no email addresses, IP addresses or user ids.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Protocol


def key_for(scope: str, value: str) -> str:
    """A key that reveals nothing about the value it counts."""
    digest = hashlib.sha256(value.strip().lower().encode("utf-8")).hexdigest()
    return f"rl:{scope}:{digest}"


@dataclass(frozen=True, slots=True)
class Decision:
    allowed: bool
    remaining: int
    retry_after_seconds: int = 0


@dataclass(frozen=True, slots=True)
class Limit:
    max_events: int
    window_seconds: int

    def __post_init__(self) -> None:
        if self.max_events <= 0:
            raise ValueError("max_events must be positive")
        if self.window_seconds <= 0:
            raise ValueError("window_seconds must be positive")


class Limiter(Protocol):
    async def check(self, key: str, limit: Limit) -> Decision: ...
