from __future__ import annotations

import pytest

from firebrief.ingest.parse import EmptyDocument, parse_sections
from tests.ingest.fixtures import GUIDANCE_HTML


def test_sections_follow_the_heading_structure() -> None:
    sections = parse_sections(GUIDANCE_HTML)

    assert [section.heading for section in sections] == [
        "Fire safety in purpose-built flats",
        "Means of escape",
        "Dead ends",
        "Fire doors",
    ]


def test_nested_headings_carry_their_path() -> None:
    sections = parse_sections(GUIDANCE_HTML)
    dead_ends = next(section for section in sections if section.heading == "Dead ends")

    assert dead_ends.heading_path == (
        "Fire safety in purpose-built flats > Means of escape > Dead ends"
    )


def test_navigation_and_scripts_are_not_captured() -> None:
    sections = parse_sections(GUIDANCE_HTML)
    everything = " ".join(section.body for section in sections)

    assert "Home > Housing" not in everything
    assert "breadcrumbs" not in everything


def test_list_items_join_the_section_body() -> None:
    sections = parse_sections(GUIDANCE_HTML)
    doors = next(section for section in sections if section.heading == "Fire doors")

    assert "Check the gaps." in doors.body
    assert "Check the seals." in doors.body


def test_a_page_without_headings_is_refused() -> None:
    with pytest.raises(EmptyDocument):
        parse_sections("<html><body><p>No structure here.</p></body></html>")


def test_text_before_the_first_heading_is_discarded() -> None:
    sections = parse_sections("<p>Navigation</p><h1>Real title</h1><p>Real body.</p>")

    assert len(sections) == 1
    assert sections[0].body == "Real body."
