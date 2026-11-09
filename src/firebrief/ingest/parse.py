"""Turn a guidance page into sections that follow its heading structure.

Two shapes matter. A rendered GOV.UK page has an h1 and wraps content in <main>.
A Content API body is govspeak without an h1: the title is a separate field, and
the body often opens with paragraphs before the first h2. So the title seeds the
heading path, and text before the first heading becomes an introduction rather
than being dropped.

Tables matter for fire guidance, so cell and row boundaries are kept.
"""

from __future__ import annotations

import re
from html.parser import HTMLParser

from firebrief.ingest.types import ParsedSection

HEADING_TAGS = {"h1": 1, "h2": 2, "h3": 3, "h4": 4}
SKIP_TAGS = {"script", "style", "nav", "footer", "header", "form", "noscript"}
BLOCK_TAGS = {"p", "li", "div", "tr", "dt", "dd", "h5", "h6", "table", "ul", "ol"}
CELL_TAGS = {"td", "th"}
INTRO_HEADING = "Introduction"
MAIN_TAG = re.compile(r"<main[\s>]", re.IGNORECASE)

CELL_SEPARATOR = " | "
BLOCK_SEPARATOR = " "


class EmptyDocument(Exception):
    """The page produced no sections, so there is nothing to cite."""


def _tidy(text: str) -> str:
    collapsed = " ".join(text.split())
    while " | |" in collapsed:
        collapsed = collapsed.replace(" | |", " |")
    return collapsed.strip(" |")


class _Extractor(HTMLParser):
    def __init__(self, title: str | None, require_main: bool) -> None:
        super().__init__(convert_charrefs=True)
        self.sections: list[ParsedSection] = []
        self._require_main = require_main
        self._main_depth = 0
        # The title is the root of every heading path, so a content-API body that
        # starts at h2 still cites as "Title > Section".
        self._path: list[tuple[int, str]] = [(0, title)] if title else []
        self._body: list[str] = []
        self._heading_level = 0
        self._heading: list[str] = []
        self._in_heading = False
        self._skip_depth = 0

    @property
    def _capturing(self) -> bool:
        return not self._require_main or self._main_depth > 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "main":
            self._main_depth += 1
        elif tag in SKIP_TAGS:
            self._skip_depth += 1
        elif tag == "br":
            self._body.append(BLOCK_SEPARATOR)
        elif tag in HEADING_TAGS and self._capturing:
            self._flush()
            self._in_heading = True
            self._heading_level = HEADING_TAGS[tag]
            self._heading = []

    def handle_endtag(self, tag: str) -> None:
        if tag == "main":
            self._main_depth = max(0, self._main_depth - 1)
        elif tag in SKIP_TAGS:
            self._skip_depth = max(0, self._skip_depth - 1)
        elif tag in HEADING_TAGS and self._in_heading:
            text = _tidy("".join(self._heading))
            if text:
                # A rendered page repeats the title as its h1; do not cite it twice.
                if len(self._path) == 1 and self._path[0][0] == 0 and self._path[0][1] == text:
                    self._path = [(self._heading_level, text)]
                else:
                    while self._path and self._path[-1][0] >= self._heading_level:
                        self._path.pop()
                    self._path.append((self._heading_level, text))
            self._in_heading = False
            self._heading = []
        elif tag in CELL_TAGS:
            self._body.append(CELL_SEPARATOR)
        elif tag in BLOCK_TAGS:
            self._body.append(BLOCK_SEPARATOR)

    def handle_data(self, data: str) -> None:
        if self._skip_depth or not self._capturing:
            return
        if self._in_heading:
            self._heading.append(data)
        else:
            self._body.append(data)

    def close(self) -> None:
        super().close()
        self._flush()

    def _flush(self) -> None:
        body = _tidy("".join(self._body))
        self._body = []
        if not body:
            return
        if self._path:
            heading_path = " > ".join(text for _, text in self._path)
            heading = self._path[-1][1]
        else:
            heading_path = INTRO_HEADING
            heading = INTRO_HEADING
        self.sections.append(ParsedSection(heading_path=heading_path, heading=heading, body=body))


def parse_sections(html: str, *, title: str | None = None) -> list[ParsedSection]:
    """Parse the main content into sections, in reading order."""
    parser = _Extractor(title=title, require_main=bool(MAIN_TAG.search(html)))
    parser.feed(html)
    parser.close()
    if not parser.sections:
        raise EmptyDocument("the page produced no sections")
    return parser.sections
