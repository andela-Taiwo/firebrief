"""An extractive baseline: quote the first sentence of the top source.

No model, no key, deterministic. It is the floor a real model has to beat, and it gives
the harness something honest to report before any provider is configured.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from firebrief.llm import LLMRequest, LLMResponse, Usage

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
    model: str = "extractive-baseline"
    name: str = "baseline"

    async def complete(self, request: LLMRequest) -> LLMResponse:
        prompt = request.messages[-1].content
        sentence = first_sentence(prompt)
        if sentence is None:
            return LLMResponse(
                text="INSUFFICIENT_EVIDENCE",
                usage=Usage(0, 0),
                model=self.model,
                provider=self.name,
                finish_reason="stop",
            )
        return LLMResponse(
            text=f'"{sentence}" [1]',
            usage=Usage(0, 0),
            model=self.model,
            provider=self.name,
            finish_reason="stop",
        )
