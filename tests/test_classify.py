"""Tests for resilient article classification."""

from __future__ import annotations

import sqlite3
import unittest
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch

import ai.classify as classify
from ai.llm_provider import LLMAuthError, LLMQuotaError
from bot.config import settings
from db.models import ReportFilter


def _anthropic_settings(**kwargs: object):
    base = replace(
        settings,
        classify_provider="anthropic",
        anthropic_api_key="test-key",
        google_api_key="",
    )
    return replace(base, **kwargs)


def _gemini_settings(**kwargs: object):
    base = replace(
        settings,
        classify_provider="gemini",
        google_api_key="test-google-key",
        anthropic_api_key="",
    )
    return replace(base, **kwargs)


class ClassificationFallbackTests(unittest.TestCase):
    def tearDown(self) -> None:
        classify._API_AUTH_FAILED = False

    def test_invalid_anthropic_key_falls_back_offline(self) -> None:
        api_settings = _anthropic_settings(anthropic_api_key="invalid")
        provider = Mock()
        provider.name = "anthropic"
        provider.generate_json.side_effect = LLMAuthError("invalid key")

        with (
            patch("ai.classify.settings", api_settings),
            patch("ai.classify.get_provider", return_value=provider) as factory,
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
        self.assertEqual(provider.generate_json.call_count, 1)
        self.assertTrue(classify._API_AUTH_FAILED)
        factory.assert_called()

    def test_invalid_api_key_raises_when_offline_disabled(self) -> None:
        classify._API_AUTH_FAILED = True
        api_settings = _anthropic_settings(anthropic_api_key="invalid")

        with patch("ai.classify.settings", api_settings):
            with self.assertRaises(RuntimeError):
                classify.classify_article(
                    titulo="New publishing merger",
                    resumen="Two book publishers combine their imprints.",
                    medio="Publishers Weekly",
                    categoria_default="noticias",
                    idioma="en",
                    allow_offline=False,
                )

    def test_verify_classify_api_rejects_missing_anthropic_key(self) -> None:
        offline_settings = _anthropic_settings(anthropic_api_key="")
        with patch("ai.classify.settings", offline_settings):
            with self.assertRaises(RuntimeError):
                classify.verify_classify_api()

    def test_verify_classify_api_rejects_missing_gemini_key(self) -> None:
        offline_settings = _gemini_settings(google_api_key="")
        with patch("ai.classify.settings", offline_settings):
            with self.assertRaises(RuntimeError):
                classify.verify_classify_api()

    def test_gemini_classify_uses_json_response(self) -> None:
        gemini_json = (
            '{"categoria":"noticias","relevance_score":4,"en_alcance":true,'
            '"resumen_generado":"Una editorial anuncia novedades.","titular_traducido":'
            '"Novedades editoriales","tags":["mundo_editorial"]}'
        )
        api_settings = _gemini_settings()
        provider = Mock()
        provider.name = "gemini"
        provider.generate_json.return_value = gemini_json

        with (
            patch("ai.classify.settings", api_settings),
            patch("ai.classify.get_provider", return_value=provider) as factory,
        ):
            result = classify.classify_article(
                titulo="Publisher news",
                resumen="A publisher announces books.",
                medio="Publishers Weekly",
                categoria_default="noticias",
                idioma="en",
            )

        provider.generate_json.assert_called_once()
        factory.assert_called()
        self.assertEqual(result.categoria, "noticias")
        self.assertEqual(result.tags, ["mundo_editorial"])
        self.assertIn("editorial", result.resumen_generado.lower())

    def test_gemini_quota_failure_falls_back_offline(self) -> None:
        api_settings = _gemini_settings()
        provider = Mock()
        provider.name = "gemini"
        provider.key_env_name = "GOOGLE_API_KEY"
        provider.generate_json.side_effect = LLMQuotaError("quota exhausted")

        with (
            patch("ai.classify.settings", api_settings),
            patch("ai.classify.get_provider", return_value=provider),
        ):
            result = classify.classify_article(
                titulo="Publisher news",
                resumen="A publisher announces books.",
                medio="Publishers Weekly",
                categoria_default="noticias",
                idioma="en",
            )

        self.assertTrue(classify._API_AUTH_FAILED)
        self.assertIn("GOOGLE_API_KEY", result.resumen_generado)

    def test_active_provider_and_model_reflect_settings(self) -> None:
        api_settings = _gemini_settings()
        with patch("ai.classify.settings", api_settings):
            self.assertEqual(classify.active_provider(), "gemini")
            self.assertEqual(classify.active_model(), "gemini-2.5-flash")

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

            offline_settings = _anthropic_settings(anthropic_api_key="")
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
