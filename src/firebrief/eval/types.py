"""What an evaluation run produces."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from firebrief.answer import AnswerResult


class Expect(StrEnum):
    ANSWER = "answer"
    REFUSE = "refuse"


@dataclass(frozen=True, slots=True)
class EvalCase:
    id: str
    question: str
    expect: Expect
    heading: str | None = None
    terms: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class CaseOutcome:
    case: EvalCase
    result: AnswerResult
    correct: bool
    citation_precision: float
    latency_ms: int
    cost_micros: int


@dataclass(frozen=True, slots=True)
class Report:
    outcomes: tuple[CaseOutcome, ...]
    priced: bool = False

    @property
    def total(self) -> int:
        return len(self.outcomes)

    @property
    def accuracy(self) -> float:
        if not self.outcomes:
            return 0.0
        return sum(1 for outcome in self.outcomes if outcome.correct) / len(self.outcomes)

    @property
    def answer_accuracy(self) -> float:
        cases = [o for o in self.outcomes if o.case.expect is Expect.ANSWER]
        return sum(1 for o in cases if o.correct) / len(cases) if cases else 0.0

    @property
    def refusal_accuracy(self) -> float:
        cases = [o for o in self.outcomes if o.case.expect is Expect.REFUSE]
        return sum(1 for o in cases if o.correct) / len(cases) if cases else 0.0

    @property
    def citation_precision(self) -> float:
        answered = [o for o in self.outcomes if o.result.answered]
        if not answered:
            return 0.0
        return sum(o.citation_precision for o in answered) / len(answered)

    @property
    def total_cost_micros(self) -> int:
        return sum(outcome.cost_micros for outcome in self.outcomes)

    @property
    def p95_latency_ms(self) -> int:
        if not self.outcomes:
            return 0
        ordered = sorted(outcome.latency_ms for outcome in self.outcomes)
        index = min(len(ordered) - 1, round(0.95 * (len(ordered) - 1)))
        return ordered[index]

    @property
    def failures(self) -> tuple[CaseOutcome, ...]:
        return tuple(outcome for outcome in self.outcomes if not outcome.correct)

    def summary(self) -> str:
        cost = f"{self.total_cost_micros} micros" if self.priced else "unpriced"
        return (
            f"accuracy {self.accuracy:.2f} "
            f"({sum(1 for o in self.outcomes if o.correct)}/{self.total})"
            f" · answers {self.answer_accuracy:.2f}"
            f" · refusals {self.refusal_accuracy:.2f}"
            f" · citation precision {self.citation_precision:.2f}"
            f" · p95 {self.p95_latency_ms}ms"
            f" · cost {cost}"
        )

    def table(self) -> str:
        lines = [f"{'case':<24} {'expect':<7} {'got':<20} {'cites':<6} ok"]
        for outcome in self.outcomes:
            got = (
                "answered"
                if outcome.result.answered
                else (outcome.result.refusal_reason.value if outcome.result.refusal_reason else "?")
            )
            lines.append(
                f"{outcome.case.id:<24} {outcome.case.expect.value:<7} {got:<20} "
                f"{outcome.citation_precision:<6.2f} {'yes' if outcome.correct else 'NO'}"
            )
        return "\n".join(lines)
