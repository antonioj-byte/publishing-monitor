"""Tests for publication date filtering and Telegram HTML formatting."""

from __future__ import annotations

import sqlite3
import unittest
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from zoneinfo import ZoneInfo

from reports.dates import publication_within_window
from reports.generator import _fetch_articles
from reports.telegram_format import format_article_entry


class PublicationDateTests(unittest.TestCase):
    def test_publication_within_window_rejects_old_article(self) -> None:
        since = datetime(2026, 8, 14, 0, 0, tzinfo=ZoneInfo("Europe/Madrid"))
        self.assertFalse(
            publication_within_window("2026-02-25T22:32:32+00:00", since)
        )
        self.assertTrue(
            publication_within_window("2026-08-14T08:00:00+00:00", since)
        )

    def test_strict_fetch_excludes_old_publication_same_day_ingest(self) -> None:
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
                    enviado INTEGER,
                    tags TEXT
                );
                INSERT INTO medios VALUES (1, 'NYRB', 'us', 'us', 1);
                INSERT INTO articulos VALUES (
                    1, 1, 'Old essay', 'Old essay', 'Summary', 'Summary', 'en',
                    'https://example.com/old', 'ideas', 4,
                    '2026-02-01T10:00:00+00:00', '2026-08-14T10:00:00+00:00', 1, 0, NULL
                );
                INSERT INTO articulos VALUES (
                    2, 1, 'Fresh piece', 'Fresh piece', 'Summary', 'Summary', 'en',
                    'https://example.com/new', 'ideas', 4,
                    '2026-08-14T09:00:00+00:00', '2026-08-14T10:00:00+00:00', 1, 0, NULL
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

            since = datetime(2026, 8, 14, 0, 0, tzinfo=ZoneInfo("Europe/Madrid"))
            with (
                patch("reports.generator.get_connection", test_connection),
                patch("reports.generator.filter_editorial_scope", lambda rows: rows),
                patch("reports.generator.apply_keyword_scope_filter", lambda rows: rows),
                patch("reports.generator.get_tier", lambda _name: 1),
            ):
                articles = _fetch_articles(
                    since,
                    include_sent=True,
                    date_by_publication=True,
                    strict_publication=True,
                )

        self.assertEqual([item["id"] for item in articles], [2])


class TelegramFormatTests(unittest.TestCase):
    def test_headline_is_bold_without_tier(self) -> None:
        text = format_article_entry(
            {
                "titulo_original": "Titular original",
                "titular_traducido": "Titular en castellano",
                "resumen_generado": "Resumen breve.",
                "resumen_raw": "Raw",
                "idioma": "es",
                "url": "https://example.com/a",
                "medio_nombre": "Le Monde Livres",
                "medio_tier": 1,
                "fecha_publicacion": "2026-08-14T09:00:00+00:00",
            }
        )
        self.assertIn("<b>Titular en castellano</b>", text)
        self.assertNotIn("Tier", text)
        self.assertIn("<i>Le Monde Livres</i>", text)
        self.assertIn("📅 Publicado: 14/08/2026", text)
        self.assertLess(text.index("Resumen breve."), text.index("📅"))
        self.assertLess(text.index("📅"), text.index("🔗"))


if __name__ == "__main__":
    unittest.main()
