"""A provider that quotes instead of reasoning.

It reads the first sentence of the best source and cites it. No key, no cost, fully
deterministic — useful for local development and as a floor to compare a real model against.
It cannot answer anything the guidance does not say outright, which is exactly its limit.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from firebrief.llm.base import LLMRequest, LLMResponse
from firebrief.llm.types import Usage

SOURCE_BLOCK = re.compile(r'<source n="1"[^>]*>\n(.*?)\n</source>', re.DOTALL)
SENTENCE_END = re.compile(r"(?<=[.!?])\s+")


def first_sentence(prompt: str) -> str | None:
    match = SOURCE_BLOCK.search(prompt)
    if match is None:
        return None
    lines = match.group(1).splitlines()
    # The first line is the document title, then a "Section:" line, then the text.
    body = " ".join(line for line in lines[1:] if not line.startswith("Section:") and line.strip())
    if not body.strip():
        return None
    return SENTENCE_END.split(body.strip())[0].strip()


@dataclass
class ExtractiveProvider:
    model: str = "extractive"
    name: str = "extractive"

    async def complete(self, request: LLMRequest) -> LLMResponse:
        sentence = first_sentence(request.messages[-1].content)
        text = "INSUFFICIENT_EVIDENCE" if sentence is None else f'"{sentence}" [1]'
        return LLMResponse(
            text=text,
            usage=Usage(0, 0),
            model=self.model,
            provider=self.name,
            finish_reason="stop",
        )
