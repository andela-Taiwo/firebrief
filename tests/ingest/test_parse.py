from __future__ import annotations

import pytest

from firebrief.ingest.parse import EmptyDocument, parse_sections
from tests.ingest.fixtures import GUIDANCE_HTML, INTRO_HTML


def test_sections_follow_the_heading_structure() -> None:
    sections = parse_sections(GUIDANCE_HTML)

    assert [section.heading for section in sections] == [
        "Fire safety in purpose-built flats",
        "Means of escape",
        "Dead ends",
        "Fire doors",
        "Notes",
        "Notes",
    ]


def test_nested_headings_carry_their_path() -> None:
    sections = parse_sections(GUIDANCE_HTML)
    dead_ends = next(section for section in sections if section.heading == "Dead ends")

    assert dead_ends.heading_path == (
        "Fire safety in purpose-built flats > Means of escape > Dead ends"
    )


def test_page_furniture_is_not_captured() -> None:
    sections = parse_sections(GUIDANCE_HTML)
    everything = " ".join(section.body for section in sections)

    assert "Home > Housing" not in everything
    assert "cookies" not in everything
    assert "analytics" not in everything
    assert "Open Government Licence" not in everything


def test_list_items_join_the_section_body() -> None:
    sections = parse_sections(GUIDANCE_HTML)
    doors = next(section for section in sections if section.heading == "Fire doors")

    assert "Check the gaps." in doors.body
    assert "Check the seals." in doors.body


def test_table_content_is_kept_in_reading_order() -> None:
    sections = parse_sections(GUIDANCE_HTML)
    doors = next(section for section in sections if section.heading == "Fire doors")

    positions = [doors.body.index(cell) for cell in ("Door type", "Rating", "FD30S")]
    assert positions == sorted(positions), doors.body


def test_duplicate_headings_are_kept_as_separate_sections() -> None:
    notes = [section for section in parse_sections(GUIDANCE_HTML) if section.heading == "Notes"]

    assert len(notes) == 2
    assert [note.body for note in notes] == ["First note.", "Second note."]


def test_text_before_the_first_heading_becomes_the_introduction() -> None:
    sections = parse_sections(INTRO_HTML, title="Fire safety in purpose-built flats")

    assert sections[0].heading == "Fire safety in purpose-built flats"
    assert sections[0].body == "This summary sits before any heading."


def test_a_page_without_headings_becomes_one_introduction() -> None:
    sections = parse_sections("<main><p>Only prose, no headings.</p></main>")

    assert len(sections) == 1
    assert sections[0].body == "Only prose, no headings."


def test_an_empty_page_is_refused() -> None:
    with pytest.raises(EmptyDocument):
        parse_sections("<main>   </main>")


def test_content_outside_the_main_element_is_ignored() -> None:
    sections = parse_sections(
        "<nav>Navigation</nav><main><h1>Real title</h1><p>Real body.</p></main>"
    )

    assert [section.heading for section in sections] == ["Real title"]
    assert "Navigation" not in sections[0].body
