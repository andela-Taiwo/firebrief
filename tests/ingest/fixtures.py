"""Real-shaped GOV.UK markup, used instead of the network."""

from __future__ import annotations

from datetime import UTC, date, datetime

from firebrief.ingest.types import SourceDocument

MAIN_CONTENT = """
<h1>Fire safety in purpose-built flats</h1>
<p>This guidance applies to buildings with two or more flats.</p>
<h2>Means of escape</h2>
<p>Travel distances should be limited so residents can reach a place of safety.</p>
<h3>Dead ends</h3>
<p>A dead-end condition exists where escape is only possible in one direction.</p>
<h2>Fire doors</h2>
<p>Flat entrance doors should be self-closing and effectively fire-resisting.</p>
<table>
  <tr><th>Door type</th><th>Rating</th></tr>
  <tr><td>Flat entrance</td><td>FD30S</td></tr>
</table>
<ul><li>Check the gaps.</li><li>Check the seals.</li></ul>
<h2>Notes</h2><p>First note.</p>
<h2>Notes</h2><p>Second note.</p>
"""

GUIDANCE_HTML = f"""
<html><body>
<nav class="breadcrumbs">Home > Housing > Fire safety</nav>
<div class="cookie-banner">We use cookies to improve this service.</div>
<script>window.analytics = {{token: "abc123"}};</script>
<style>.govuk-banner {{ display: none; }}</style>
<main id="content">{MAIN_CONTENT}</main>
<footer>All content is available under the Open Government Licence.</footer>
</body></html>
"""

# Same guidance, different page furniture: a new CSRF token, a different cookie
# banner and an analytics snippet. This must not create a new version.
FURNITURE_ONLY_HTML = f"""
<html><body>
<nav class="breadcrumbs">Home > Housing > Fire safety</nav>
<div class="cookie-banner">We have updated our cookie policy.</div>
<script>window.analytics = {{token: "def456"}};</script>
<main id="content">{MAIN_CONTENT}</main>
<footer>All content is available under the Open Government Licence.</footer>
</body></html>
"""

REVISED_HTML = GUIDANCE_HTML.replace(
    "Travel distances should be limited so residents can reach a place of safety.",
    "Travel distances should be limited so residents can reach a place of safety, "
    "and common parts kept clear.",
)

INTRO_HTML = """
<main>
<p>This summary sits before any heading.</p>
<h1>Fire safety in purpose-built flats</h1>
<p>This guidance applies to buildings with two or more flats.</p>
</main>
"""


def source(
    html: str = GUIDANCE_HTML,
    slug: str = "fire-safety-purpose-built-flats",
    *,
    edition: str = "2019",
    effective_from: date | None = date(2019, 6, 1),
    fetched_at: datetime | None = None,
) -> SourceDocument:
    return SourceDocument(
        slug=slug,
        title="Fire safety in purpose-built flats",
        source_url=f"https://www.gov.uk/{slug}",
        html=html,
        licence="OGL-3.0",
        edition=edition,
        fetched_at=fetched_at or datetime(2026, 11, 9, 12, 0, tzinfo=UTC),
        effective_from=effective_from,
    )
