"""Web scraping for sources without RSS."""

from __future__ import annotations

import re
from dataclasses import dataclass
from html import unescape
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

from ingest.rss import ParsedArticle, content_hash, normalize_url, strip_html

USER_AGENT = "EditorialBot/1.0 (local scraper)"
TIMEOUT = 25.0

# Per-domain link selectors for culture/book sections
SCRAPER_SELECTORS: dict[str, dict] = {
    "publishersweekly.com": {
        "article": "article, .article-item, .listicle-item",
        "link": "a[href]",
        "title": "h2, h3, .title",
    },
    "thebookseller.com": {
        "article": "article, .node--type-article",
        "link": "a[href]",
        "title": "h2, h3",
    },
    "wsj.com": {
        "article": "article, [data-type='article']",
        "link": "a[href]",
        "title": "h2, h3",
    },
    "thetimes.co.uk": {
        "article": "article, [data-testid='article']",
        "link": "a[href]",
        "title": "h2, h3",
    },
    "ft.com": {
        "article": "article, .o-teaser",
        "link": "a[href]",
        "title": "h2, h3, .o-teaser__heading",
    },
    "nationalpost.com": {
        "article": "article, .article-card",
        "link": "a[href]",
        "title": "h2, h3",
    },
    "elmercurio.com": {
        "article": "article, .story",
        "link": "a[href]",
        "title": "h2, h3",
    },
    "cincodias.elpais.com": {
        "article": "article, .c_a",
        "link": "a[href]",
        "title": "h2, h3",
    },
    "asia.nikkei.com": {
        "article": "article, .stream-item",
        "link": "a[href]",
        "title": "h2, h3",
    },
}

DEFAULT_SELECTOR = {
    "article": "article, .article, .story, .post, li",
    "link": "a[href]",
    "title": "h1, h2, h3, h4",
}


@dataclass
class ScrapeConfig:
    url: str
    domain: str


def _domain_from_url(url: str) -> str:
    netloc = urlparse(url).netloc.lower()
    if netloc.startswith("www."):
        netloc = netloc[4:]
    return netloc


def _is_article_url(base_url: str, href: str) -> bool:
    if not href or href.startswith("#") or href.startswith("javascript:"):
        return False
    full = normalize_url(urljoin(base_url, href))
    parsed = urlparse(full)
    if parsed.scheme not in ("http", "https"):
        return False
    path = parsed.path.lower()
    if len(path) < 10:
        return False
    skip = (
        "/tag/", "/author/", "/search", "/login", "/subscribe", "/newsletter",
        "/newsletters", "/signup", "/register", "/privacy", "/terms", "/contact",
        "/about", "/account", "/cart", "/shop",
    )
    return not any(s in path for s in skip)


def _is_valid_title(title: str) -> bool:
    if len(title) < 15 or len(title) > 300:
        return False
    junk = (
        "newsletter", "subscribe", "sign up", "log in", "cookie",
        "free newsletters", "follow us",
    )
    lower = title.lower()
    return not any(j in lower for j in junk)


def scrape_section(url: str, max_articles: int = 25) -> list[ParsedArticle]:
    domain = _domain_from_url(url)
    selectors = SCRAPER_SELECTORS.get(domain, DEFAULT_SELECTOR)

    with httpx.Client(
        headers={"User-Agent": USER_AGENT},
        timeout=TIMEOUT,
        follow_redirects=True,
    ) as client:
        response = client.get(url)
        response.raise_for_status()
        html = response.text

    soup = BeautifulSoup(html, "lxml")
    seen_urls: set[str] = set()
    articles: list[ParsedArticle] = []

    containers = soup.select(selectors["article"]) or [soup.body or soup]
    for container in containers:
        for link_el in container.select(selectors["link"]):
            href = link_el.get("href")
            if not href or not _is_article_url(url, href):
                continue

            article_url = normalize_url(urljoin(url, href))
            if article_url in seen_urls:
                continue

            title = None
            title_el = link_el.find(selectors["title"].split(",")[0].strip())
            if title_el:
                title = strip_html(title_el.get_text())
            if not title:
                title = strip_html(link_el.get_text())
            if not title or not _is_valid_title(title):
                continue

            seen_urls.add(article_url)
            articles.append(
                ParsedArticle(
                    title=title,
                    url=article_url,
                    summary=None,
                    published_at=None,
                    hash_contenido=content_hash(article_url, title),
                )
            )
            if len(articles) >= max_articles:
                return articles

    return articles
