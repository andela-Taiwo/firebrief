from __future__ import annotations

import pytest

from firebrief.ingest.chunk import chunk_sections
from firebrief.ingest.types import ParsedSection


def section(body: str, heading_path: str = "Doc > Section") -> ParsedSection:
    return ParsedSection(heading_path=heading_path, heading="Section", body=body)


def test_a_short_section_stays_one_chunk() -> None:
    chunks = chunk_sections([section("A short body.")], max_tokens=100)

    assert len(chunks) == 1
    assert chunks[0].text == "A short body."
    assert chunks[0].heading_path == "Doc > Section"
    assert chunks[0].ordinal == 0


def test_a_long_section_is_split_within_the_budget() -> None:
    body = " ".join(f"word{index}" for index in range(400))
    chunks = chunk_sections([section(body)], max_tokens=60, overlap_tokens=10)

    assert len(chunks) > 1
    assert all(chunk.token_estimate <= 60 for chunk in chunks), [
        chunk.token_estimate for chunk in chunks
    ]


def test_consecutive_chunks_overlap() -> None:
    body = " ".join(f"word{index}" for index in range(200))
    chunks = chunk_sections([section(body)], max_tokens=40, overlap_tokens=10)

    tail = chunks[0].text.split()[-4:]
    assert any(word in chunks[1].text for word in tail), (chunks[0].text, chunks[1].text)


def test_ordinals_run_across_sections() -> None:
    chunks = chunk_sections(
        [section("First body."), section("Second body.", heading_path="Doc > Other")],
        max_tokens=100,
    )

    assert [chunk.ordinal for chunk in chunks] == [0, 1]
    assert [chunk.heading_path for chunk in chunks] == ["Doc > Section", "Doc > Other"]


@pytest.mark.parametrize(("max_tokens", "overlap"), [(0, 0), (10, 10), (10, 20)])
def test_invalid_budgets_are_refused(max_tokens: int, overlap: int) -> None:
    with pytest.raises(ValueError):
        chunk_sections([section("Body.")], max_tokens=max_tokens, overlap_tokens=overlap)
