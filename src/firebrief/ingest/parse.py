"""Turn a guidance page into sections that follow its heading structure.

The parser is deliberately small: headings are the structure that matters for
citation, and a DOM library would be a dependency for a job this does not do
better. Text before the first heading is discarded — it is navigation, not
guidance.
"""

from __future__ import annotations

from html.parser import HTMLParser

from firebrief.ingest.types import ParsedSection

HEADING_TAGS = {"h1": 1, "h2": 2, "h3": 3, "h4": 4}
SKIP_TAGS = {"script", "style", "nav", "footer", "header"}


class EmptyDocument(Exception):
    """The page produced no sections, so there is nothing to cite."""


def _clean(parts: list[str]) -> str:
    return " ".join("".join(parts).split())


class _Extractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.sections: list[ParsedSection] = []
        self._path: list[tuple[int, str]] = []
        self._body: list[str] = []
        self._heading_level = 0
        self._heading: list[str] = []
        self._in_heading = False
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in SKIP_TAGS:
            self._skip_depth += 1
        elif tag in HEADING_TAGS:
            self._flush()
            self._in_heading = True
            self._heading_level = HEADING_TAGS[tag]
            self._heading = []
        elif tag == "br":
            self._body.append(" ")

    def handle_endtag(self, tag: str) -> None:
        if tag in SKIP_TAGS:
            self._skip_depth = max(0, self._skip_depth - 1)
        elif tag in HEADING_TAGS and self._in_heading:
            text = _clean(self._heading)
            if text:
                while self._path and self._path[-1][0] >= self._heading_level:
                    self._path.pop()
                self._path.append((self._heading_level, text))
            self._in_heading = False
            self._heading = []
        elif tag in ("p", "li", "div"):
            self._body.append(" ")

    def handle_data(self, data: str) -> None:
        if self._skip_depth:
            return
        if self._in_heading:
            self._heading.append(data)
        else:
            self._body.append(data)

    def close(self) -> None:
        super().close()
        self._flush()

    def _flush(self) -> None:
        body = _clean(self._body)
        self._body = []
        if not body or not self._path:
            return
        self.sections.append(
            ParsedSection(
                heading_path=" > ".join(text for _, text in self._path),
                heading=self._path[-1][1],
                body=body,
            )
        )


def parse_sections(html: str) -> list[ParsedSection]:
    parser = _Extractor()
    parser.feed(html)
    parser.close()
    if not parser.sections:
        raise EmptyDocument("the page produced no sections")
    return parser.sections
