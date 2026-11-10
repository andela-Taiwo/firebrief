"""Run a labelled set and score it.

Scoring is a function of the answer, not of the model that produced it: an answer counts
only if it is shown and contains the terms a correct answer must contain, and a refusal
counts only if it should have refused.
"""

from __future__ import annotations

import time
import tomllib
from collections.abc import Awaitable, Callable, Sequence
from pathlib import Path

from firebrief.answer import AnswerResult
from firebrief.answer.verify import normalise
from firebrief.budget import PriceTable
from firebrief.eval.types import CaseOutcome, EvalCase, Expect, Report

AnswerFn = Callable[[str], Awaitable[AnswerResult]]


def load_cases(path: Path) -> list[EvalCase]:
    data = tomllib.loads(path.read_text())
    cases: list[EvalCase] = []
    for raw in data.get("cases", []):
        cases.append(
            EvalCase(
                id=str(raw["id"]),
                question=str(raw["question"]),
                expect=Expect(raw["expect"]),
                heading=raw.get("heading"),
                terms=tuple(raw.get("terms", ())),
            )
        )
    if not cases:
        raise ValueError(f"{path}: no cases")
    return cases


def is_correct(case: EvalCase, result: AnswerResult) -> bool:
    if case.expect is Expect.REFUSE:
        return not result.answered
    if not result.answered or result.answer is None:
        return False
    answer = normalise(result.answer)
    return all(normalise(term) in answer for term in case.terms)


def citation_precision(result: AnswerResult) -> float:
    if result.verification is None:
        return 0.0
    checks = [check for claim in result.verification.claims for check in claim.checks]
    if not checks:
        return 0.0
    verified = sum(1 for check in checks if check.status.value == "verified")
    return verified / len(checks)


async def run_case(
    case: EvalCase,
    answer: AnswerFn,
    *,
    prices: PriceTable | None = None,
    price_model: str | None = None,
) -> CaseOutcome:
    started = time.perf_counter()
    result = await answer(case.question)
    elapsed = int((time.perf_counter() - started) * 1000)

    cost = 0
    if prices is not None and price_model is not None and result.usage is not None:
        cost = prices.price(price_model).cost(result.usage.input_tokens, result.usage.output_tokens)

    return CaseOutcome(
        case=case,
        result=result,
        correct=is_correct(case, result),
        citation_precision=citation_precision(result),
        latency_ms=elapsed,
        cost_micros=cost,
    )


async def run_suite(
    cases: Sequence[EvalCase],
    answer: AnswerFn,
    *,
    prices: PriceTable | None = None,
    price_model: str | None = None,
) -> Report:
    outcomes = [
        await run_case(case, answer, prices=prices, price_model=price_model) for case in cases
    ]
    return Report(outcomes=tuple(outcomes), priced=prices is not None and price_model is not None)
