#!/usr/bin/env python3
"""Generate a small English PIB news digest from the regional PIB page."""
from __future__ import annotations

import argparse
import os
import sys
import urllib.error

try:
    from .ai import gemini_summary, read_env_file
    from .common import ROOT
    from .fetch import collect_items
    from .filter import fallback_summary
    from .markdown import build_post
except ImportError:  # Allows `python3 src/main.py`.
    from ai import gemini_summary, read_env_file
    from common import ROOT
    from fetch import collect_items
    from filter import fallback_summary
    from markdown import build_post


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate the PIB English digest.")
    parser.add_argument("--limit", type=int, default=12, help="Number of headlines to inspect.")
    parser.add_argument("--no-ai", action="store_true", help="Skip Gemini and write headline bullets.")
    parser.add_argument(
        "--no-resolve-links",
        action="store_true",
        help="Do not resolve source links before writing the post.",
    )
    args = parser.parse_args()

    read_env_file(ROOT)
    items = collect_items(limit=args.limit, resolve_links=not args.no_resolve_links)
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
