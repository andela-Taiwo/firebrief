"""Refusals that a person can act on.

A refusal is not an error. It is an outcome: the system looked, and either found nothing,
found something that did not answer, or could not verify what the model wrote. Each of
those needs different words, and each should show the evidence that was considered so the
reader can see the search was real.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from firebrief.answer.types import Status, Verification
from firebrief.retrieval.types import Retrieved


class RefusalReason(StrEnum):
    NO_SOURCES = "no_sources"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    UNVERIFIED = "unverified"
    MODEL_UNAVAILABLE = "model_unavailable"
    BUDGET_EXHAUSTED = "budget_exhausted"
    TRUNCATED = "truncated"
    BUDGET_UNAVAILABLE = "budget_unavailable"
    DUPLICATE_REQUEST = "duplicate_request"


MESSAGES: dict[RefusalReason, str] = {
    RefusalReason.NO_SOURCES: (
        "I could not find guidance that covers that question, so I am not going to guess."
    ),
    RefusalReason.INSUFFICIENT_EVIDENCE: (
        "I found guidance on the topic, but not enough to answer that question."
    ),
    RefusalReason.UNVERIFIED: (
        "I found relevant guidance, but I could not verify the answer against it, "
        "so I am not showing it."
    ),
    RefusalReason.MODEL_UNAVAILABLE: (
        "The answering service is unavailable right now. Nothing was charged for this."
    ),
    RefusalReason.BUDGET_EXHAUSTED: ("This question would exceed your usage limit."),
    RefusalReason.DUPLICATE_REQUEST: (
        "This request has already been answered. Ask again as a new question."
    ),
    RefusalReason.BUDGET_UNAVAILABLE: (
        "Usage checks are unavailable right now, so nothing was attempted. Nothing was charged."
    ),
    RefusalReason.TRUNCATED: (
        "The answer was cut off before it finished, so it cannot be checked. "
        "Try a narrower question."
    ),
}


@dataclass(frozen=True, slots=True)
class Refusal:
    reason: RefusalReason
    message: str
    evidence: tuple[Retrieved, ...]
    details: tuple[str, ...] = ()

    def for_audit(self) -> dict[str, object]:
        """What to store: why, and which sections were considered."""
        return {
            "reason": self.reason.value,
            "message": self.message,
            "details": list(self.details),
            "evidence": [
                {
                    "chunk_id": str(source.chunk_id),
                    "version_id": str(source.version_id),
                    "heading_path": source.heading_path,
                    "edition": source.edition,
                    "source_url": source.source_url,
                }
                for source in self.evidence
            ],
        }


def build_refusal(
    reason: RefusalReason,
    evidence: tuple[Retrieved, ...],
    verification: Verification | None = None,
    details: tuple[str, ...] = (),
) -> Refusal:
    collected = list(details)
    if verification is not None:
        for index, claim in enumerate(verification.claims, start=1):
            for check in claim.checks:
                if check.status is not Status.VERIFIED:
                    marker = f", [{check.marker}]" if check.marker is not None else ""
                    quote = f' — "{check.quote[:40]}"' if check.quote else ""
                    collected.append(f"claim {index}{marker}: {check.status.value}{quote}")
    return Refusal(
        reason=reason,
        message=MESSAGES[reason],
        evidence=evidence,
        details=tuple(collected),
    )
