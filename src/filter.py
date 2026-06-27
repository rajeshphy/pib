from __future__ import annotations

import re

try:
    from .common import NewsItem, clean_text
except ImportError:
    from common import NewsItem, clean_text


def readable_title(text: str) -> str:
    text = clean_text(text)
    letters = [char for char in text if char.isalpha()]
    if letters and sum(char.isupper() for char in letters) / len(letters) > 0.82:
        small_words = {"a", "an", "and", "as", "at", "for", "from", "in", "of", "on", "or", "the", "to"}
        words = text.lower().split()
        titled: list[str] = []
        for index, word in enumerate(words):
            if index > 0 and word in small_words:
                titled.append(word)
            else:
                titled.append(word[:1].upper() + word[1:])
        return " ".join(titled)
    return text


def plain_text(markdown: str) -> str:
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", markdown)
    text = re.sub(r"[*_`#>~-]+", "", text)
    return clean_text(text)


def fallback_summary(items: list[NewsItem]) -> str:
    lines = ["TITLE: PIB Regional Updates"]
    for index, item in enumerate(items[:5], 1):
        lines.append(f"- **{readable_title(item.title)}:** {readable_title(item.title)}. Sources: [{index}]")
    return "\n".join(lines)


def split_digest_title(summary: str) -> tuple[str, str]:
    lines = summary.splitlines()
    remaining: list[str] = []
    title = ""
    for line in lines:
        stripped = line.strip()
        match = re.match(r"^TITLE\s*:\s*(.+)$", stripped, flags=re.I)
        if match and not title:
            title = clean_title(match.group(1))
            continue
        remaining.append(line)
    return title, "\n".join(remaining).strip()


def clean_title(value: str) -> str:
    title = plain_text(value)
    title = re.sub(r"^(PIB\s+)?(Daily\s+)?(Brief|Digest)\s*[:\-]\s*", "", title, flags=re.I)
    title = clean_text(title).strip(" .,:;-")
    if not title:
        return "PIB Brief"
    if len(title) > 80:
        title = " ".join(title.split()[:10]).rstrip(".,;:")
    return title


def digest_topics(summary: str) -> list[str]:
    _, body = split_digest_title(summary)
    topics: list[str] = []
    for line in body.splitlines():
        stripped = line.strip()
        if not stripped.startswith(("- ", "* ")):
            continue
        match = re.match(r"^[-*]\s+\*\*([^*:]+):?\*\*\s*:?", stripped)
        if not match:
            continue
        topic = clean_title(match.group(1))
        if topic and topic.lower() not in {item.lower() for item in topics}:
            topics.append(topic)
    return topics


def one_line_summary(summary: str, items: list[NewsItem]) -> str:
    _, summary = split_digest_title(summary)
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
    explicit_title, _ = split_digest_title(summary)
    if explicit_title:
        return explicit_title
    topics = digest_topics(summary)
    if len(topics) >= 2:
        title = ", ".join(topics[:2])
        if len(topics) >= 3:
            title = f"{title} and {topics[2]}"
        return title[:76].rstrip(" ,;:") if len(title) > 78 else title
    teaser = one_line_summary(summary, items)
    words = teaser.split()
    return " ".join(words[:8]).rstrip(".,;:") if words else "PIB Brief"


def extract_source_numbers(text: str) -> tuple[str, list[int]]:
    source_numbers = [int(match) for match in re.findall(r"\[(\d+)\]", text)]
    text = re.sub(r"\s*Sources?:\s*(?:\[\d+\]\s*,?\s*)+$", "", text, flags=re.I)
    text = re.sub(r"\s*(?:\[\d+\]\s*)+$", "", text)
    return clean_text(text), source_numbers


def keyword_set(text: str) -> set[str]:
    words = re.findall(r"[a-zA-Z][a-zA-Z-]{3,}", text.lower())
    stopwords = {
        "and", "from", "have", "into", "that", "their", "this", "with",
        "government", "india", "indian", "pib", "press", "release",
    }
    return {word for word in words if word not in stopwords}


def infer_source_numbers(text: str, items: list[NewsItem], limit: int = 2) -> list[int]:
    text_words = keyword_set(plain_text(text))
    if not text_words:
        return []
    scored: list[tuple[int, int]] = []
    for index, item in enumerate(items, 1):
        title_words = keyword_set(item.title)
        overlap = len(text_words & title_words)
        if overlap:
            scored.append((overlap, index))
    scored.sort(reverse=True)
    return [index for _, index in scored[:limit]]
