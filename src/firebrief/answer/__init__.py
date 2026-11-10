"""Answer verification: an answer is shown only if its evidence exists."""

from firebrief.answer.judge import FailingJudge, FixedJudge, SupportJudge
from firebrief.answer.types import ClaimCheck, ClaimResult, Status, Verdict, Verification
from firebrief.answer.verify import Claim, normalise, parse_claims, verify_answer

__all__ = [
    "Claim",
    "ClaimCheck",
    "ClaimResult",
    "FailingJudge",
    "FixedJudge",
    "Status",
    "SupportJudge",
    "Verdict",
    "Verification",
    "normalise",
    "parse_claims",
    "verify_answer",
]
