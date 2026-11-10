"""Whether a quoted passage actually supports the claim it is attached to.

Existence is checked before this is ever called, so a judge cannot create a citation
that is not in the source. The real model is wired in a later PR; the interface exists
now so the pipeline can be built against it and tested without a network.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


class SupportJudge(Protocol):
    async def supports(self, claim: str, evidence: str) -> bool: ...


@dataclass(frozen=True)
class FixedJudge:
    """For tests and offline runs: accepts or rejects everything, visibly."""

    accepts: bool = True

    async def supports(self, claim: str, evidence: str) -> bool:
        return self.accepts
