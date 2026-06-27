from __future__ import annotations

import html
import json
import re
from datetime import datetime, timezone
from pathlib import Path

try:
    from .common import IST, PIB_URL, POSTS, NewsItem
    from .filter import (
        extract_source_numbers,
        infer_source_numbers,
        one_line_summary,
        plain_text,
        post_title,
        readable_title,
        split_digest_title,
    )
except ImportError:
    from common import IST, PIB_URL, POSTS, NewsItem
    from filter import (
        extract_source_numbers,
        infer_source_numbers,
        one_line_summary,
        plain_text,
        post_title,
        readable_title,
        split_digest_title,
    )


def yaml_escape(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def source_chips_html(source_numbers: list[int], items: list[NewsItem]) -> str:
    valid_numbers: list[int] = []
    seen: set[int] = set()
    for number in source_numbers:
        if number in seen or number < 1 or number > len(items):
            continue
        seen.add(number)
        valid_numbers.append(number)
    if not valid_numbers:
        return ""
    links: list[str] = []
    for number in valid_numbers:
        item = items[number - 1]
        url = html.escape(item.url, quote=True)
        links.append(f'<a href="{url}" target="_blank" rel="noopener noreferrer">Source {number}</a>')
    return f'<span class="source-chips">{" ".join(links)}</span>'


def inline_markdown_to_html(text: str) -> str:
    placeholders: list[str] = []

    def link_replacer(match: re.Match[str]) -> str:
        label = html.escape(match.group(1))
        url = html.escape(match.group(2), quote=True)
        placeholders.append(f'<a href="{url}" target="_blank" rel="noopener noreferrer">{label}</a>')
        return f"@@LINK{len(placeholders) - 1}@@"

    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", link_replacer, text)
    escaped = html.escape(text)
    escaped = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", escaped)
    for index, replacement in enumerate(placeholders):
        escaped = escaped.replace(f"@@LINK{index}@@", replacement)
    return escaped


def summary_to_html(summary: str, items: list[NewsItem]) -> str:
    _, summary = split_digest_title(summary)
    bullet_items: list[str] = []
    paragraphs: list[str] = []
    for raw_line in summary.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("<") or line.startswith("#"):
            continue
        line = re.sub(r"^\d+\.\s+", "- ", line)
        if line.startswith(("- ", "* ")):
            bullet_items.append(line[2:].strip())
        else:
            paragraphs.append(line)

    parts: list[str] = []
    if paragraphs:
        parts.extend(f"<p>{inline_markdown_to_html(line)}</p>" for line in paragraphs)
    if bullet_items:
        parts.append('<ul class="digest-points">')
        for bullet_item in bullet_items:
            item_text, source_numbers = extract_source_numbers(bullet_item)
            if not source_numbers and "](" not in bullet_item:
                source_numbers = infer_source_numbers(item_text, items)
            chips = source_chips_html(source_numbers, items)
            parts.append(f"  <li>{inline_markdown_to_html(item_text)}{chips}</li>")
        parts.append("</ul>")
    return "\n".join(parts)


def sources_to_html(items: list[NewsItem]) -> str:
    lines = ['<ul class="source-list">']
    for item in items[:10]:
        title = html.escape(readable_title(item.title))
        url = html.escape(item.url, quote=True)
        lines.append(f'  <li><a href="{url}" target="_blank" rel="noopener noreferrer">{title}</a></li>')
    lines.append("</ul>")
    return "\n".join(lines)


def build_post(summary: str, items: list[NewsItem], used_ai: bool) -> Path:
    POSTS.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc)
    now_ist = now.astimezone(IST)
    post_path = POSTS / f"{now.date().isoformat()}-pib-digest.md"
    source_list = sources_to_html(items)
    try:
        run_time = now_ist.strftime("%-I:%M%p")
    except ValueError:
        run_time = now_ist.strftime("%I:%M%p").lstrip("0")
    ai_note = f"Gemini Summary: {run_time}" if used_ai else f"Headline Digest: {run_time}"
    teaser = one_line_summary(summary, items)
    title = post_title(summary, items)
    content = f"""---
layout: default
title: {yaml_escape(title)}
date: {now.isoformat()}
summary: {yaml_escape(teaser)}
run_time_ist: {yaml_escape(run_time)}
---

# PIB Brief

<p class="digest-meta">{html.escape(ai_note)}</p>

{summary_to_html(summary, items)}

## Source

Generated from <a href="{html.escape(PIB_URL, quote=True)}" target="_blank" rel="noopener noreferrer">PIB regional news listing</a>.

Headlines considered:

{source_list}
"""
    post_path.write_text(content, encoding="utf-8")
    return post_path
