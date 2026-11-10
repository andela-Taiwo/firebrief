"""Question to answer, or refusal with a reason.

Retrieval, the model and the verifier are separate steps with separate failure modes.
The model is the only non-deterministic one, and it never gets the last word: whatever
it writes is checked against the sources before anyone sees it.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date

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

DEFAULT_MODEL = "claude-sonnet-4-5-20250929"
DEFAULT_MAX_TOKENS = 800


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

    @property
    def answered(self) -> bool:
        return self.answer is not None

    @property
    def refusal_reason(self) -> RefusalReason | None:
        return self.refusal.reason if self.refusal is not None else None


def _refuse(
    question: str,
    reason: RefusalReason,
    sources: Sequence[Retrieved],
    *,
    verification: Verification | None = None,
    usage: Usage | None = None,
) -> AnswerResult:
    return AnswerResult(
        question=question,
        answer=None,
        refusal=build_refusal(reason, tuple(sources), verification),
        sources=tuple(sources),
        verification=verification,
        usage=usage,
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
) -> AnswerResult:
    if not sources:
        return _refuse(question, RefusalReason.NO_SOURCES, sources)

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
        decision = budget.reserve(
            request_id=question[:64],
            org_id=scope.org_id,
            team_id=scope.team_id,
            user_id=scope.user_id,
            model=model,
            prompt_tokens=estimate_prompt_tokens([system, user]),
            max_output_tokens=max_tokens,
        )
        if not decision.admitted or decision.reservation is None:
            return _refuse(question, RefusalReason.BUDGET_EXHAUSTED, sources)
        reservation = decision.reservation

    try:
        response = await provider.complete(request)
    except Exception:
        if budget is not None and reservation is not None:
            budget.release(reservation.id)
        return _refuse(question, RefusalReason.MODEL_UNAVAILABLE, sources)

    if budget is not None and reservation is not None:
        budget.settle(
            reservation.id,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
        )

    text = response.text.strip()
    if text.strip().strip('"') == INSUFFICIENT_EVIDENCE:
        return _refuse(question, RefusalReason.INSUFFICIENT_EVIDENCE, sources, usage=response.usage)

    verification = await verify_answer(text, sources, judge=judge)
    if not verification.may_show:
        return _refuse(question, RefusalReason.UNVERIFIED, sources, verification=verification)

    return AnswerResult(
        question=question,
        answer=text,
        refusal=None,
        sources=tuple(sources),
        verification=verification,
        usage=response.usage,
    )


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
    )
