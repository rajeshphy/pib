from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from zoneinfo import ZoneInfo

PIB_URL = "https://www.pib.gov.in/indexd.aspx?reg=48&lang=1"
GEMINI_API_ROOT = "https://generativelanguage.googleapis.com/v1beta/models"
DEFAULT_GEMINI_MODEL = "gemini-3.1-flash-lite"
IST = ZoneInfo("Asia/Kolkata")

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
POSTS = DOCS / "_posts"
DATA = ROOT / "data"
QUOTA_FILE = DATA / "quota.json"


@dataclass(slots=True)
class NewsItem:
    title: str
    url: str
    date: str = ""


def clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()
