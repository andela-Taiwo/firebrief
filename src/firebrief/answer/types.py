"""The result of checking an answer against its evidence."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from enum import StrEnum


class Status(StrEnum):
    VERIFIED = "verified"
    MISSING_SPAN = "missing_span"
    UNKNOWN_MARKER = "unknown_marker"
    UNCITED = "uncited"
    UNSUPPORTED = "unsupported"


class Verdict(StrEnum):
    VERIFIED = "verified"
    WITHHELD = "withheld"


@dataclass(frozen=True, slots=True)
class ClaimCheck:
    marker: int | None
    chunk_id: uuid.UUID | None
    status: Status
    quote: str = ""


@dataclass(frozen=True, slots=True)
class ClaimResult:
    text: str
    checks: tuple[ClaimCheck, ...]

    @property
    def verified(self) -> bool:
        return bool(self.checks) and all(check.status is Status.VERIFIED for check in self.checks)


@dataclass(frozen=True, slots=True)
class Verification:
    claims: tuple[ClaimResult, ...]
    verdict: Verdict

    @property
    def may_show(self) -> bool:
        return self.verdict is Verdict.VERIFIED
