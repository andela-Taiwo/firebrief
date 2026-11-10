"""Remove personal details before a question leaves for a model provider.

This is pattern redaction, not a data-loss-prevention classifier. It covers what people
paste into a fire-safety question — an email, a phone number, a postcode, a national
insurance number, something that looks like a card number. It does not detect names or
free-text addresses, and the documentation says so rather than implying otherwise.

Findings record the kind and the count, never the matched value: a log that stores the
secret is a second copy of the secret.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum


class Kind(StrEnum):
    EMAIL = "email"
    PHONE = "phone"
    POSTCODE = "postcode"
    NATIONAL_INSURANCE = "national_insurance"
    CARD = "card"


PATTERNS: tuple[tuple[Kind, re.Pattern[str]], ...] = (
    (Kind.EMAIL, re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")),
    (
        Kind.NATIONAL_INSURANCE,
        re.compile(r"\b[A-CEGHJ-PR-TW-Z]{2}\s?\d{2}\s?\d{2}\s?\d{2}\s?[A-D]\b"),
    ),
    (Kind.CARD, re.compile(r"\b(?:\d[ -]?){13,19}\b")),
    (Kind.PHONE, re.compile(r"(?:\+44\s?\d{2,4}|\b0\d{2,4})[\s-]?\d{3,4}[\s-]?\d{3,4}\b")),
    (Kind.POSTCODE, re.compile(r"\b[A-Z]{1,2}\d[A-Z\d]?\s?\d[A-Z]{2}\b", re.IGNORECASE)),
)

MASK = "[REDACTED:{kind}]"


@dataclass(frozen=True, slots=True)
class Finding:
    kind: Kind
    count: int


@dataclass(frozen=True, slots=True)
class Redaction:
    text: str
    findings: tuple[Finding, ...]

    @property
    def changed(self) -> bool:
        return bool(self.findings)


def redact(text: str) -> Redaction:
    counts: dict[Kind, int] = {}
    redacted = text
    for kind, pattern in PATTERNS:
        redacted, found = pattern.subn(MASK.format(kind=kind.value), redacted)
        if found:
            counts[kind] = counts.get(kind, 0) + found
    findings = tuple(Finding(kind=kind, count=count) for kind, count in counts.items())
    return Redaction(text=redacted, findings=findings)
