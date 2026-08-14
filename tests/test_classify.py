"""Tests for resilient article classification."""

from __future__ import annotations

import sqlite3
import unittest
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch

import anthropic
import httpx

import ai.classify as classify
from bot.config import settings
from db.models import ReportFilter


class ClassificationFallbackTests(unittest.TestCase):
    def tearDown(self) -> None:
        classify._API_AUTH_FAILED = False

    def test_invalid_api_key_falls_back_offline_for_current_and_later_articles(
        self,
    ) -> None:
        request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
        response = httpx.Response(401, request=request)
        auth_error = anthropic.AuthenticationError(
            "invalid key",
            response=response,
            body=None,
        )
        client = Mock()
        client.messages.create.side_effect = auth_error
        api_settings = replace(settings, anthropic_api_key="invalid")

        with (
            patch("ai.classify.settings", api_settings),
            patch("ai.classify.anthropic.Anthropic", return_value=client) as factory,
        ):
            first = classify.classify_article(
                titulo="New publishing merger",
                resumen="Two book publishers combine their imprints.",
                medio="Publishers Weekly",
                categoria_default="noticias",
                idioma="en",
            )
            second = classify.classify_article(
                titulo="New literary prize",
                resumen="A novelist wins a major book award.",
                medio="Publishers Weekly",
                categoria_default="noticias",
                idioma="en",
            )

        self.assertTrue(first.en_alcance)
        self.assertTrue(second.en_alcance)
        self.assertEqual(factory.call_count, 1)
        self.assertTrue(classify._API_AUTH_FAILED)

    def test_pending_classification_can_be_scoped_to_country_window(self) -> None:
        with TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "test.db"
            conn = sqlite3.connect(db_path)
            conn.executescript(
                """
                CREATE TABLE medios (
                    id INTEGER PRIMARY KEY,
                    nombre TEXT,
                    categoria_default TEXT,
                    tier INTEGER,
                    pais TEXT,
                    region TEXT
                );
                CREATE TABLE articulos (
                    id INTEGER PRIMARY KEY,
                    medio_id INTEGER,
                    titulo_original TEXT,
                    resumen_raw TEXT,
                    categoria TEXT,
                    idioma TEXT,
                    fecha_publicacion TEXT,
                    fecha_ingesta TEXT,
                    procesado INTEGER,
                    relevance_score INTEGER,
                    resumen_generado TEXT,
                    titular_traducido TEXT,
                    tags TEXT
                );
                INSERT INTO medios VALUES
                    (1, 'Publishers Weekly', 'noticias', 1, 'us', 'us'),
                    (2, 'Die Zeit Kultur', 'noticias', 2, 'de', 'eu');
                INSERT INTO articulos VALUES
                    (1, 1, 'Book publishing news', 'A publisher announces a book',
                     'noticias', 'en', '2026-08-13T10:00:00+00:00',
                     '2026-08-13T10:00:00+00:00', 0, NULL, NULL, NULL, NULL),
                    (2, 2, 'Literatur und Bücher', 'Ein neuer Roman',
                     'noticias', 'de', '2026-08-13T10:00:00+00:00',
                     '2026-08-13T10:00:00+00:00', 0, NULL, NULL, NULL, NULL);
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

            offline_settings = replace(settings, anthropic_api_key="")
            with (
                patch("ai.classify.get_connection", test_connection),
                patch("ai.classify.settings", offline_settings),
            ):
                stats = classify.classify_pending(
                    report_filter=ReportFilter(pais="us"),
                    since_iso="2026-08-13T00:00:00+00:00",
                    date_by_publication=True,
                )

            conn = sqlite3.connect(db_path)
            rows = dict(conn.execute("SELECT id, procesado FROM articulos"))
            conn.close()

        self.assertEqual(stats["classified"], 1)
        self.assertEqual(stats["remaining"], 0)
        self.assertEqual(rows, {1: 1, 2: 0})


if __name__ == "__main__":
    unittest.main()
