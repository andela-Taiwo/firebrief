from __future__ import annotations

import uuid

from firebrief.answer.judge import FixedJudge
from firebrief.answer.types import Status, Verdict
from firebrief.answer.verify import normalise, parse_claims, verify_answer
from firebrief.retrieval.types import Retrieved

DEAD_ENDS = "Dead ends must be limited in length to thirty metres."
DOORS = "Flat entrance doors must be self-closing and fire-resisting."


def source(text: str, *, index: int = 0) -> Retrieved:
    return Retrieved(
        chunk_id=uuid.uuid4(),
        section_id=uuid.uuid4(),
        version_id=uuid.uuid4(),
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


async def test_a_quoted_passage_that_exists_is_verified() -> None:
    answer = f'Dead ends are capped. "{DEAD_ENDS}" [1]'
    result = await verify_answer(answer, [source(DEAD_ENDS)])

    assert result.verdict is Verdict.VERIFIED
    assert result.may_show
    assert result.claims[0].checks[0].chunk_id is not None


async def test_a_quoted_passage_that_is_absent_withholds() -> None:
    answer = 'Dead ends are capped at ten metres. "Dead ends must be limited to ten metres." [1]'
    result = await verify_answer(answer, [source(DEAD_ENDS)])

    assert result.verdict is Verdict.WITHHELD
    assert result.claims[0].checks[0].status is Status.MISSING_SPAN


async def test_an_unknown_marker_withholds() -> None:
    answer = f'"{DEAD_ENDS}" [3]'
    result = await verify_answer(answer, [source(DEAD_ENDS)])

    assert result.verdict is Verdict.WITHHELD
    assert result.claims[0].checks[0].status is Status.UNKNOWN_MARKER


async def test_an_uncited_claim_withholds() -> None:
    result = await verify_answer("Dead ends are capped.", [source(DEAD_ENDS)])

    assert result.verdict is Verdict.WITHHELD
    assert result.claims[0].checks[0].status is Status.UNCITED


async def test_whitespace_and_case_do_not_affect_existence() -> None:
    answer = '"dead   ends must be limited in length to THIRTY metres." [1]'
    result = await verify_answer(answer, [source(DEAD_ENDS.replace(" ", "\n"))])

    assert result.verdict is Verdict.VERIFIED


async def test_an_empty_answer_is_withheld() -> None:
    assert (await verify_answer("   ", [source(DEAD_ENDS)])).verdict is Verdict.WITHHELD


async def test_a_rejecting_judge_withholds() -> None:
    answer = f'"{DEAD_ENDS}" [1]'
    result = await verify_answer(answer, [source(DEAD_ENDS)], judge=FixedJudge(accepts=False))

    assert result.verdict is Verdict.WITHHELD
    assert result.claims[0].checks[0].status is Status.UNSUPPORTED


async def test_an_accepting_judge_still_requires_existence() -> None:
    answer = '"Dead ends must be limited to ten metres." [1]'
    result = await verify_answer(answer, [source(DEAD_ENDS)], judge=FixedJudge(accepts=True))

    assert result.verdict is Verdict.WITHHELD
    assert result.claims[0].checks[0].status is Status.MISSING_SPAN


async def test_one_bad_claim_withholds_the_whole_answer() -> None:
    answer = f'Doors must close. "{DOORS}" [1] Dead ends are capped. "{DEAD_ENDS}" [2]'
    result = await verify_answer(answer, [source(DOORS), source("Something else entirely.")])

    assert result.verdict is Verdict.WITHHELD
    assert len(result.claims) == 2


async def test_a_claim_with_a_marker_but_no_quote_withholds() -> None:
    answer = "Dead ends are capped. [1]"
    result = await verify_answer(answer, [source(DEAD_ENDS)])

    assert result.verdict is Verdict.WITHHELD
    assert result.claims[0].checks[0].status is Status.MISSING_SPAN


def test_claims_are_parsed_with_their_markers_and_quotes() -> None:
    claims = parse_claims(f'One thing. Two thing. "{DEAD_ENDS}" [1][2]')

    assert len(claims) == 2
    assert claims[0].text == "One thing."
    assert claims[1].markers == (1, 2)
    assert claims[1].quotes == (DEAD_ENDS,)


def test_normalise_collapses_case_and_whitespace() -> None:
    assert normalise("  Dead\nEnds  ") == "dead ends"
