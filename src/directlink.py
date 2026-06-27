from __future__ import annotations

"""Resolve RSS/redirect/listing links into direct article links.

The generated PIB digest must publish browser-openable article links, not
temporary RSS/redirect links.  This module follows redirects and inspects the
final HTML page when needed, but it treats PIB links carefully.

Important PIB rule
------------------
Do NOT force a PIB URL from::

    PressReleaseDetail.aspx?PRID=...

into::

    PressReleasePage.aspx?PRID=...

For many PIB releases the forced ``PressReleasePage.aspx`` form produces
"The specified URL cannot be found".  The stable, directly openable link for
this project is the PIB detail URL itself, cleaned and preserved as::

    https://www.pib.gov.in/PressReleaseDetail.aspx?PRID=...&lang=1&reg=48

Public functions
----------------
resolve_direct_url(url)
    Return the best direct article URL for one source/RSS/redirect URL.

resolve_direct_link(url)
    Backward-compatible alias for resolve_direct_url(url).

resolve_direct_links_for_items(items)
    Add a ``direct_link`` field to dictionaries that contain a ``link`` field.

choose_best_link(item)
    Helper for markdown generation when working with dictionaries.
"""

import re
import urllib.parse
import urllib.request
from collections.abc import Iterable, Mapping
from typing import Any

PIB_BASE = "https://www.pib.gov.in/"
DEFAULT_LANG = "1"
DEFAULT_REG = "48"
TRACKING_KEYS = {"fbclid", "gclid", "mc_cid", "mc_eid", "igshid"}
TARGET_QUERY_KEYS = (
    "url",
    "u",
    "target",
    "redirect",
    "redirect_url",
    "destination",
    "dest",
    "link",
)


def _request(url: str, method: str = "GET") -> urllib.request.Request:
    return urllib.request.Request(
        url,
        method=method,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/126.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-IN,en;q=0.9,hi;q=0.8",
            "Referer": PIB_BASE,
        },
    )


def _safe_unescape(url: str) -> str:
    """Decode common HTML entity separators without corrupting ``&reg``.

    ``html.unescape`` converts ``&reg`` into the registered-trademark symbol
    when a feed accidentally writes ``...PRID=123&reg=48``.  That breaks PIB
    URLs.  Therefore only the known ampersand encodings are replaced.
    """

    return (
        (url or "")
        .strip()
        .replace("&amp;", "&")
        .replace("&#38;", "&")
        .replace("&#x26;", "&")
        .replace("&#X26;", "&")
    )


def normalize_url(url: str) -> str:
    """Return an absolute URL with fragments and tracking parameters removed."""

    url = _safe_unescape(url)
    if not url:
        return ""

    parsed = urllib.parse.urlsplit(url)
    if not parsed.scheme:
        url = urllib.parse.urljoin(PIB_BASE, url)
        parsed = urllib.parse.urlsplit(url)

    scheme = parsed.scheme or "https"
    netloc = parsed.netloc
    if netloc.lower() == "pib.gov.in":
        netloc = "www.pib.gov.in"

    kept: list[tuple[str, str]] = []
    for key, value in urllib.parse.parse_qsl(parsed.query, keep_blank_values=True):
        lowered = key.lower()
        if lowered.startswith("utm_") or lowered in TRACKING_KEYS:
            continue
        kept.append((key, value))

    clean_query = urllib.parse.urlencode(kept, doseq=True)
    return urllib.parse.urlunsplit((scheme, netloc, parsed.path, clean_query, ""))


def _query_pairs(url: str) -> list[tuple[str, str]]:
    parsed = urllib.parse.urlsplit(normalize_url(url))
    return urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)


def _query_map(url: str) -> dict[str, str]:
    return {k.lower(): v for k, v in _query_pairs(url)}


def _first_nonempty(*values: str | None, default: str) -> str:
    for value in values:
        if value:
            return value
    return default


def _is_http_url(url: str) -> bool:
    parsed = urllib.parse.urlsplit(url)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def extract_embedded_target(url: str) -> str | None:
    """Return a real article URL embedded inside a redirect query string.

    Some RSS/redirect URLs carry the article as ``?url=...`` or ``?target=...``.
    When such a value exists, it is more reliable than opening the redirector.
    """

    q = urllib.parse.parse_qs(urllib.parse.urlsplit(normalize_url(url)).query)
    for key in TARGET_QUERY_KEYS:
        values = q.get(key)
        if not values:
            continue
        candidate = normalize_url(urllib.parse.unquote(values[0]))
        if _is_http_url(candidate):
            return candidate
    return None


def pib_direct_url(url: str) -> str | None:
    """Return a safe direct PIB URL when the input contains PIB identifiers.

    For normal PIB press releases this preserves ``PressReleaseDetail.aspx``.
    For PIB note/backgrounder pages it preserves ``PressNoteDetails.aspx``.
    """

    clean = normalize_url(url)
    if not clean:
        return None

    parsed = urllib.parse.urlsplit(clean)
    host = parsed.netloc.lower()
    if host not in {"pib.gov.in", "www.pib.gov.in"}:
        return None

    q = _query_map(clean)
    path = parsed.path.lower()
    lang = _first_nonempty(q.get("lang"), q.get("language"), default=DEFAULT_LANG)
    reg = _first_nonempty(q.get("reg"), default=DEFAULT_REG)

    prid = q.get("prid")
    if prid and ("pressreleasedetail" in path or "pressrelesedetail" in path or "pressreleasepage" in path):
        query = urllib.parse.urlencode((
            ("PRID", prid),
            ("lang", lang),
            ("reg", reg),
        ))
        return f"{PIB_BASE}PressReleaseDetail.aspx?{query}"

    note_id = q.get("noteid") or q.get("id")
    module_id = q.get("moduleid")
    if "pressnotedetails.aspx" in path and note_id:
        pairs: list[tuple[str, str]] = []
        if module_id:
            pairs.append(("ModuleId", module_id))
        pairs.extend((("NoteId", note_id), ("lang", lang), ("reg", reg)))
        return f"{PIB_BASE}PressNoteDetails.aspx?{urllib.parse.urlencode(pairs)}"

    return None


def follow_redirects(url: str) -> str:
    """Open a URL and return the final HTTP redirect target.

    If the network fails or the site blocks automated access, the normalized
    input URL is returned so the generator can continue.
    """

    url = normalize_url(url)
    if not url:
        return ""

    for method in ("HEAD", "GET"):
        try:
            with urllib.request.urlopen(_request(url, method=method), timeout=20) as response:
                return normalize_url(response.geturl())
        except Exception:
            continue
    return url


def _extract_canonical(html_text: str, base_url: str) -> str | None:
    patterns = [
        r'<link[^>]+rel=["\']canonical["\'][^>]+href=["\']([^"\']+)["\']',
        r'<link[^>]+href=["\']([^"\']+)["\'][^>]+rel=["\']canonical["\']',
        r'<meta[^>]+property=["\']og:url["\'][^>]+content=["\']([^"\']+)["\']',
        r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:url["\']',
    ]
    for pattern in patterns:
        match = re.search(pattern, html_text, flags=re.I)
        if match:
            return normalize_url(urllib.parse.urljoin(base_url, match.group(1)))
    return None


def _extract_meta_refresh(html_text: str, base_url: str) -> str | None:
    match = re.search(
        r'<meta[^>]+http-equiv=["\']?refresh["\']?[^>]+content=["\'][^"\']*url\s*=\s*([^"\';>]+)',
        html_text,
        flags=re.I,
    )
    if not match:
        return None
    return normalize_url(urllib.parse.urljoin(base_url, match.group(1).strip()))


def _looks_like_article_url(url: str) -> bool:
    if not url:
        return False

    clean = normalize_url(url)
    parsed = urllib.parse.urlsplit(clean)
    path = parsed.path.lower()
    q = _query_map(clean)

    if parsed.netloc.lower() in {"pib.gov.in", "www.pib.gov.in"}:
        if ("pressreleasedetail" in path or "pressrelesedetail" in path) and q.get("prid"):
            return True
        if "pressnotedetails.aspx" in path and (q.get("noteid") or q.get("id")):
            return True
        return False

    bad_bits = ("/rss", "/feed", "news.google.com/rss", "?output=rss")
    return parsed.scheme in {"http", "https"} and not any(bit in clean.lower() for bit in bad_bits)


def resolve_direct_url(url: str) -> str:
    """Resolve one RSS/indirect/source URL to a direct article URL.

    Resolution order:
    1. Clean the URL.
    2. Extract embedded target URL from redirect query parameters.
    3. Preserve safe PIB PRID/NoteId URLs without converting the endpoint.
    4. Follow HTTP redirects.
    5. Inspect canonical/OG/meta-refresh links from the final HTML page.
    6. Fall back to the best normalized URL.
    """

    clean = normalize_url(url)
    if not clean:
        return ""

    embedded = extract_embedded_target(clean)
    if embedded:
        return pib_direct_url(embedded) or embedded

    direct = pib_direct_url(clean)
    if direct:
        return direct

    final_url = follow_redirects(clean)
    final_direct = pib_direct_url(final_url)
    if final_direct:
        return final_direct

    try:
        with urllib.request.urlopen(_request(final_url, method="GET"), timeout=20) as response:
            page_url = normalize_url(response.geturl())
            content_type = response.headers.get("content-type", "")
            if "html" not in content_type.lower():
                return page_url if _looks_like_article_url(page_url) else final_url
            raw = response.read(250_000)
    except Exception:
        return final_url

    text = raw.decode("utf-8", errors="replace")

    canonical = _extract_canonical(text, page_url)
    if canonical:
        canonical_direct = pib_direct_url(canonical)
        if canonical_direct:
            return canonical_direct
        if _looks_like_article_url(canonical):
            return canonical

    refresh = _extract_meta_refresh(text, page_url)
    if refresh:
        refresh_direct = pib_direct_url(refresh)
        if refresh_direct:
            return refresh_direct
        return follow_redirects(refresh)

    if _looks_like_article_url(page_url):
        return page_url
    return final_url


def resolve_direct_link(url: str) -> str:
    """Backward-compatible alias for projects that call directlink.py this way."""

    return resolve_direct_url(url)


def resolve_direct_links_for_items(
    items: Iterable[Mapping[str, Any]],
    link_key: str = "link",
    output_key: str = "direct_link",
) -> list[dict[str, Any]]:
    """Resolve direct links for dictionaries from RSS/feed parsers.

    The original indirect link is preserved in ``link_key`` and the resolved
    URL is written to ``output_key``.
    """

    resolved: list[dict[str, Any]] = []
    for item in items:
        copied = dict(item)
        original = str(copied.get(link_key, "") or "")
        copied[output_key] = resolve_direct_url(original) or original
        resolved.append(copied)
    return resolved


def choose_best_link(item: Mapping[str, Any]) -> str:
    """Prefer a resolved direct link when dictionary items are used."""

    return str(item.get("direct_link") or item.get("url") or item.get("link") or "#")


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python src/directlink.py <rss-or-indirect-url>")
        raise SystemExit(1)

    print(resolve_direct_url(sys.argv[1]))
