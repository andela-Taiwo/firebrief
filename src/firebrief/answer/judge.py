"""Whether a quoted passage actually supports the claim it is attached to.

Existence is checked before this is ever called, so a judge cannot create a citation
that is not in the source. The judge sees the claim *without* its quotes, the quote
itself, and a bounded window of source text around it — otherwise it is asked whether
a sentence containing the source's own words is supported by that source, and says yes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


class SupportJudge(Protocol):
    @property
    def model(self) -> str: ...

    @property
    def prompt_version(self) -> str: ...

    async def supports(self, claim: str, quote: str, window: str) -> bool: ...


@dataclass
class FixedJudge:
    """For tests: accepts or rejects everything, and counts its calls."""

    accepts: bool = True
    model: str = "fixed-judge"
    prompt_version: str = "v1"
    calls: list[tuple[str, str, str]] = field(default_factory=list)

    async def supports(self, claim: str, quote: str, window: str) -> bool:
        self.calls.append((claim, quote, window))
        return self.accepts


@dataclass
class FailingJudge:
    """A judge that raises, standing in for a timeout or an unparseable verdict."""

    model: str = "failing-judge"
    prompt_version: str = "v1"

    async def supports(self, claim: str, quote: str, window: str) -> bool:
        raise TimeoutError("judge timed out")
