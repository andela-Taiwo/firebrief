"""Check an answer against the passages it cites.

Claims are sentences. A marker is `[n]`, resolving to the n-th retrieved source
(1-based). A quoted passage is the evidence. The passage must appear in the cited
chunk, so a citation to something that is not there withholds the answer.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass

from firebrief.answer.judge import SupportJudge
from firebrief.answer.types import ClaimCheck, ClaimResult, Status, Verdict, Verification
from firebrief.retrieval.types import Retrieved

MARKER = re.compile(r"\[(\d{1,3})\]")
QUOTE = re.compile(r"[\"“]([^\"”]+)[\"”]")
SENTENCE = re.compile(r"(?<=[.!?])\s+")


@dataclass(frozen=True, slots=True)
class Claim:
    text: str
    markers: tuple[int, ...]
    quotes: tuple[str, ...]


def normalise(text: str) -> str:
    """Case and whitespace are not evidence: collapse both before comparing."""
    return " ".join(text.casefold().split())


def _merge_marker_only_segments(segments: list[str]) -> list[str]:
    """Attach a trailing "[1]" or a bare quote to the claim before it.

    Models write "Claim. [1]" as often as "Claim [1]."; the marker belongs to the
    sentence it follows, not to a claim of its own.
    """
    merged: list[str] = []
    for segment in segments:
        bare = QUOTE.sub("", MARKER.sub("", segment))
        if merged and not re.search(r"[A-Za-z0-9]", bare):
            merged[-1] = f"{merged[-1].rstrip()} {segment.strip()}"
        else:
            merged.append(segment)
    return merged


def parse_claims(answer: str) -> list[Claim]:
    claims: list[Claim] = []
    segments = [part for part in SENTENCE.split(answer.strip()) if part.strip()]
    for sentence in _merge_marker_only_segments(segments):
        markers = tuple(int(match) for match in MARKER.findall(sentence))
        quotes = tuple(match.strip() for match in QUOTE.findall(sentence))
        text = MARKER.sub("", sentence).strip()
        claims.append(Claim(text=text, markers=markers, quotes=quotes))
    return claims


async def verify_answer(
    answer: str,
    sources: Sequence[Retrieved],
    *,
    judge: SupportJudge | None = None,
) -> Verification:
    claims = parse_claims(answer)
    results: list[ClaimResult] = []

    for claim in claims:
        if not claim.markers:
            results.append(
                ClaimResult(
                    text=claim.text,
                    checks=(ClaimCheck(marker=None, chunk_id=None, status=Status.UNCITED),),
                )
            )
            continue

        checks: list[ClaimCheck] = []
        for marker in claim.markers:
            if marker < 1 or marker > len(sources):
                checks.append(
                    ClaimCheck(marker=marker, chunk_id=None, status=Status.UNKNOWN_MARKER)
                )
                continue

            source = sources[marker - 1]
            if not claim.quotes:
                checks.append(
                    ClaimCheck(marker=marker, chunk_id=source.chunk_id, status=Status.MISSING_SPAN)
                )
                continue

            for quote in claim.quotes:
                found = normalise(quote) in normalise(source.text)
                status = Status.VERIFIED if found else Status.MISSING_SPAN
                if (
                    status is Status.VERIFIED
                    and judge is not None
                    and not await judge.supports(claim.text, source.text)
                ):
                    status = Status.UNSUPPORTED
                checks.append(
                    ClaimCheck(marker=marker, chunk_id=source.chunk_id, status=status, quote=quote)
                )

        results.append(ClaimResult(text=claim.text, checks=tuple(checks)))

    verdict = (
        Verdict.VERIFIED
        if results and all(result.verified for result in results)
        else Verdict.WITHHELD
    )
    return Verification(claims=tuple(results), verdict=verdict)
