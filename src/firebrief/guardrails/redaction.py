"""Remove personal details before a question leaves for a third party.

This is pattern redaction, not a data-loss-prevention classifier. It covers what people
paste into a fire-safety question — an email, a phone number, a postcode, a national
insurance number, something that passes a Luhn check and looks like a card number. It does
not detect names, free-text addresses, or obfuscated forms such as "ada [at] example [dot]
com", and the documentation says so rather than implying otherwise.

Findings record the kind and the count, never the matched value: a log that stores the
secret is a second copy of the secret.

`redact` is a `Redactor`. A stronger detector can be supplied per deployment without the
pipeline changing.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol


class Kind(StrEnum):
    EMAIL = "email"
    PHONE = "phone"
    POSTCODE = "postcode"
    NATIONAL_INSURANCE = "national_insurance"
    CARD = "card"


MASK = "[REDACTED:{kind}]"

PHONE = re.compile(
    r"(?<!\d)"  # never start inside a longer digit run (a card number)
    r"(?:\+44\s?(?:\(0\)\s?)?|\(?0)"  # +44, +44 (0), (0 or 0
    r"\d{2,4}\)?"  # area code, optional closing bracket
    r"[\s.\-]?\d{3,4}[\s.\-]?\d{3,4}\b"
)
EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
NATIONAL_INSURANCE = re.compile(
    r"\b[A-CEGHJ-PR-TW-Z]{2}\s?\d{2}\s?\d{2}\s?\d{2}\s?[A-D]\b", re.IGNORECASE
)
POSTCODE = re.compile(
    r"\b[A-Z]{1,2}\d[A-Z\d]?\s?\d(?!st\b|nd\b|rd\b|th\b)[A-Z]{2}\b",
    re.IGNORECASE,
)
DIGIT_RUN = re.compile(r"\b(?:\d[ -]?){13,19}\b")


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


class Redactor(Protocol):
    def __call__(self, text: str) -> Redaction: ...


def _luhn(digits: str) -> bool:
    total = 0
    for index, character in enumerate(reversed(digits)):
        value = int(character)
        if index % 2 == 1:
            value *= 2
            if value > 9:
                value -= 9
        total += value
    return total % 10 == 0


def _mask_card(match: re.Match[str], counts: dict[Kind, int]) -> str:
    digits = re.sub(r"\D", "", match.group(0))
    if 13 <= len(digits) <= 19 and _luhn(digits):
        counts[Kind.CARD] = counts.get(Kind.CARD, 0) + 1
        return MASK.format(kind=Kind.CARD.value)
    return match.group(0)


def redact(text: str) -> Redaction:
    counts: dict[Kind, int] = {}
    redacted = text

    for kind, pattern in (
        (Kind.EMAIL, EMAIL),
        (Kind.NATIONAL_INSURANCE, NATIONAL_INSURANCE),
    ):
        redacted, found = pattern.subn(MASK.format(kind=kind.value), redacted)
        if found:
            counts[kind] = counts.get(kind, 0) + found

    # Cards before phones: a card group starting with 0 would otherwise match as a
    # phone number and leave the rest of the card behind.
    redacted = DIGIT_RUN.sub(lambda match: _mask_card(match, counts), redacted)

    for kind, pattern in ((Kind.PHONE, PHONE), (Kind.POSTCODE, POSTCODE)):
        redacted, found = pattern.subn(MASK.format(kind=kind.value), redacted)
        if found:
            counts[kind] = counts.get(kind, 0) + found

    findings = tuple(Finding(kind=kind, count=count) for kind, count in counts.items())
    return Redaction(text=redacted, findings=findings)
