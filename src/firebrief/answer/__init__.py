"""Answer verification: an answer is shown only if its evidence exists."""

from firebrief.answer.judge import FailingJudge, FixedJudge, SupportJudge
from firebrief.answer.pipeline import (
    AnswerResult,
    BudgetScope,
    answer_from_sources,
    answer_question,
)
from firebrief.answer.prompt import INSUFFICIENT_EVIDENCE, SYSTEM_PROMPT, build_prompt
from firebrief.answer.refusal import Refusal, RefusalReason, build_refusal
from firebrief.answer.types import ClaimCheck, ClaimResult, Status, Verdict, Verification
from firebrief.answer.verify import Claim, normalise, parse_claims, verify_answer

__all__ = [
    "INSUFFICIENT_EVIDENCE",
    "SYSTEM_PROMPT",
    "AnswerResult",
    "BudgetScope",
    "Claim",
    "ClaimCheck",
    "ClaimResult",
    "FailingJudge",
    "Finding",
    "FixedJudge",
    "Kind",
    "Redaction",
    "Refusal",
    "RefusalReason",
    "Status",
    "SupportJudge",
    "Verdict",
    "Verification",
    "answer_from_sources",
    "answer_question",
    "build_prompt",
    "build_refusal",
    "normalise",
    "parse_claims",
    "redact",
    "verify_answer",
]
