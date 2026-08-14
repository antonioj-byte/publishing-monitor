"""Tests for report selection and continuation behavior."""

from __future__ import annotations

import sqlite3
import unittest
from contextlib import contextmanager
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from bot.config import settings
from reports.generator import (
    _apply_report_limits,
    _build_pages,
    _collapse_events_for_report,
    _fetch_articles,
    split_message,
)


def _article(article_id: int, score: int) -> dict:
    return {
        "id": article_id,
        "relevance_score": score,
        "categoria": "noticias",
    }


class ReportLimitTests(unittest.TestCase):
    def test_applies_per_score_and_total_limits(self) -> None:
        articles = [
            *[_article(i, 5) for i in range(1, 5)],
            *[_article(i, 4) for i in range(5, 9)],
            *[_article(i, 3) for i in range(9, 13)],
        ]
        limited_settings = replace(
            settings,
            max_destacados=2,
            max_relevantes=2,
            max_secundarios=2,
            max_articles_per_informe=5,
        )
        with patch("reports.generator.settings", limited_settings):
            limited = _apply_report_limits(articles)

        self.assertEqual([item["id"] for item in limited], [1, 2, 5, 6, 9])

    def test_round_robin_limits_per_medio(self) -> None:
        articles = [
            {"id": 1, "relevance_score": 5, "categoria": "noticias", "medio_nombre": "Publishers Weekly"},
            {"id": 2, "relevance_score": 5, "categoria": "noticias", "medio_nombre": "Publishers Weekly"},
            {"id": 3, "relevance_score": 5, "categoria": "noticias", "medio_nombre": "El País Babelia"},
            {"id": 4, "relevance_score": 5, "categoria": "noticias", "medio_nombre": "The Bookseller"},
        ]
        limited_settings = replace(
            settings,
            max_destacados=3,
            max_relevantes=0,
            max_secundarios=0,
            max_articles_per_informe=10,
            max_articles_per_medio=1,
        )
        with patch("reports.generator.settings", limited_settings):
            limited = _apply_report_limits(articles)

        medios = [item["medio_nombre"] for item in limited]
        self.assertEqual(len(limited), 3)
        self.assertEqual(len(set(medios)), 3)
        self.assertEqual(medios.count("Publishers Weekly"), 1)

    def test_collapses_multiple_articles_from_same_event(self) -> None:
        articles = [
            {"id": 1, "event_id": 10, "relevance_score": 5, "medio_tier": 1, "medio_nombre": "PW"},
            {"id": 2, "event_id": 10, "relevance_score": 4, "medio_tier": 1, "medio_nombre": "Bookseller"},
            {"id": 3, "event_id": 11, "relevance_score": 4, "medio_tier": 2, "medio_nombre": "Reforma"},
        ]
        collapsed = _collapse_events_for_report(articles)
        self.assertEqual([item["id"] for item in collapsed], [1, 3])

    def test_oversized_first_article_advances_pagination_cursor(self) -> None:
        article = {
            "id": 1,
            "titulo_original": "A" * 500,
            "titular_traducido": None,
            "resumen_generado": "B" * 500,
            "resumen_raw": None,
            "idioma": "es",
            "url": "https://example.com/article",
            "categoria": "noticias",
            "relevance_score": 4,
            "medio_nombre": "Publishers Weekly",
            "medio_tier": 1,
        }
        _, ids, cursor, has_more, _ = _build_pages(
            mode="informe",
            report_filter=None,
            since=datetime.fromisoformat("2026-08-13T00:00:00+00:00"),
            include_sent=False,
            ordered_articles=[article],
            trends=[],
            max_words=1,
        )
        self.assertEqual(ids, [1])
        self.assertEqual(cursor, 1)
        self.assertFalse(has_more)

    def test_split_message_hard_splits_single_oversized_block(self) -> None:
        chunks = split_message("x" * 9000, max_len=4000)
        self.assertEqual([len(chunk) for chunk in chunks], [4000, 4000, 1000])


class ContinuationFetchTests(unittest.TestCase):
    def test_snapshot_fetch_keeps_already_sent_articles(self) -> None:
        with TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "test.db"
            conn = sqlite3.connect(db_path)
            conn.executescript(
                """
                CREATE TABLE medios (
                    id INTEGER PRIMARY KEY,
                    nombre TEXT,
                    region TEXT,
                    pais TEXT,
                    tier INTEGER
                );
                CREATE TABLE articulos (
                    id INTEGER PRIMARY KEY,
                    medio_id INTEGER,
                    titulo_original TEXT,
                    titular_traducido TEXT,
                    resumen_generado TEXT,
                    resumen_raw TEXT,
                    idioma TEXT,
                    url TEXT,
                    categoria TEXT,
                    relevance_score INTEGER,
                    fecha_publicacion TEXT,
                    fecha_ingesta TEXT,
                    procesado INTEGER,
                    enviado INTEGER
                );
                INSERT INTO medios VALUES (1, 'Publishers Weekly', 'us', 'us', 1);
                INSERT INTO articulos VALUES (
                    1, 1, 'Publishing merger', NULL, 'Editorial industry news',
                    'Editorial industry news', 'en', 'https://example.com/1',
                    'noticias', 4, '2026-08-13T10:00:00+00:00',
                    '2026-08-13T10:00:00+00:00', 1, 1
                );
                """
            )
            conn.commit()
            conn.close()

            @contextmanager
            def test_connection():
                test_conn = sqlite3.connect(db_path)
                test_conn.row_factory = sqlite3.Row
                try:
                    yield test_conn
                finally:
                    test_conn.close()

            with patch("reports.generator.get_connection", test_connection):
                articles = _fetch_articles(
                    since=datetime.fromisoformat("2026-08-13T00:00:00+00:00"),
                    include_sent=False,
                    article_ids=[1],
                )

        self.assertEqual([item["id"] for item in articles], [1])


if __name__ == "__main__":
    unittest.main()
