from __future__ import annotations

from pathlib import Path

import pytest

from firebrief.answer import AnswerResult, RefusalReason, build_refusal
from firebrief.answer.types import ClaimCheck, ClaimResult, Status, Verdict, Verification
from firebrief.eval.runner import citation_precision, is_correct, load_cases, run_suite
from firebrief.eval.types import EvalCase, Expect

CASES = Path(__file__).resolve().parents[2] / "evals" / "answering" / "questions.toml"


def answered(text: str, *, verified: bool = True) -> AnswerResult:
    checks = (
        ClaimCheck(
            marker=1, chunk_id=None, status=Status.VERIFIED if verified else Status.MISSING_SPAN
        ),
    )
    verification = Verification(
        claims=(ClaimResult(text="", checks=checks),),
        verdict=Verdict.VERIFIED if verified else Verdict.WITHHELD,
        judge_model="fixed",
        judge_prompt_version="v1",
    )
    return AnswerResult(
        question="q", answer=text, refusal=None, sources=(), verification=verification
    )


def refused() -> AnswerResult:
    return AnswerResult(
        question="q",
        answer=None,
        refusal=build_refusal(RefusalReason.NO_SOURCES, ()),
        sources=(),
    )


def case(expect: Expect, terms: tuple[str, ...] = ()) -> EvalCase:
    return EvalCase(id="c", question="q", expect=expect, terms=terms)


def test_the_case_file_loads_and_covers_both_outcomes() -> None:
    cases = load_cases(CASES)

    assert len(cases) >= 6
    assert {c.expect for c in cases} == {Expect.ANSWER, Expect.REFUSE}


def test_an_answer_missing_a_required_term_is_incorrect() -> None:
    assert is_correct(
        case(Expect.ANSWER, ("thirty metres",)), answered("thirty metres is the limit")
    )
    assert not is_correct(
        case(Expect.ANSWER, ("thirty metres",)), answered("ten metres is the limit")
    )


def test_a_refusal_where_an_answer_was_expected_is_incorrect() -> None:
    assert not is_correct(case(Expect.ANSWER, ("thirty metres",)), refused())


def test_an_answer_where_a_refusal_was_expected_is_incorrect() -> None:
    assert not is_correct(case(Expect.REFUSE), answered("anything"))
    assert is_correct(case(Expect.REFUSE), refused())


def test_citation_precision_counts_verified_checks() -> None:
    assert citation_precision(answered("x", verified=True)) == 1.0
    assert citation_precision(answered("x", verified=False)) == 0.0
    assert citation_precision(refused()) == 0.0


async def test_the_report_summarises_accuracy_and_failures() -> None:
    cases = [
        EvalCase(id="a", question="q1", expect=Expect.ANSWER, terms=("thirty metres",)),
        EvalCase(id="b", question="q2", expect=Expect.ANSWER, terms=("FD30S",)),
        EvalCase(id="c", question="q3", expect=Expect.REFUSE),
    ]
    replies = {
        "q1": answered("thirty metres"),
        "q2": answered("thirty metres"),
        "q3": refused(),
    }

    async def answer(question: str) -> AnswerResult:
        return replies[question]

    report = await run_suite(cases, answer)

    assert report.total == 3
    assert report.accuracy == pytest.approx(2 / 3)
    assert [outcome.case.id for outcome in report.failures] == ["b"]
    assert "accuracy" in report.summary()
    assert "NO" in report.table()
