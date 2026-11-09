from __future__ import annotations

import pytest

from firebrief.ingest.parse import EmptyDocument, parse_sections
from tests.ingest.fixtures import CONTENT_API_HTML, GUIDANCE_HTML

TITLE = "Fire safety in purpose-built flats"


def test_sections_follow_the_heading_structure() -> None:
    sections = parse_sections(GUIDANCE_HTML, title=TITLE)

    assert [section.heading for section in sections] == [
        "Fire safety in purpose-built flats",
        "Means of escape",
        "Dead ends",
        "Fire doors",
        "Notes",
        "Notes",
    ]


def test_the_title_is_not_repeated_when_the_page_has_an_h1() -> None:
    sections = parse_sections(GUIDANCE_HTML, title=TITLE)
    escape = next(section for section in sections if section.heading == "Means of escape")

    assert escape.heading_path == "Fire safety in purpose-built flats > Means of escape"


def test_a_content_api_body_starts_at_the_title() -> None:
    """Govspeak bodies have no h1: the title is a separate field."""
    sections = parse_sections(CONTENT_API_HTML, title=TITLE)

    assert sections[0].heading == TITLE
    assert sections[0].body == "The summary sits before any heading."
    assert sections[1].heading_path == "Fire safety in purpose-built flats > Means of escape"


def test_page_furniture_is_not_captured() -> None:
    sections = parse_sections(GUIDANCE_HTML, title=TITLE)
    everything = " ".join(section.body for section in sections)

    assert "Home > Housing" not in everything
    assert "cookies" not in everything
    assert "analytics" not in everything
    assert "Open Government Licence" not in everything


def test_list_items_join_the_section_body() -> None:
    sections = parse_sections(GUIDANCE_HTML, title=TITLE)
    doors = next(section for section in sections if section.heading == "Fire doors")

    assert "Check the gaps." in doors.body
    assert "Check the seals." in doors.body


def test_table_cells_are_separated_in_reading_order() -> None:
    sections = parse_sections(GUIDANCE_HTML, title=TITLE)
    doors = next(section for section in sections if section.heading == "Fire doors")

    assert "Door type | Rating" in doors.body
    assert "Flat entrance | FD30S" in doors.body


def test_duplicate_headings_are_kept_as_separate_sections() -> None:
    notes = [
        section
        for section in parse_sections(GUIDANCE_HTML, title=TITLE)
        if section.heading == "Notes"
    ]

    assert len(notes) == 2
    assert [note.body for note in notes] == ["First note.", "Second note."]


def test_text_before_the_first_heading_becomes_the_introduction() -> None:
    sections = parse_sections(CONTENT_API_HTML, title=TITLE)

    assert sections[0].heading_path == TITLE


def test_a_page_without_a_title_or_headings_becomes_one_introduction() -> None:
    sections = parse_sections("<main><p>Only prose, no headings.</p></main>")

    assert len(sections) == 1
    assert sections[0].heading == "Introduction"


def test_an_empty_page_is_refused() -> None:
    with pytest.raises(EmptyDocument):
        parse_sections("<main>   </main>", title=TITLE)


def test_content_outside_the_main_element_is_ignored() -> None:
    sections = parse_sections(
        "<nav>Navigation</nav><main><h1>Real title</h1><p>Real body.</p></main>"
    )

    assert [section.heading for section in sections] == ["Real title"]
    assert "Navigation" not in sections[0].body
