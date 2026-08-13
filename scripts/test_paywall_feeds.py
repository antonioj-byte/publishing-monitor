#!/usr/bin/env python3
"""Verify RSS alternatives for paywalled medios."""

import socket
import sys
from pathlib import Path

socket.setdefaulttimeout(15)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import feedparser

from ingest.paywall_alternatives import PAYWALL_ALTERNATIVES


def main() -> None:
    ok = 0
    fail = 0
    for name, info in PAYWALL_ALTERNATIVES.items():
        url = info["url"]
        feed = feedparser.parse(url, agent="EditorialBot/1.0")
        n = len(feed.entries)
        status = "OK" if n > 0 else "FAIL"
        if n > 0:
            ok += 1
        else:
            fail += 1
        print(f"{status} {n:3} {name}")
        print(f"      {info['alternativa']}")
        print(f"      {url}")
        if n:
            print(f"      → {feed.entries[0].get('title', '')[:70]}")
        print()

    print(f"Result: {ok}/{ok + fail} feeds working")
    sys.exit(1 if fail else 0)


if __name__ == "__main__":
    main()
