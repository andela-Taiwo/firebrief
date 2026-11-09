"""Turn a guidance page into sections that follow its heading structure.

Only the main content is read: GOV.UK wraps it in <main>, and everything outside
it is navigation, cookie banners and footers. Text before the first heading inside
the main content becomes an introduction rather than being dropped, because on
real pages it is often the summary a reader needs.

Headings are the structure that matters for citation, so a section is a heading
plus the text beneath it, and it keeps the path that reached it.
"""

from __future__ import annotations

from html.parser import HTMLParser

from firebrief.ingest.types import ParsedSection

HEADING_TAGS = {"h1": 1, "h2": 2, "h3": 3, "h4": 4}
SKIP_TAGS = {"script", "style", "nav", "footer", "header", "form", "noscript"}
CELL_END_TAGS = {"td", "th"}
INTRO_HEADING = "Introduction"


class EmptyDocument(Exception):
    """The page produced no sections, so there is nothing to cite."""


def _clean(parts: list[str]) -> str:
    return " ".join("".join(parts).split())


class _Extractor(HTMLParser):
    def __init__(self, title: str | None, require_main: bool) -> None:
        super().__init__(convert_charrefs=True)
        self.sections: list[ParsedSection] = []
        self._title = title
        self._require_main = require_main
        self._main_depth = 0
        self._path: list[tuple[int, str]] = []
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
            text = _clean(self._heading)
            if text:
                while self._path and self._path[-1][0] >= self._heading_level:
                    self._path.pop()
                self._path.append((self._heading_level, text))
            self._in_heading = False
            self._heading = []
        elif tag in CELL_END_TAGS:
            self._body.append(" | ")

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
        body = _clean(self._body).replace(" | | ", " | ") if self._body else ""
        self._body = []
        if not body:
            return
        if self._path:
            heading_path = " > ".join(text for _, text in self._path)
            heading = self._path[-1][1]
        else:
            heading_path = self._title or INTRO_HEADING
            heading = heading_path
        self.sections.append(ParsedSection(heading_path=heading_path, heading=heading, body=body))


def parse_sections(html: str, *, title: str | None = None) -> list[ParsedSection]:
    """Parse the main content into sections, in reading order."""
    parser = _Extractor(title=title, require_main="<main" in html.lower())
    parser.feed(html)
    parser.close()
    if not parser.sections:
        raise EmptyDocument("the page produced no sections")
    return parser.sections
