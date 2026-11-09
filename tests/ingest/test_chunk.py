from __future__ import annotations

import pytest

from firebrief.ingest.chunk import chunk_sections, chunker_id
from firebrief.ingest.types import ParsedSection


def section(body: str, heading_path: str = "Doc > Section") -> ParsedSection:
    return ParsedSection(heading_path=heading_path, heading="Section", body=body)


def words(count: int) -> str:
    return " ".join(f"word{index}" for index in range(count))


def test_a_short_section_stays_one_chunk() -> None:
    chunks = chunk_sections([section("A short body.")], max_tokens=100)

    assert len(chunks) == 1
    assert chunks[0].text == "A short body."
    assert chunks[0].heading_path == "Doc > Section"
    assert chunks[0].ordinal == 0


def test_offsets_point_at_the_chunk_text() -> None:
    body = "One sentence. Two sentence. Three sentence."
    chunk = chunk_sections([section(body)], max_tokens=100)[0]

    assert body[chunk.char_start : chunk.char_end] == chunk.text


def test_a_long_section_is_split_within_the_budget() -> None:
    chunks = chunk_sections([section(words(400))], max_tokens=60, overlap_tokens=10)

    assert len(chunks) > 1
    assert all(chunk.token_estimate <= 60 for chunk in chunks)


def test_consecutive_chunks_overlap_by_exactly_the_configured_words() -> None:
    chunks = chunk_sections([section(words(200))], max_tokens=40, overlap_tokens=10)

    first = chunks[0].text.split()
    second = chunks[1].text.split()
    overlap = max(1, 10 // 2)
    assert first[-overlap:] == second[:overlap], (first[-overlap:], second[:overlap])


def test_a_word_longer_than_the_budget_still_produces_one_chunk() -> None:
    long_word = "x" * 300
    chunks = chunk_sections([section(long_word)], max_tokens=10, overlap_tokens=0)

    assert len(chunks) == 1
    assert chunks[0].text == long_word


def test_chunks_remember_which_section_they_came_from() -> None:
    chunks = chunk_sections(
        [section("First."), section("Second.", heading_path="Doc > Notes")], max_tokens=100
    )

    assert [chunk.section_index for chunk in chunks] == [0, 1]
    assert [chunk.ordinal for chunk in chunks] == [0, 1]


def test_the_chunker_identity_carries_the_configuration() -> None:
    assert chunker_id(300, 50) != chunker_id(200, 50)
    assert chunker_id(300, 50) != chunker_id(300, 20)


@pytest.mark.parametrize(("max_tokens", "overlap"), [(0, 0), (10, 10), (10, 20)])
def test_invalid_budgets_are_refused(max_tokens: int, overlap: int) -> None:
    with pytest.raises(ValueError):
        chunk_sections([section("Body.")], max_tokens=max_tokens, overlap_tokens=overlap)
