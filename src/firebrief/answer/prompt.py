"""The contract between the model and the verifier.

The verifier only accepts a verbatim quote of at least six words, attributed to the
marker that follows it. The prompt has to ask for exactly that, and nothing else in
quotation marks, or the model will produce answers that cannot be verified.
"""

from __future__ import annotations

from collections.abc import Sequence

from firebrief.retrieval.types import Retrieved

INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"

SYSTEM_PROMPT = """You answer questions about UK fire safety using ONLY the numbered sources.

Rules, without exception:
1. Every claim must end with one or more markers like [1].
2. Immediately before each marker, put a verbatim quote of at least six consecutive
   words from that source, in double quotation marks.
3. Use no ellipses inside a quote; quotes must be contiguous text from the source.
4. Use double quotation marks for evidence only — never for emphasis or terminology.
5. If the sources do not answer the question, reply with exactly: INSUFFICIENT_EVIDENCE

Do not use outside knowledge. Do not guess."""


def build_prompt(question: str, sources: Sequence[Retrieved]) -> tuple[str, str]:
    if not sources:
        raise ValueError("a prompt needs at least one source")

    lines: list[str] = ["Sources:"]
    for index, source in enumerate(sources, start=1):
        lines.append("")
        lines.append(f"[{index}] {source.document_title} (edition {source.edition})")
        lines.append(f"Section: {source.heading_path}")
        lines.append(source.text)
    lines.append("")
    lines.append(f"Question: {question}")
    return SYSTEM_PROMPT, "\n".join(lines)
