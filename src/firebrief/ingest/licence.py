"""Licence gate.

Only documents whose licence is on the allowlist are ingested. British Standards
and other copyrighted material are never fetched; if one is offered, this refuses
it by name rather than hoping nobody notices.
"""

from __future__ import annotations

ALLOWED_LICENCES: frozenset[str] = frozenset({"ogl-3.0", "ogl-2.0"})


class LicenceNotAccepted(Exception):
    """The document's licence is not one we may reuse."""


def normalise_licence(value: str) -> str:
    return value.strip().lower()


def check_licence(value: str) -> str:
    """Return the normalised licence or raise. Never silently downgrade."""
    normalised = normalise_licence(value)
    if normalised not in ALLOWED_LICENCES:
        raise LicenceNotAccepted(
            f"licence {value!r} is not accepted; allowed: {sorted(ALLOWED_LICENCES)}"
        )
    return normalised
