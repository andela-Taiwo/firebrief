"""Conservative, provider-independent token estimation.

A network tokeniser on the hot path is a dependency and a failure mode, so the
estimate is deliberately simple and pessimistic: about one token per three
characters, plus per-message overhead. It is reconciled against the provider's
exact counts when the call settles.
"""

from __future__ import annotations

from collections.abc import Sequence

from firebrief.budget.money import ceil_div

CHARS_PER_TOKEN = 3
PER_MESSAGE_OVERHEAD = 4
PROMPT_OVERHEAD = 3

__all__ = ["estimate_prompt_tokens", "estimate_tokens"]


def estimate_tokens(text: str) -> int:
    """Estimate tokens for a single string. Never returns less than one."""
    if not text:
        return 1
    return max(1, ceil_div(len(text), CHARS_PER_TOKEN))


def estimate_prompt_tokens(contents: Sequence[str]) -> int:
    """Estimate the prompt size for a sequence of message bodies."""
    return PROMPT_OVERHEAD + sum(
        estimate_tokens(content) + PER_MESSAGE_OVERHEAD for content in contents
    )
