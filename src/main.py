#!/usr/bin/env python3
"""Generate a small English PIB news digest from the regional PIB page."""

from __future__ import annotations

import argparse
import html
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path


PIB_URL = "https://www.pib.gov.in/indexd.aspx?reg=48&lang=1"
GEMINI_API_ROOT = "https://generativelanguage.googleapis.com/v1beta/models"
DEFAULT_GEMINI_MODEL = "gemini-3.1-flash-lite"
ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
POSTS = DOCS / "_posts"
DATA = ROOT / "data"
QUOTA_FILE = DATA / "quota.json"


@dataclass
class NewsItem:
    title: str
    url: str
    date: str = ""


class LinkParser(HTMLParser):
    """Collect link text and URLs from the PIB listing page."""

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


def clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


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


def collect_items(limit: int) -> list[NewsItem]:
    parser = LinkParser()
    parser.feed(fetch_text(PIB_URL))

    seen: set[str] = set()
    items: list[NewsItem] = []
    for item in parser.links:
        key = item.title.lower()
        if key in seen:
            continue
        seen.add(key)
        items.append(item)
        if len(items) >= limit:
            break
    return items


def read_env_file() -> None:
    env_file = ROOT / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def load_quota() -> dict:
    if not QUOTA_FILE.exists():
        return {"day": "", "count": 0, "last_call": 0.0}
    try:
        return json.loads(QUOTA_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"day": "", "count": 0, "last_call": 0.0}


def reserve_gemini_call(max_daily_calls: int, min_interval_seconds: int) -> None:
    DATA.mkdir(exist_ok=True)
    today = datetime.now(timezone.utc).date().isoformat()
    quota = load_quota()
    if quota.get("day") != today:
        quota = {"day": today, "count": 0, "last_call": 0.0}

    if int(quota.get("count", 0)) >= max_daily_calls:
        raise RuntimeError(f"Daily Gemini call limit reached: {max_daily_calls}")

    elapsed = time.time() - float(quota.get("last_call", 0.0))
    if elapsed < min_interval_seconds:
        time.sleep(min_interval_seconds - elapsed)

    quota["count"] = int(quota.get("count", 0)) + 1
    quota["last_call"] = time.time()
    QUOTA_FILE.write_text(json.dumps(quota, indent=2), encoding="utf-8")


def gemini_summary(items: list[NewsItem], api_key: str) -> str:
    reserve_gemini_call(max_daily_calls=20, min_interval_seconds=12)
    model = os.environ.get("GEMINI_MODEL", DEFAULT_GEMINI_MODEL)
    prompt_items = "\n".join(
        f"{index}. {item.title}\n   URL: {item.url}" for index, item in enumerate(items, 1)
    )
    prompt = f"""
Convert these PIB regional news headlines into an English Markdown digest.

Rules:
- Output no more than 5 significant bullet points.
- Use clear, readable English.
- Group related items where possible.
- Prefer policy/public-service meaning over headline wording.
- Keep every point factual and avoid adding facts not present in the headlines.
- Do not include a heading.
- Do not include inline links in the bullet points.
- Format each point as: - **Short topic:** one concise sentence.

PIB page: {PIB_URL}

Items:
{prompt_items}
""".strip()
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.2, "maxOutputTokens": 700},
    }
    body = json.dumps(payload).encode("utf-8")
    url = f"{GEMINI_API_ROOT}/{urllib.parse.quote(model)}:generateContent?key={urllib.parse.quote(api_key)}"
    request = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        data = json.loads(response.read().decode("utf-8"))
    try:
        return data["candidates"][0]["content"]["parts"][0]["text"].strip()
    except (KeyError, IndexError) as exc:
        raise RuntimeError(f"Unexpected Gemini response: {data}") from exc


def fallback_summary(items: list[NewsItem]) -> str:
    lines = []
    for item in items[:5]:
        lines.append(f"- [{readable_title(item.title)}]({item.url})")
    return "\n".join(lines)


def plain_text(markdown: str) -> str:
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", markdown)
    text = re.sub(r"[*_`#>~-]+", "", text)
    return clean_text(text)


def readable_title(text: str) -> str:
    text = clean_text(text)
    letters = [char for char in text if char.isalpha()]
    if letters and sum(char.isupper() for char in letters) / len(letters) > 0.82:
        small_words = {"a", "an", "and", "as", "at", "for", "from", "in", "of", "on", "or", "the", "to"}
        words = text.lower().split()
        titled = []
        for index, word in enumerate(words):
            if index > 0 and word in small_words:
                titled.append(word)
            else:
                titled.append(word[:1].upper() + word[1:])
        return " ".join(titled)
    return text


def one_line_summary(summary: str, items: list[NewsItem]) -> str:
    for line in summary.splitlines():
        line = line.strip()
        if not line or line.startswith("<") or line.startswith("#"):
            continue
        line = re.sub(r"^[-*]\s+", "", line)
        line = re.sub(r"^\d+\.\s+", "", line)
        text = plain_text(line)
        if "digest" in text.lower() and len(text) < 60:
            continue
        if text and len(text) > 20:
            return text[:157].rstrip() + "..." if len(text) > 160 else text
    return plain_text(items[0].title) if items else "PIB daily brief"


def post_title(summary: str, items: list[NewsItem]) -> str:
    teaser = one_line_summary(summary, items)
    if ":" in teaser:
        title = teaser.split(":", 1)[0]
        if 8 <= len(title) <= 70:
            return title
    words = teaser.split()
    return " ".join(words[:9]).rstrip(".,;:") if words else "PIB Brief"


def yaml_escape(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def inline_markdown_to_html(text: str) -> str:
    placeholders: list[str] = []

    def link_replacer(match: re.Match[str]) -> str:
        label = html.escape(match.group(1))
        url = html.escape(match.group(2), quote=True)
        placeholders.append(f'<a href="{url}">{label}</a>')
        return f"@@LINK{len(placeholders) - 1}@@"

    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", link_replacer, text)
    escaped = html.escape(text)
    escaped = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", escaped)
    for index, replacement in enumerate(placeholders):
        escaped = escaped.replace(f"@@LINK{index}@@", replacement)
    return escaped


def summary_to_html(summary: str) -> str:
    items: list[str] = []
    paragraphs: list[str] = []
    for raw_line in summary.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("<") or line.startswith("#"):
            continue
        line = re.sub(r"^\d+\.\s+", "- ", line)
        if line.startswith(("- ", "* ")):
            items.append(line[2:].strip())
        else:
            paragraphs.append(line)

    parts: list[str] = []
    if paragraphs:
        parts.extend(f"<p>{inline_markdown_to_html(line)}</p>" for line in paragraphs)
    if items:
        parts.append('<ul class="digest-points">')
        parts.extend(f"  <li>{inline_markdown_to_html(item)}</li>" for item in items)
        parts.append("</ul>")
    return "\n".join(parts)


def sources_to_html(items: list[NewsItem]) -> str:
    lines = ['<ul class="source-list">']
    for item in items[:10]:
        title = html.escape(readable_title(item.title))
        url = html.escape(item.url, quote=True)
        lines.append(f'  <li><a href="{url}">{title}</a></li>')
    lines.append("</ul>")
    return "\n".join(lines)


def build_post(summary: str, items: list[NewsItem], used_ai: bool) -> Path:
    POSTS.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc)
    post_path = POSTS / f"{now.date().isoformat()}-pib-digest.md"
    source_list = sources_to_html(items)
    ai_note = "Gemini-assisted summary" if used_ai else "Direct headline digest"
    teaser = one_line_summary(summary, items)
    title = post_title(summary, items)
    content = f"""---
layout: default
title: {yaml_escape(title)}
date: {now.isoformat()}
summary: {yaml_escape(teaser)}
---

<article class="digest-post">
  <a class="back-link" href="{{{{ '/' | relative_url }}}}">PIB Brief</a>
  <p class="post-meta">{now.date().isoformat()} · {ai_note}</p>

{summary_to_html(summary)}

<section class="source-note">
  <h2>Source</h2>
  <p>Generated from <a href="{PIB_URL}">PIB regional news listing</a>.</p>
</section>

<details class="tp-sources">
<summary>Headlines considered</summary>

{source_list}

</details>
</article>
"""
    post_path.write_text(content, encoding="utf-8")
    return post_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate the PIB English digest.")
    parser.add_argument("--limit", type=int, default=12, help="Number of headlines to inspect.")
    parser.add_argument("--no-ai", action="store_true", help="Skip Gemini and write headline bullets.")
    args = parser.parse_args()

    read_env_file()
    items = collect_items(limit=args.limit)
    if not items:
        print("No PIB news items found.", file=sys.stderr)
        return 1

    api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    used_ai = bool(api_key and not args.no_ai)
    try:
        summary = gemini_summary(items, api_key) if used_ai else fallback_summary(items)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        print(f"Gemini request failed: HTTP {exc.code}: {detail}", file=sys.stderr)
        print("Writing fallback headline digest instead.", file=sys.stderr)
        summary = fallback_summary(items)
        used_ai = False
    except Exception as exc:
        print(f"Gemini summary failed: {exc}", file=sys.stderr)
        print("Writing fallback headline digest instead.", file=sys.stderr)
        summary = fallback_summary(items)
        used_ai = False

    post_path = build_post(summary, items, used_ai)
    print(f"Wrote {post_path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
