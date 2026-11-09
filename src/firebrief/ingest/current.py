"""Which version should answer a question asked on a given date.

The rule is explicit and testable: among versions in force on that date, the one
with the latest `effective_from` wins, and `fetched_at` breaks the tie. A version
with no `effective_from` is treated as always having been in force.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date

from firebrief.db.models import DocumentVersion


def select_current(versions: Sequence[DocumentVersion], *, as_of: date) -> DocumentVersion | None:
    eligible = [
        version
        for version in versions
        if (version.effective_from is None or version.effective_from <= as_of)
        and (version.effective_to is None or version.effective_to >= as_of)
    ]
    if not eligible:
        return None
    return max(
        eligible,
        key=lambda version: (version.effective_from or date.min, version.fetched_at),
    )
