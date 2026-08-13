"""RSS ingestion utilities."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from html import unescape
from typing import Any
from urllib.parse import urlparse, urlunparse

import feedparser

USER_AGENT = "EditorialBot/1.0 (local RSS monitor)"


@dataclass
class ParsedArticle:
    title: str
    url: str
    summary: str | None
    published_at: str | None
    hash_contenido: str


def strip_html(text: str) -> str:
    cleaned = re.sub(r"<[^>]+>", " ", text)
    cleaned = unescape(cleaned)
    return re.sub(r"\s+", " ", cleaned).strip()


def normalize_url(url: str) -> str:
    try:
        parsed = urlparse(url.strip())
        path = parsed.path.rstrip("/") if parsed.path != "/" else parsed.path
        normalized = urlunparse(
            (parsed.scheme, parsed.netloc.lower(), path, parsed.params, parsed.query, "")
        )
        return normalized
    except Exception:
        return url.strip()


def content_hash(url: str, title: str) -> str:
    payload = f"{normalize_url(url)}|{title.strip().lower()}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def parse_published(entry: Any) -> str | None:
    for key in ("published_parsed", "updated_parsed"):
        parsed = getattr(entry, key, None)
        if parsed:
            try:
                dt = datetime(*parsed[:6], tzinfo=timezone.utc)
                return dt.isoformat()
            except (TypeError, ValueError):
                pass
    for key in ("published", "updated"):
        raw = entry.get(key) if hasattr(entry, "get") else None
        if raw:
            try:
                dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return dt.isoformat()
            except ValueError:
                pass
    return None


def extract_link(entry: Any) -> str | None:
    link = entry.get("link") if hasattr(entry, "get") else None
    if link:
        return str(link)
    links = entry.get("links") if hasattr(entry, "get") else None
    if links:
        for item in links:
            href = item.get("href") if isinstance(item, dict) else getattr(item, "href", None)
            if href:
                return str(href)
    return None


def extract_summary(entry: Any) -> str | None:
    for key in ("summary", "description", "content"):
        raw = entry.get(key) if hasattr(entry, "get") else None
        if not raw:
            continue
        if isinstance(raw, list) and raw:
            raw = raw[0].get("value") if isinstance(raw[0], dict) else raw[0]
        if isinstance(raw, str):
            text = strip_html(raw)
            if text:
                return text[:500] if len(text) > 500 else text
    return None


def parse_feed(url: str) -> list[ParsedArticle]:
    feed = feedparser.parse(url, agent=USER_AGENT)
    if feed.bozo and not feed.entries:
        raise RuntimeError(getattr(feed, "bozo_exception", "Invalid feed"))

    articles: list[ParsedArticle] = []
    for entry in feed.entries:
        title = entry.get("title") if hasattr(entry, "get") else None
        link = extract_link(entry)
        if not title or not link:
            continue
        title = strip_html(str(title))
        link = normalize_url(str(link))
        articles.append(
            ParsedArticle(
                title=title,
                url=link,
                summary=extract_summary(entry),
                published_at=parse_published(entry),
                hash_contenido=content_hash(link, title),
            )
        )
    return articles
