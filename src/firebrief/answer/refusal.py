"""Refusals that a person can act on.

A refusal is not an error. It is an outcome: the system looked, and either found nothing,
found something that did not answer, or could not verify what the model wrote. Each of
those needs different words, and each should show the evidence that was considered so the
reader can see the search was real.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from firebrief.answer.types import Verification
from firebrief.retrieval.types import Retrieved


class RefusalReason(StrEnum):
    NO_SOURCES = "no_sources"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    UNVERIFIED = "unverified"
    MODEL_UNAVAILABLE = "model_unavailable"
    BUDGET_EXHAUSTED = "budget_exhausted"


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
    RefusalReason.BUDGET_EXHAUSTED: (
        "This question would exceed your usage limit. The limit resets at the time shown "
        "in your account."
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
) -> Refusal:
    details: tuple[str, ...] = ()
    if verification is not None:
        details = tuple(
            f"claim {index}: {check.status.value}"
            for index, claim in enumerate(verification.claims, start=1)
            for check in claim.checks
            if check.status.value != "verified"
        )
    return Refusal(
        reason=reason,
        message=MESSAGES[reason],
        evidence=evidence,
        details=details,
    )
