from __future__ import annotations

import pytest

from firebrief.guardrails import Finding, Kind, redact


@pytest.mark.parametrize(
    ("text", "kind", "secret"),
    [
        ("email me at ada@example.com", Kind.EMAIL, "ada@example.com"),
        ("call 07700 900123", Kind.PHONE, "07700 900123"),
        ("call (0121) 496 0000", Kind.PHONE, "(0121) 496 0000"),
        ("call +44 (0)121 496 0000", Kind.PHONE, "+44 (0)121 496 0000"),
        ("call 07700.900.123", Kind.PHONE, "07700.900.123"),
        ("the flat is SW1A 2AA", Kind.POSTCODE, "SW1A 2AA"),
        ("NI AB123456C", Kind.NATIONAL_INSURANCE, "AB123456C"),
        ("NI ab123456c", Kind.NATIONAL_INSURANCE, "ab123456c"),
    ],
)
def test_each_pattern_is_redacted(text: str, kind: Kind, secret: str) -> None:
    result = redact(text)

    assert result.changed
    assert secret not in result.text
    assert f"[REDACTED:{kind.value}]" in result.text
    assert kind in {finding.kind for finding in result.findings}


@pytest.mark.parametrize(
    "card", ["4111 1111 1111 1111", "5555 5555 5555 4444", "4000 0566 5566 5556"]
)
def test_a_luhn_valid_card_is_redacted(card: str) -> None:
    result = redact(f"card {card} on file")

    assert card not in result.text
    assert "[REDACTED:card]" in result.text


def test_a_long_reference_number_that_fails_luhn_is_left_alone() -> None:
    reference = "1234 5678 9012 3456"

    result = redact(f"reference {reference}")

    assert result.findings == ()
    assert result.text == f"reference {reference}"


@pytest.mark.parametrize(
    "text",
    [
        "Dead ends must be limited in length to thirty metres.",
        "Flat entrance doors are marked FD30S.",
        "Systems should follow BS 5839.",
        "Doors are 1100mm wide and 2100mm high.",
        "Tested to BS EN 1634-1:2014.",
        "See BS 9991:2015 for guidance.",
        "A Category L1 system is required.",
        "Provide 30 minutes' fire resistance.",
        "Reviewed on 10/11/2026.",
        "Regulation 38 applies.",
        "SI 2005/1541 applies.",
    ],
)
def test_real_guidance_text_is_untouched(text: str) -> None:
    result = redact(text)

    assert not result.changed
    assert result.text == text


def test_findings_record_the_kind_and_count_but_not_the_value() -> None:
    result = redact("ada@example.com and grace@example.com")

    assert result.findings == (Finding(kind=Kind.EMAIL, count=2),)
    assert "ada" not in str(result.findings)
    assert "example.com" not in str(result.findings)
    assert result.text.count("[REDACTED:email]") == 2


def test_several_kinds_in_one_question() -> None:
    result = redact("I am ada@example.com at SW1A 2AA, call 07700 900123")

    assert result.findings == (
        Finding(kind=Kind.EMAIL, count=1),
        Finding(kind=Kind.PHONE, count=1),
        Finding(kind=Kind.POSTCODE, count=1),
    )


def test_text_without_personal_data_is_returned_unchanged() -> None:
    result = redact("Is a fire door required?")

    assert result.text == "Is a fire door required?"
    assert result.findings == ()
    assert not result.changed


@pytest.mark.parametrize(
    "phone",
    ["07700 900123", "(0121) 496 0000", "+44 (0)121 496 0000", "07700.900.123"],
)
def test_a_phone_number_is_replaced_whole(phone: str) -> None:
    """A stray bracket left behind would mean the pattern started in the wrong place."""
    assert redact(f"call {phone}").text == "call [REDACTED:phone]"


def test_a_card_starting_with_zero_is_a_card_not_a_phone() -> None:
    """Cards are checked first: a group starting 0 would otherwise match as a phone."""
    result = redact("card 4000 0566 5566 5556")

    assert result.findings == (Finding(kind=Kind.CARD, count=1),)
    assert result.text == "card [REDACTED:card]"


@pytest.mark.parametrize(
    "text",
    [
        "requirement B1 1st floor",
        "level L2 2nd floor",
        "room F2 3rd floor",
        "flat B4 4th floor",
    ],
)
def test_ordinals_are_not_postcodes(text: str) -> None:
    assert not redact(text).changed


def test_redaction_is_idempotent() -> None:
    once = redact("ada@example.com at SW1A 2AA")

    twice = redact(once.text)

    assert twice.text == once.text
    assert twice.findings == ()
