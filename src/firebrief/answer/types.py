"""The result of checking an answer against its evidence."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from enum import StrEnum


class Status(StrEnum):
    VERIFIED = "verified"
    MISSING_SPAN = "missing_span"
    QUOTE_TOO_SHORT = "quote_too_short"
    UNKNOWN_MARKER = "unknown_marker"
    UNATTRIBUTED = "unattributed"
    UNCITED = "uncited"
    UNSUPPORTED = "unsupported"
    JUDGE_ERROR = "judge_error"


class Verdict(StrEnum):
    VERIFIED = "verified"
    WITHHELD = "withheld"


@dataclass(frozen=True, slots=True)
class ClaimCheck:
    marker: int | None
    chunk_id: uuid.UUID | None
    status: Status
    quote: str = ""
    section_id: uuid.UUID | None = None
    version_id: uuid.UUID | None = None
    char_start: int | None = None
    char_end: int | None = None


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
    judge_model: str
    judge_prompt_version: str

    @property
    def may_show(self) -> bool:
        return self.verdict is Verdict.VERIFIED
