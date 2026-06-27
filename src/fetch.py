from __future__ import annotations

import re
import urllib.parse
import urllib.request
from html.parser import HTMLParser

try:
    from .common import PIB_URL, NewsItem, clean_text
    from .directlink import resolve_direct_url
except ImportError:  # Allows running src/main.py directly.
    from common import PIB_URL, NewsItem, clean_text
    from directlink import resolve_direct_url


class LinkParser(HTMLParser):
    """Collect news links from the PIB regional listing page."""

    def __init__(self) -> None:
        super().__init__()
        self.links: list[NewsItem] = []
        self._href: str | None = None
        self._text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "a":
            return
        attrs_map = dict(attrs)
        href = attrs_map.get("href")
        if href:
            self._href = href
            self._text = []

    def handle_data(self, data: str) -> None:
        if self._href:
            self._text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() != "a" or not self._href:
            return
        title = clean_text(" ".join(self._text))
        if is_news_link(self._href) and is_news_title(title):
            self.links.append(NewsItem(title=title, url=absolute_url(self._href)))
        self._href = None
        self._text = []


def is_news_title(title: str) -> bool:
    if len(title) < 35:
        return False
    lowered = title.lower()
    rejected = (
        "skip to main",
        "screen reader",
        "press information bureau",
        "ministry",
        "archive",
        "home",
        "contact",
    )
    return not any(bit in lowered for bit in rejected)


def is_news_link(href: str) -> bool:
    lowered = href.lower()
    return "pressreleasedetail.aspx" in lowered and "prid=" in lowered


def absolute_url(href: str) -> str:
    return urllib.parse.urljoin(PIB_URL, href)


def fetch_text(url: str) -> str:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/126.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": "https://www.pib.gov.in/",
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        raw = response.read()
        content_type = response.headers.get("content-type", "")
    charset = "utf-8"
    match = re.search(r"charset=([\w-]+)", content_type, flags=re.I)
    if match:
        charset = match.group(1)
    return raw.decode(charset, errors="replace")


def collect_items(limit: int, resolve_links: bool = True) -> list[NewsItem]:
    """Fetch PIB listing links and return unique items.

    The generated posts must link to directly openable article URLs.  Therefore
    links are resolved after extraction, while preserving the original Jekyll
    output directory logic elsewhere.
    """

    parser = LinkParser()
    parser.feed(fetch_text(PIB_URL))
    seen: set[str] = set()
    items: list[NewsItem] = []
    for item in parser.links:
        key = item.title.lower()
        if key in seen:
            continue
        seen.add(key)
        if resolve_links:
            item = NewsItem(title=item.title, url=resolve_direct_url(item.url), date=item.date)
        items.append(item)
        if len(items) >= limit:
            break
    return items
