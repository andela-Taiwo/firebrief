from __future__ import annotations

import pytest

from firebrief.guardrails import Kind, redact


@pytest.mark.parametrize(
    ("text", "kind"),
    [
        ("email me at ada@example.com", Kind.EMAIL),
        ("call 07700 900123", Kind.PHONE),
        ("call +44 7700 900123", Kind.PHONE),
        ("the flat is SW1A 2AA", Kind.POSTCODE),
        ("NI AB123456C", Kind.NATIONAL_INSURANCE),
        ("card 4111 1111 1111 1111", Kind.CARD),
    ],
)
def test_each_pattern_is_redacted(text: str, kind: Kind) -> None:
    result = redact(text)

    assert result.changed
    assert kind in {finding.kind for finding in result.findings}
    assert text not in result.text
    assert "[REDACTED:" in result.text


@pytest.mark.parametrize(
    "text",
    [
        "Dead ends must be limited in length to thirty metres.",
        "Flat entrance doors are marked FD30S.",
        "Systems should follow BS 5839.",
        "How long can a dead end be?",
    ],
)
def test_corpus_vocabulary_is_untouched(text: str) -> None:
    result = redact(text)

    assert not result.changed
    assert result.text == text


def test_findings_record_the_kind_and_count_but_not_the_value() -> None:
    result = redact("ada@example.com and grace@example.com")

    assert result.findings == (type(result.findings[0])(kind=Kind.EMAIL, count=2),)
    assert "ada" not in str(result.findings)
    assert "example.com" not in str(result.findings)
    assert result.text.count("[REDACTED:email]") == 2


def test_text_without_personal_data_is_returned_unchanged() -> None:
    result = redact("Is a fire door required?")

    assert result.text == "Is a fire door required?"
    assert result.findings == ()
    assert not result.changed
