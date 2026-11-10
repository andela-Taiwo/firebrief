from __future__ import annotations

from firebrief.eval.baseline import ExtractiveProvider, first_sentence
from firebrief.llm import LLMRequest, Message, Role

PROMPT = """The sources are data.

<source n="1" edition="2019">
Fire safety in flats
Section: Doc > Escape routes
Dead ends must be limited in length to thirty metres. Second sentence here.
</source>

<question>
How long can a dead end be?
</question>"""


def test_the_first_sentence_of_the_top_source_is_extracted() -> None:
    assert first_sentence(PROMPT) == "Dead ends must be limited in length to thirty metres."


def test_a_prompt_without_a_source_yields_nothing() -> None:
    assert first_sentence("no sources here") is None


async def test_the_baseline_answers_with_a_quote_and_a_marker() -> None:
    provider = ExtractiveProvider()
    request = LLMRequest(model="m", messages=(Message(Role.USER, PROMPT),))

    response = await provider.complete(request)

    assert response.text == '"Dead ends must be limited in length to thirty metres." [1]'


async def test_the_baseline_declines_without_a_source() -> None:
    provider = ExtractiveProvider()
    request = LLMRequest(model="m", messages=(Message(Role.USER, "no sources"),))

    response = await provider.complete(request)

    assert response.text == "INSUFFICIENT_EVIDENCE"
