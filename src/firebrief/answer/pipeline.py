"""Question to answer, or refusal with a reason.

Retrieval, the model and the verifier are separate steps with separate failure modes.
The model is the only non-deterministic one, and it never gets the last word: whatever
it writes is checked against the sources before anyone sees it.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from firebrief.answer.judge import SupportJudge
from firebrief.answer.prompt import INSUFFICIENT_EVIDENCE, build_prompt
from firebrief.answer.refusal import Refusal, RefusalReason, build_refusal
from firebrief.answer.types import Verification
from firebrief.answer.verify import verify_answer
from firebrief.budget import BudgetService, estimate_prompt_tokens
from firebrief.ingest.embed import Embedder
from firebrief.llm import LLMRequest, Message, Provider, Role, Usage
from firebrief.retrieval.search import search
from firebrief.retrieval.types import Retrieved

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "claude-sonnet-4-5-20250929"
DEFAULT_MAX_TOKENS = 800
TRUNCATION_REASONS = {"max_tokens", "length"}


@dataclass(frozen=True, slots=True)
class BudgetScope:
    org_id: str
    team_id: str
    user_id: str


@dataclass(frozen=True, slots=True)
class AnswerResult:
    question: str
    answer: str | None
    refusal: Refusal | None
    sources: tuple[Retrieved, ...]
    verification: Verification | None = None
    usage: Usage | None = None
    request_id: str = ""

    @property
    def answered(self) -> bool:
        return self.answer is not None

    @property
    def refusal_reason(self) -> RefusalReason | None:
        return self.refusal.reason if self.refusal is not None else None


def is_insufficient(text: str) -> bool:
    """Models add quotes, full stops and explanations to the token. Accept those."""
    first_line = text.strip().splitlines()[0] if text.strip() else ""
    return first_line.strip().strip("\"'.,;:!? ").strip().upper() == INSUFFICIENT_EVIDENCE


def _refuse(
    question: str,
    reason: RefusalReason,
    sources: Sequence[Retrieved],
    *,
    verification: Verification | None = None,
    usage: Usage | None = None,
    details: tuple[str, ...] = (),
    request_id: str = "",
) -> AnswerResult:
    return AnswerResult(
        question=question,
        answer=None,
        refusal=build_refusal(reason, tuple(sources), verification, details),
        sources=tuple(sources),
        verification=verification,
        usage=usage,
        request_id=request_id,
    )


async def answer_from_sources(
    question: str,
    sources: Sequence[Retrieved],
    *,
    provider: Provider,
    judge: SupportJudge,
    model: str = DEFAULT_MODEL,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    budget: BudgetService | None = None,
    scope: BudgetScope | None = None,
    request_id: str | None = None,
) -> AnswerResult:
    request_id = request_id or uuid.uuid4().hex

    if not sources:
        return _refuse(question, RefusalReason.NO_SOURCES, sources, request_id=request_id)

    system, user = build_prompt(question, sources)
    request = LLMRequest(
        model=model,
        messages=(Message(Role.SYSTEM, system), Message(Role.USER, user)),
        max_tokens=max_tokens,
    )

    reservation = None
    if budget is not None:
        if scope is None:
            raise ValueError("a budget needs a scope to charge")
        try:
            decision = budget.reserve(
                request_id=request_id,
                org_id=scope.org_id,
                team_id=scope.team_id,
                user_id=scope.user_id,
                model=model,
                prompt_tokens=estimate_prompt_tokens([system, user]),
                max_output_tokens=max_tokens,
            )
        except Exception as exc:
            logger.warning("budget reservation failed: %s", type(exc).__name__)
            return _refuse(
                question,
                RefusalReason.BUDGET_EXHAUSTED,
                sources,
                details=("the budget service is unavailable, so nothing was attempted",),
                request_id=request_id,
            )
        if not decision.admitted or decision.reservation is None:
            details = ()
            if decision.rejection is not None:
                details = (f"limit resets at {decision.rejection.reset_at.isoformat()}",)
            return _refuse(
                question,
                RefusalReason.BUDGET_EXHAUSTED,
                sources,
                details=details,
                request_id=request_id,
            )
        reservation = decision.reservation

    try:
        response = await provider.complete(request)
    except Exception as exc:
        logger.warning("provider failed: %s", type(exc).__name__)
        if budget is not None and reservation is not None:
            _safe(lambda: budget.release(reservation.id), "release")
        return _refuse(question, RefusalReason.MODEL_UNAVAILABLE, sources, request_id=request_id)

    if budget is not None and reservation is not None:
        _safe(
            lambda: budget.settle(
                reservation.id,
                input_tokens=response.usage.input_tokens,
                output_tokens=response.usage.output_tokens,
            ),
            "settle",
        )

    text = response.text.strip()
    if is_insufficient(text):
        return _refuse(
            question,
            RefusalReason.INSUFFICIENT_EVIDENCE,
            sources,
            usage=response.usage,
            request_id=request_id,
        )

    if (response.finish_reason or "").lower() in TRUNCATION_REASONS:
        return _refuse(
            question,
            RefusalReason.TRUNCATED,
            sources,
            usage=response.usage,
            request_id=request_id,
        )

    verification = await verify_answer(text, sources, judge=judge)
    if not verification.may_show:
        return _refuse(
            question,
            RefusalReason.UNVERIFIED,
            sources,
            verification=verification,
            usage=response.usage,
            request_id=request_id,
        )

    return AnswerResult(
        question=question,
        answer=text,
        refusal=None,
        sources=tuple(sources),
        verification=verification,
        usage=response.usage,
        request_id=request_id,
    )


def _safe(action: Any, name: str) -> None:
    """A bookkeeping failure must not turn an answer into a crash."""
    try:
        action()
    except Exception as exc:
        logger.warning("budget %s failed: %s", name, type(exc).__name__)


async def answer_question(
    session: AsyncSession,
    question: str,
    *,
    embedder: Embedder,
    provider: Provider,
    judge: SupportJudge,
    limit: int = 6,
    as_of: date | None = None,
    model: str = DEFAULT_MODEL,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    budget: BudgetService | None = None,
    scope: BudgetScope | None = None,
    request_id: str | None = None,
) -> AnswerResult:
    sources = await search(session, question, embedder, limit=limit, as_of=as_of)
    return await answer_from_sources(
        question,
        sources,
        provider=provider,
        judge=judge,
        model=model,
        max_tokens=max_tokens,
        budget=budget,
        scope=scope,
        request_id=request_id,
    )
