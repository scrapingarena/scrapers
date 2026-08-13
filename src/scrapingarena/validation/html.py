from __future__ import annotations

from html.parser import HTMLParser


class VisibleTextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._hidden_depth = 0
        self._parts: list[str] = []
        self.title = ""
        self._in_title = False

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        del attrs
        if tag in {"script", "style", "noscript", "svg", "template"}:
            self._hidden_depth += 1
        if tag == "title":
            self._in_title = True

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript", "svg", "template"}:
            self._hidden_depth = max(0, self._hidden_depth - 1)
        if tag == "title":
            self._in_title = False

    def handle_data(self, data: str) -> None:
        value = " ".join(data.split())
        if not value:
            return
        if self._in_title:
            self.title = f"{self.title} {value}".strip()
        if self._hidden_depth == 0:
            self._parts.append(value)

    @property
    def text(self) -> str:
        return " ".join(self._parts)


def extract_visible_text(html: str) -> tuple[str, str]:
    parser = VisibleTextParser()
    try:
        parser.feed(html)
        parser.close()
    except (AssertionError, ValueError):
        # Malformed markup is common on challenge pages. Returning the text
        # collected so far is more useful than failing validation.
        pass
    return parser.title, parser.text
