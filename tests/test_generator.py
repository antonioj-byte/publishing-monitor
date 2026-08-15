"""Tests for report selection and continuation behavior."""

from __future__ import annotations

import sqlite3
import unittest
from contextlib import contextmanager
from dataclasses import replace
from datetime import datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from zoneinfo import ZoneInfo

from bot.config import settings
from db.models import ReportFilter
from reports.generator import (
    _apply_report_limits,
    _build_pages,
    _collapse_events_for_report,
    _empty_tag_message,
    _fetch_articles,
    _is_catalog_report,
    _order_catalog_articles,
    build_report,
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

    def test_catalog_report_detects_multi_day_tag_query(self) -> None:
        tag_filter = ReportFilter(days=7, tags=["ficcion"], tag_labels=["Ficción"])
        self.assertTrue(_is_catalog_report(tag_filter, "informe_pais"))
        self.assertFalse(_is_catalog_report(tag_filter, "informe"))
        self.assertFalse(_is_catalog_report(ReportFilter(days=1, tags=["ficcion"]), "informe_pais"))

    def test_catalog_order_keeps_all_articles_not_one_per_event(self) -> None:
        articles = [
            {
                "id": 1,
                "categoria": "noticias",
                "relevance_score": 4,
                "medio_tier": 1,
                "fecha_ingesta": "2026-08-10T10:00:00+00:00",
            },
            {
                "id": 2,
                "categoria": "noticias",
                "relevance_score": 4,
                "medio_tier": 2,
                "fecha_ingesta": "2026-08-09T10:00:00+00:00",
            },
            {
                "id": 3,
                "categoria": "noticias",
                "relevance_score": 3,
                "medio_tier": 2,
                "fecha_ingesta": "2026-08-08T10:00:00+00:00",
            },
        ]
        ordered = _order_catalog_articles(articles)
        self.assertEqual([item["id"] for item in ordered], [1, 2, 3])

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
                    enviado INTEGER,
                    tags TEXT
                );
                INSERT INTO medios VALUES (1, 'Publishers Weekly', 'us', 'us', 1);
                INSERT INTO articulos VALUES (
                    1, 1, 'Publishing merger', NULL, 'Editorial industry news',
                    'Editorial industry news', 'en', 'https://example.com/1',
                    'noticias', 4, '2026-08-13T10:00:00+00:00',
                    '2026-08-13T10:00:00+00:00', 1, 1, NULL
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


class EmptyTagMessageTests(unittest.TestCase):
    def test_mentions_missing_tags_not_country(self) -> None:
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
                CREATE TABLE informes (
                    id INTEGER PRIMARY KEY,
                    fecha_cierre TEXT,
                    tipo TEXT,
                    articulos_incluidos TEXT,
                    enviado_at TEXT
                );
                INSERT INTO medios VALUES (1, 'Publishers Weekly', 'us', 'us', 1);
                INSERT INTO articulos VALUES (
                    1, 1, 'Novel news', 'Noticia novela', 'Resumen',
                    'Summary', 'en', 'https://example.com/1',
                    'noticias', 4, '2026-08-13T10:00:00+00:00',
                    '2026-08-13T10:00:00+00:00', 1, 0, NULL
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

            report_filter = ReportFilter(
                days=7,
                tags=["ficcion"],
                tag_labels=["Ficción"],
            )
            since = datetime.fromisoformat("2026-08-06T00:00:00+00:00")

            with patch("reports.generator.get_connection", test_connection):
                message = _empty_tag_message(
                    report_filter,
                    since,
                    date_by_publication=True,
                )

        self.assertIn("Ficción", message)
        self.assertIn("sin tags editoriales", message)
        self.assertNotIn("país", message.lower())
        self.assertNotIn("run_ingest_once", message)


class CatalogReportIntegrationTests(unittest.TestCase):
    """End-to-end regression test for /informe 7 ficcion (multi-day tag catalog)."""

    def _build_db(self, db_path: Path, *, num_articles: int, num_medios: int) -> None:
        conn = sqlite3.connect(db_path)
        conn.executescript(
            """
            CREATE TABLE medios (
                id INTEGER PRIMARY KEY,
                nombre TEXT,
                categoria_default TEXT,
                tier INTEGER,
                pais TEXT,
                region TEXT,
                activo INTEGER DEFAULT 1
            );
            CREATE TABLE informes (
                id INTEGER PRIMARY KEY,
                fecha_cierre TEXT
            );
            CREATE TABLE articulos (
                id INTEGER PRIMARY KEY,
                medio_id INTEGER,
                titulo_original TEXT,
                resumen_raw TEXT,
                titular_traducido TEXT,
                resumen_generado TEXT,
                url TEXT,
                categoria TEXT,
                idioma TEXT,
                fecha_publicacion TEXT,
                fecha_ingesta TEXT,
                procesado INTEGER,
                relevance_score INTEGER,
                tags TEXT,
                enviado INTEGER DEFAULT 0
            );
            """
        )
        now = datetime.now(ZoneInfo("Europe/Madrid"))
        for m in range(1, num_medios + 1):
            conn.execute(
                "INSERT INTO medios VALUES (?,?,?,?,?,?,1)",
                (m, f"Medio {m}", "noticias", 1, "uk", "eu"),
            )
        for i in range(1, num_articles + 1):
            age_days = 1 + (i % 6)  # spread across the 7-day window
            medio_id = ((i - 1) % num_medios) + 1
            when = (now - timedelta(days=age_days)).isoformat()
            conn.execute(
                """
                INSERT INTO articulos VALUES (?,?,?,?,?,?,?,?,?,?,?,1,4,?,0)
                """,
                (
                    i,
                    medio_id,
                    f"Fiction review {i} about a distinct novel",
                    f"A review of a different novel, book number {i}.",
                    f"Reseña de ficción {i}",
                    f"Resumen distinto de la reseña número {i} sobre un libro diferente.",
                    f"https://example.com/{i}",
                    "noticias",
                    "en",
                    when,
                    when,
                    '["ficcion"]',
                ),
            )
        conn.commit()
        conn.close()

    def test_seven_day_tag_report_returns_more_than_ten_articles(self) -> None:
        """Regression test: /informe 7 ficcion used to collapse ~15 matches to 2-3."""
        with TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "test.db"
            self._build_db(db_path, num_articles=15, num_medios=8)

            @contextmanager
            def test_connection():
                test_conn = sqlite3.connect(db_path)
                test_conn.row_factory = sqlite3.Row
                try:
                    yield test_conn
                finally:
                    test_conn.close()

            with patch("reports.generator.get_connection", test_connection):
                result = build_report(
                    mode="informe_pais",
                    report_filter=ReportFilter(
                        days=7, tags=["ficcion"], tag_labels=["Ficción"]
                    ),
                )

        self.assertGreater(result.total_matched, 10)
        self.assertEqual(result.mode, "informe_pais")

    def test_fast_path_skips_embedding_prioritization(self) -> None:
        with TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "test.db"
            self._build_db(db_path, num_articles=15, num_medios=8)

            @contextmanager
            def test_connection():
                test_conn = sqlite3.connect(db_path)
                test_conn.row_factory = sqlite3.Row
                try:
                    yield test_conn
                finally:
                    test_conn.close()

            with (
                patch("reports.generator.get_connection", test_connection),
                patch("reports.generator.prioritize_articles") as prioritize,
            ):
                result = build_report(
                    mode="informe_pais",
                    report_filter=ReportFilter(
                        days=7, tags=["ficcion"], tag_labels=["Ficción"]
                    ),
                    use_embedding_prioritization=False,
                )

        prioritize.assert_not_called()
        self.assertGreater(result.total_matched, 10)

    def test_daily_digest_still_filters_stale_singleton_articles(self) -> None:
        """Same articles, but /informe (daily digest) must keep its strict threshold."""
        with TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "test.db"
            self._build_db(db_path, num_articles=15, num_medios=8)

            @contextmanager
            def test_connection():
                test_conn = sqlite3.connect(db_path)
                test_conn.row_factory = sqlite3.Row
                try:
                    yield test_conn
                finally:
                    test_conn.close()

            with patch("reports.generator.get_connection", test_connection):
                result = build_report(mode="informe")

        self.assertLess(result.total_matched, 10)


class InformeHoyDiagnosticsTests(unittest.TestCase):
    def test_empty_today_message_explains_no_publication_date(self) -> None:
        with TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "test.db"
            conn = sqlite3.connect(db_path)
            conn.executescript(
                """
                CREATE TABLE medios (
                    id INTEGER PRIMARY KEY, nombre TEXT, region TEXT, pais TEXT, tier INTEGER
                );
                CREATE TABLE articulos (
                    id INTEGER PRIMARY KEY, medio_id INTEGER, titulo_original TEXT,
                    titular_traducido TEXT, resumen_generado TEXT, resumen_raw TEXT,
                    idioma TEXT, url TEXT, categoria TEXT, relevance_score INTEGER,
                    fecha_publicacion TEXT, fecha_ingesta TEXT, procesado INTEGER,
                    enviado INTEGER, tags TEXT
                );
                INSERT INTO medios VALUES (1, 'Test', 'eu', 'es', 2);
                INSERT INTO articulos VALUES (
                    1, 1, 'Old piece', 'Old', 'Summary', 'Summary', 'es',
                    'https://example.com/old', 'noticias', 4,
                    '2026-08-13T10:00:00+00:00', '2026-08-15T08:00:00+00:00', 1, 0, '[]'
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

            since = datetime(2026, 8, 15, 0, 0, tzinfo=ZoneInfo("Europe/Madrid"))
            with patch("reports.generator.get_connection", test_connection):
                from reports.generator import _empty_today_message

                message = _empty_today_message(since)

        self.assertIn("fecha de publicación de hoy", message)
        self.assertIn("ingeridos hoy", message)
        self.assertIn("/muestra", message)


if __name__ == "__main__":
    unittest.main()
