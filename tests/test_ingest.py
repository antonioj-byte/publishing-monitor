"""Tests for ingestion fallback behavior."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from db.models import Medio
from ingest.rss import ParsedArticle
from ingest.runner import fetch_articles


class IngestFallbackTests(unittest.TestCase):
    def setUp(self) -> None:
        self.medio = Medio(
            id=1,
            nombre="Example Books",
            url_site="https://example.com/books",
            url_rss="https://example.com/feed",
            url_scraping="https://example.com/books",
            metodo="rss",
            categoria_default="noticias",
            idioma="en",
            region="us",
            pais="us",
            tier=1,
            activo=True,
        )
        self.scraped = [
            ParsedArticle(
                title="Publishing industry update",
                url="https://example.com/article",
                summary=None,
                published_at=None,
                hash_contenido="hash",
            )
        ]

    def test_empty_rss_falls_back_to_scraper(self) -> None:
        with (
            patch("ingest.runner.parse_feed", return_value=[]),
            patch(
                "ingest.runner.scrape_section",
                return_value=self.scraped,
            ) as scraper,
        ):
            result = fetch_articles(self.medio)

        self.assertEqual(result, self.scraped)
        scraper.assert_called_once_with(self.medio.url_scraping)

    def test_broken_rss_falls_back_to_scraper(self) -> None:
        with (
            patch("ingest.runner.parse_feed", side_effect=RuntimeError("broken")),
            patch(
                "ingest.runner.scrape_section",
                return_value=self.scraped,
            ),
        ):
            result = fetch_articles(self.medio)

        self.assertEqual(result, self.scraped)


if __name__ == "__main__":
    unittest.main()
