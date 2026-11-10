from __future__ import annotations

import uuid

import pytest

from firebrief.answer.judge import FailingJudge, FixedJudge
from firebrief.answer.types import Status, Verdict
from firebrief.answer.verify import find_span, normalise, parse_claims, verify_answer
from firebrief.retrieval.types import Retrieved

DEAD_ENDS = "Dead ends must be limited in length to thirty metres."
DOORS = "Flat entrance doors must be self-closing and fire-resisting."
SHARED_VERSION = uuid.UUID("018f0000-0000-7000-8000-00000000aaaa")


def source(text: str, *, version_id: uuid.UUID | None = None, index: int = 0) -> Retrieved:
    return Retrieved(
        chunk_id=uuid.uuid4(),
        section_id=uuid.uuid4(),
        version_id=version_id or uuid.uuid4(),
        heading_path=f"Doc > Section {index}",
        text=text,
        score=0.5,
        vector_rank=1,
        text_rank=1,
        embedding_model="bow-1024",
        document_title="Doc",
        edition="2019",
        source_url="https://www.gov.uk/doc",
    )


def answer(quote: str, marker: int = 1) -> str:
    return f'The guidance says: "{quote}" [{marker}]'


async def test_a_quote_in_the_cited_source_is_verified() -> None:
    result = await verify_answer(answer(DEAD_ENDS), [source(DEAD_ENDS)], judge=FixedJudge())

    assert result.verdict is Verdict.VERIFIED
    assert result.may_show


async def test_a_quote_that_is_in_another_source_withholds() -> None:
    """The quote exists, but not in the source the claim cites."""
    result = await verify_answer(
        answer(DEAD_ENDS, marker=1), [source(DOORS), source(DEAD_ENDS)], judge=FixedJudge()
    )

    assert result.verdict is Verdict.WITHHELD
    assert result.claims[0].checks[0].status is Status.MISSING_SPAN
    assert not result.may_show


async def test_a_contradictory_claim_is_caught_by_the_judge() -> None:
    """Existence passes; only support checking catches 'ten metres' against thirty."""
    claim = f'Dead ends are capped at ten metres: "{DEAD_ENDS}" [1]'
    result = await verify_answer(claim, [source(DEAD_ENDS)], judge=FixedJudge(accepts=False))

    assert result.verdict is Verdict.WITHHELD
    assert result.claims[0].checks[0].status is Status.UNSUPPORTED


async def test_a_judge_error_withholds_rather_than_raising() -> None:
    result = await verify_answer(answer(DEAD_ENDS), [source(DEAD_ENDS)], judge=FailingJudge())

    assert result.verdict is Verdict.WITHHELD
    assert result.claims[0].checks[0].status is Status.JUDGE_ERROR


async def test_the_judge_and_its_prompt_are_recorded() -> None:
    result = await verify_answer(answer(DEAD_ENDS), [source(DEAD_ENDS)], judge=FixedJudge())

    assert result.judge_model == "fixed-judge"
    assert result.judge_prompt_version == "v1"


async def test_the_judge_sees_the_claim_without_its_quote() -> None:
    judge = FixedJudge()
    await verify_answer(answer(DEAD_ENDS), [source(DEAD_ENDS)], judge=judge)

    claim, quote, window = judge.calls[0]
    assert DEAD_ENDS not in claim
    assert quote == DEAD_ENDS
    assert DEAD_ENDS in window


async def test_the_judge_is_not_called_when_the_quote_is_absent() -> None:
    judge = FixedJudge()
    await verify_answer(
        answer("Dead ends must be limited to ten metres."), [source(DEAD_ENDS)], judge=judge
    )

    assert judge.calls == []


async def test_a_trivial_quote_is_refused() -> None:
    result = await verify_answer('Doors: "must be" [1]', [source(DEAD_ENDS)], judge=FixedJudge())

    assert result.verdict is Verdict.WITHHELD
    assert result.claims[0].checks[0].status is Status.QUOTE_TOO_SHORT


async def test_an_unknown_marker_withholds() -> None:
    result = await verify_answer(
        answer(DEAD_ENDS, marker=3), [source(DEAD_ENDS)], judge=FixedJudge()
    )

    assert result.verdict is Verdict.WITHHELD
    assert result.claims[0].checks[0].status is Status.UNKNOWN_MARKER


async def test_marker_zero_withholds() -> None:
    result = await verify_answer(
        answer(DEAD_ENDS, marker=0), [source(DEAD_ENDS)], judge=FixedJudge()
    )

    assert result.verdict is Verdict.WITHHELD
    assert result.claims[0].checks[0].status is Status.UNKNOWN_MARKER


async def test_no_sources_withholds() -> None:
    result = await verify_answer(answer(DEAD_ENDS), [], judge=FixedJudge())

    assert result.verdict is Verdict.WITHHELD
    assert not result.may_show


async def test_an_uncited_claim_withholds() -> None:
    result = await verify_answer("Dead ends are capped.", [source(DEAD_ENDS)], judge=FixedJudge())

    assert result.verdict is Verdict.WITHHELD
    assert result.claims[0].checks[0].status is Status.UNCITED
    assert not result.may_show


async def test_two_markers_each_need_their_own_quote() -> None:
    claim = f'Doors and dead ends: "{DOORS}" [1] "{DEAD_ENDS}" [2]'
    result = await verify_answer(claim, [source(DOORS), source(DEAD_ENDS)], judge=FixedJudge())

    assert result.verdict is Verdict.VERIFIED


async def test_a_marker_without_a_quote_withholds() -> None:
    claim = f'Doors and dead ends: "{DOORS}" [1][2]'
    result = await verify_answer(claim, [source(DOORS), source(DEAD_ENDS)], judge=FixedJudge())

    assert result.verdict is Verdict.WITHHELD


async def test_a_repeated_marker_with_one_quote_withholds() -> None:
    claim = f'Doors: "{DOORS}" [1][1]'
    result = await verify_answer(claim, [source(DOORS)], judge=FixedJudge())

    assert result.verdict is Verdict.WITHHELD


async def test_a_quote_survives_typography() -> None:
    source_text = "Flat entrance doors must be self-closing and fire-resistant."
    claim = 'Doors: "doors must be self\u2011closing and fire\u2013resistant" [1]'
    result = await verify_answer(claim, [source(source_text)], judge=FixedJudge())

    assert result.verdict is Verdict.VERIFIED


async def test_whitespace_and_case_do_not_affect_existence() -> None:
    result = await verify_answer(
        '"dead   ends must be limited in length to THIRTY metres." [1]',
        [source(DEAD_ENDS.replace(" ", "\n"))],
        judge=FixedJudge(),
    )

    assert result.verdict is Verdict.VERIFIED


async def test_a_quote_containing_a_full_stop_is_one_sentence() -> None:
    claim = 'The rule: "Dead ends must be limited in length to thirty metres." [1]'
    result = await verify_answer(claim, [source(DEAD_ENDS)], judge=FixedJudge())

    assert result.verdict is Verdict.VERIFIED


async def test_abbreviations_do_not_split_a_claim() -> None:
    claim = (
        "Dead ends, e.g. in flats, are capped: "
        '"Dead ends must be limited in length to thirty metres." [1]'
    )
    result = await verify_answer(claim, [source(DEAD_ENDS)], judge=FixedJudge())

    assert len(result.claims) == 1
    assert result.verdict is Verdict.VERIFIED


async def test_an_empty_answer_is_withheld() -> None:
    assert (
        await verify_answer("   ", [source(DEAD_ENDS)], judge=FixedJudge())
    ).verdict is Verdict.WITHHELD


async def test_two_sections_of_one_version_are_told_apart() -> None:
    first = source(DEAD_ENDS, version_id=SHARED_VERSION, index=0)
    second = source(DOORS, version_id=SHARED_VERSION, index=1)

    result = await verify_answer(answer(DOORS, marker=2), [first, second], judge=FixedJudge())

    check = result.claims[0].checks[0]
    assert check.section_id == second.section_id
    assert check.version_id == SHARED_VERSION
    assert check.char_start is not None
    assert check.char_end is not None


def test_claims_are_parsed_with_their_markers_and_quotes() -> None:
    claims = parse_claims(f'One thing. Two thing. "{DEAD_ENDS}" [1][2]')

    assert len(claims) == 2
    assert claims[0].text == "One thing."
    assert claims[0].markers == ()
    assert claims[1].markers == (1, 2)
    assert DEAD_ENDS in claims[1].text or claims[1].quotes


def test_normalise_collapses_case_and_whitespace() -> None:
    assert normalise("  Dead\nEnds  ") == "dead ends"


@pytest.mark.parametrize(
    ("source_text", "quote"),
    [(DEAD_ENDS, "thirty metres"), (DEAD_ENDS, "metres"), (DEAD_ENDS, "metre")],
)
def test_find_span_respects_word_boundaries(source_text: str, quote: str) -> None:
    span = find_span(source_text, quote)

    assert (span is not None) == (quote != "metre")
