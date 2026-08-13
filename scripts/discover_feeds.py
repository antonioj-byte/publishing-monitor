#!/usr/bin/env python3
"""Discover RSS feed URLs for medios with broken feeds."""

import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import feedparser
import httpx
from bs4 import BeautifulSoup

from bot.config import MEDIOS_CSV

USER_AGENT = "EditorialBot/1.0 (feed discovery)"
COMMON_PATHS = ["/feed", "/feed/", "/rss", "/rss.xml", "/index.xml", "/atom.xml"]


def find_rss_in_html(url: str) -> list[str]:
    found: list[str] = []
    try:
        with httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=15, follow_redirects=True) as client:
            r = client.get(url)
            r.raise_for_status()
            soup = BeautifulSoup(r.text, "lxml")
            for link in soup.find_all("link", rel="alternate"):
                typ = link.get("type", "")
                href = link.get("href")
                if href and ("rss" in typ or "atom" in typ or "xml" in typ):
                    from urllib.parse import urljoin
                    found.append(urljoin(url, href))
    except Exception:
        pass
    return found


def test_feed(url: str) -> bool:
    feed = feedparser.parse(url, agent=USER_AGENT)
    return bool(feed.entries) and not (feed.bozo and not feed.entries)


def main() -> None:
    broken = []
    with MEDIOS_CSV.open(encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row["metodo"] != "rss" or not row.get("url_rss"):
                continue
            url = row["url_rss"].strip()
            if test_feed(url):
                continue
            candidates = find_rss_in_html(row["url_site"].strip())
            for path in COMMON_PATHS:
                from urllib.parse import urljoin
                candidates.append(urljoin(row["url_site"].strip(), path))
            working = [c for c in dict.fromkeys(candidates) if test_feed(c)]
            broken.append((row["nombre"], url, working[:3]))

    print(f"Broken feeds: {len(broken)}")
    for name, old, fixes in broken:
        print(f"\n{name}")
        print(f"  current: {old}")
        if fixes:
            print(f"  suggested: {fixes[0]}")
        else:
            print("  suggested: switch to scraping")


if __name__ == "__main__":
    main()
