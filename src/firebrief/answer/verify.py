"""Check an answer against the passages it cites.

Claims are sentences. A marker is `[n]`, resolving to the n-th retrieved source
(1-based). A quoted passage is the evidence, and it is attributed to the marker that
follows it. The passage must appear in that source, as a contiguous run of words, and
the judge must agree it supports the claim.

Every failure path withholds. A judge that errors, a quote that is too short to prove
anything, a marker with no quote: all of them mean the answer is not shown.
"""

from __future__ import annotations

import logging
import re
import unicodedata
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass

from firebrief.answer.judge import SupportJudge
from firebrief.answer.types import ClaimCheck, ClaimResult, Status, Verdict, Verification
from firebrief.retrieval.types import Retrieved

MARKER = re.compile(r"\[(\d{1,3})\]")
QUOTE = re.compile(r'"([^"]+)"')
SENTENCE = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\"'])")
# Tokens are found in the ORIGINAL text, so offsets point at the original.
TOKEN = re.compile(r"[^\W_]+", re.UNICODE)

MIN_QUOTE_WORDS = 6
WINDOW_CHARS = 200

ABBREVIATION = re.compile(r"\b(e\.g|i\.e|approx|no|dr|mr|mrs|fig|para|section)\.", re.IGNORECASE)
TYPOGRAPHY = str.maketrans(
    {
        "\u2018": "'",
        "\u2019": "'",
        "\u201c": '"',
        "\u201d": '"',
        "\u2013": "-",
        "\u2014": "-",
        "\u2212": "-",
        "\u00a0": " ",
    }
)


logger = logging.getLogger(__name__)


def prepare(text: str) -> str:
    """NFKC, plain punctuation, then casefold. NOT length-preserving."""
    return unicodedata.normalize("NFKC", text).translate(TYPOGRAPHY).casefold()


def _normalise_token(token: str) -> str:
    return unicodedata.normalize("NFKC", token).casefold()


def normalise(text: str) -> str:
    return " ".join(prepare(text).split())


def tokens(text: str) -> list[tuple[str, int, int]]:
    """Tokens with offsets into `text` itself, each normalised individually.

    Normalising the whole string first would shift every offset after a ligature
    or a superscript, so the highlight and the judge's window would point at the
    wrong words.
    """
    return [
        (_normalise_token(match.group()), match.start(), match.end())
        for match in TOKEN.finditer(text)
    ]


def find_span(source_text: str, quote: str) -> tuple[int, int] | None:
    """Locate the quote as a contiguous run of words, returning character offsets."""
    wanted = [word for word, _, _ in tokens(quote)]
    if not wanted:
        return None
    available = tokens(source_text)
    width = len(wanted)
    for start in range(len(available) - width + 1):
        if [word for word, _, _ in available[start : start + width]] == wanted:
            end = available[start + width - 1][2]
            # Include trailing punctuation that the quote itself ends with, so the
            # span covers the passage rather than stopping at its last word.
            tail = quote.rstrip()
            while tail and not tail[-1].isalnum():
                if end < len(source_text) and source_text[end] == tail[-1]:
                    end += 1
                    tail = tail[:-1]
                else:
                    break
            return available[start][1], end
    return None


def _mask_quotes(text: str) -> tuple[str, list[str]]:
    quotes: list[str] = []

    def replace(match: re.Match[str]) -> str:
        quotes.append(match.group(1))
        return f"\x00{len(quotes) - 1}\x00"

    return QUOTE.sub(replace, text), quotes


def _split_sentences(text: str) -> list[str]:
    """Split on sentence ends, but never inside a quotation or an abbreviation."""
    masked, quotes = _mask_quotes(text.translate(TYPOGRAPHY))
    masked = ABBREVIATION.sub(lambda match: match.group(0)[:-1] + "\x01", masked)
    parts = [part for part in SENTENCE.split(masked) if part.strip()]
    restored: list[str] = []
    for part in parts:
        for index, quote in enumerate(quotes):
            part = part.replace(f"\x00{index}\x00", f'"{quote}"')
        restored.append(part.replace("\x01", "."))
    return restored


@dataclass(frozen=True, slots=True)
class Claim:
    text: str
    markers: tuple[int, ...]
    quotes: tuple[tuple[int | None, str], ...]


def parse_claims(answer: str) -> list[Claim]:
    claims: list[Claim] = []
    for sentence in _split_sentences(answer.strip()):
        if not sentence.strip():
            continue
        plain = sentence.translate(TYPOGRAPHY)
        markers = [(match.start(), int(match.group(1))) for match in MARKER.finditer(plain)]
        quotes: list[tuple[int | None, str]] = []
        for match in QUOTE.finditer(plain):
            after = [number for position, number in markers if position >= match.end()]
            before = [number for position, number in markers if position < match.start()]
            marker = after[0] if after else (before[-1] if before else None)
            quotes.append((marker, match.group(1).strip()))
        text = QUOTE.sub("", MARKER.sub("", plain)).strip()
        claims.append(
            Claim(
                text=text,
                markers=tuple(number for _, number in markers),
                quotes=tuple(quotes),
            )
        )
    return claims


def _window(source_text: str, span: tuple[int, int]) -> str:
    start = max(0, span[0] - WINDOW_CHARS)
    end = min(len(source_text), span[1] + WINDOW_CHARS)
    return source_text[start:end]


async def verify_answer(
    answer: str,
    sources: Sequence[Retrieved],
    *,
    judge: SupportJudge,
) -> Verification:
    results: list[ClaimResult] = []

    for claim in parse_claims(answer):
        if not claim.markers:
            results.append(
                ClaimResult(
                    text=claim.text,
                    checks=(ClaimCheck(marker=None, chunk_id=None, status=Status.UNCITED),),
                )
            )
            continue

        checks: list[ClaimCheck] = []
        # Every occurrence of a marker needs its own quote: [1][2] with one quote,
        # or [1][1], is under-cited and must not verify.
        available = Counter(marker for marker, _ in claim.quotes if marker is not None)
        for marker in claim.markers:
            if available.get(marker, 0) > 0:
                available[marker] -= 1
            else:
                checks.append(ClaimCheck(marker=marker, chunk_id=None, status=Status.MISSING_SPAN))

        for marker, quote in claim.quotes:
            if marker is None:  # unreachable: a claim with a marker attributes every quote
                continue
            if marker < 1 or marker > len(sources):
                checks.append(
                    ClaimCheck(
                        marker=marker, chunk_id=None, status=Status.UNKNOWN_MARKER, quote=quote
                    )
                )
                continue
            if len(tokens(quote)) < MIN_QUOTE_WORDS:
                checks.append(
                    ClaimCheck(
                        marker=marker,
                        chunk_id=sources[marker - 1].chunk_id,
                        status=Status.QUOTE_TOO_SHORT,
                        quote=quote,
                    )
                )
                continue

            source = sources[marker - 1]
            span = find_span(source.text, quote)
            if span is None:
                checks.append(
                    ClaimCheck(
                        marker=marker,
                        chunk_id=source.chunk_id,
                        section_id=source.section_id,
                        version_id=source.version_id,
                        status=Status.MISSING_SPAN,
                        quote=quote,
                    )
                )
                continue

            status = Status.VERIFIED
            error: str | None = None
            try:
                supported = await judge.supports(claim.text, quote, _window(source.text, span))
            except Exception as exc:
                status = Status.JUDGE_ERROR
                error = type(exc).__name__
                logger.warning("citation judge failed for chunk %s: %s", source.chunk_id, error)
            else:
                if not supported:
                    status = Status.UNSUPPORTED

            checks.append(
                ClaimCheck(
                    marker=marker,
                    chunk_id=source.chunk_id,
                    section_id=source.section_id,
                    version_id=source.version_id,
                    status=status,
                    quote=quote,
                    char_start=span[0],
                    char_end=span[1],
                    error=error,
                )
            )

        results.append(ClaimResult(text=claim.text, checks=tuple(checks)))

    verdict = (
        Verdict.VERIFIED
        if results and all(result.verified for result in results)
        else Verdict.WITHHELD
    )
    return Verification(
        claims=tuple(results),
        verdict=verdict,
        judge_model=judge.model,
        judge_prompt_version=judge.prompt_version,
    )
