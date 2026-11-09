"""Real-shaped GOV.UK markup, used instead of the network."""

from __future__ import annotations

from datetime import UTC, date, datetime

from firebrief.ingest.types import SourceDocument

GUIDANCE_HTML = """
<html><body>
<nav class="breadcrumbs">Home > Housing > Fire safety</nav>
<h1>Fire safety in purpose-built flats</h1>
<p>This guidance applies to buildings with two or more flats.</p>
<h2>Means of escape</h2>
<p>Travel distances should be limited so residents can reach a place of safety.</p>
<h3>Dead ends</h3>
<p>A dead-end condition exists where escape is only possible in one direction.</p>
<h2>Fire doors</h2>
<p>Flat entrance doors should be self-closing and effectively fire-resisting.</p>
<ul><li>Check the gaps.</li><li>Check the seals.</li></ul>
</body></html>
"""

REVISED_HTML = GUIDANCE_HTML.replace(
    "Travel distances should be limited so residents can reach a place of safety.",
    "Travel distances should be limited so residents can reach a place of safety, "
    "and common parts kept clear.",
)


def source(
    html: str = GUIDANCE_HTML, slug: str = "fire-safety-purpose-built-flats"
) -> SourceDocument:
    return SourceDocument(
        slug=slug,
        title="Fire safety in purpose-built flats",
        source_url=f"https://www.gov.uk/{slug}",
        html=html,
        licence="OGL-3.0",
        edition="2019",
        fetched_at=datetime(2026, 11, 9, 12, 0, tzinfo=UTC),
        effective_from=date(2019, 6, 1),
    )
