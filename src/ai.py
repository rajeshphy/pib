from __future__ import annotations

import json
import os
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone

try:
    from .common import DATA, DEFAULT_GEMINI_MODEL, GEMINI_API_ROOT, PIB_URL, QUOTA_FILE, NewsItem
except ImportError:
    from common import DATA, DEFAULT_GEMINI_MODEL, GEMINI_API_ROOT, PIB_URL, QUOTA_FILE, NewsItem


def read_env_file(root) -> None:
    env_file = root / ".env"
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
        f"{index}. {item.title}\nURL: {item.url}" for index, item in enumerate(items, 1)
    )
    prompt = f"""
Convert these PIB regional news headlines into an English Markdown digest.

Rules:
- First line must be a suitable one-line digest title using this exact format: TITLE: concise title covering the whole digest
- Output no more than 5 significant bullet points.
- Use clear, readable English.
- Group related items where possible.
- Prefer policy/public-service meaning over headline wording.
- Keep every point factual and avoid adding facts not present in the headlines.
- Do not include a heading.
- Do not include inline links in the bullet points.
- End every bullet with source numbers using this exact format: Sources: [1], [3]
- Format each point as: - **Short topic:** one concise sentence. Sources: [1], [3]
- The TITLE must not simply copy the first bullet topic.

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
    request = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(request, timeout=60) as response:
        data = json.loads(response.read().decode("utf-8"))
    try:
        return data["candidates"][0]["content"]["parts"][0]["text"].strip()
    except (KeyError, IndexError) as exc:
        raise RuntimeError(f"Unexpected Gemini response: {data}") from exc
