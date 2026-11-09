"""Which version should answer a question asked on a given date.

There is no `effective_to`: you only learn that an edition has ended when its
successor arrives, and versions are immutable. So the version in force on a date
is the one with the latest `effective_from` at or before that date, with
`fetched_at` breaking ties between corrections of the same edition.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date

from firebrief.db.models import DocumentVersion


def select_current(versions: Sequence[DocumentVersion], *, as_of: date) -> DocumentVersion | None:
    eligible = [
        version
        for version in versions
        if version.effective_from is None or version.effective_from <= as_of
    ]
    if not eligible:
        return None
    return max(
        eligible,
        key=lambda version: (version.effective_from or date.min, version.fetched_at),
    )
