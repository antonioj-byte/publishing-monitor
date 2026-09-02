"""Tests for informe shortfall hints."""

from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from bot.pipeline_status import informe_shortfall_hint


class InformeShortfallTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmp.name) / "test.db"
        conn = sqlite3.connect(self.db_path)
        conn.executescript(
            """
            CREATE TABLE informes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fecha_cierre TEXT NOT NULL,
                tipo TEXT NOT NULL,
                articulos_incluidos TEXT NOT NULL,
                enviado_at TEXT NOT NULL
            );
            CREATE TABLE articulos (
                id INTEGER PRIMARY KEY,
                medio_id INTEGER NOT NULL DEFAULT 1,
                url TEXT NOT NULL UNIQUE,
                titulo_original TEXT NOT NULL,
                fecha_publicacion TEXT,
                fecha_ingesta TEXT NOT NULL,
                categoria TEXT NOT NULL,
                idioma TEXT NOT NULL,
                resumen_generado TEXT,
                relevance_score INTEGER,
                hash_contenido TEXT NOT NULL UNIQUE,
                procesado INTEGER NOT NULL DEFAULT 0,
                enviado INTEGER NOT NULL DEFAULT 0,
                tags TEXT
            );
            """
        )
        conn.execute(
            """
            INSERT INTO articulos (
                id, url, titulo_original, fecha_ingesta, categoria, idioma,
                hash_contenido, procesado
            ) VALUES (1, 'https://example.com/p', 'Pendiente', '2026-09-02T08:00:00',
                      'noticias', 'es', 'h1', 0)
            """
        )
        conn.commit()
        conn.close()

    def tearDown(self) -> None:
        self.tmp.cleanup()

    @patch("bot.pipeline_status.settings")
    @patch("bot.pipeline_status._resolve_window")
    @patch("bot.pipeline_status.get_connection")
    def test_hint_when_pending_in_window(
        self, mock_conn, mock_window, mock_settings
    ) -> None:
        mock_settings.timezone = "Europe/Madrid"
        mock_settings.min_relevance_score = 3
        from datetime import datetime
        from zoneinfo import ZoneInfo

        tz = ZoneInfo("Europe/Madrid")
        mock_window.return_value = (
            datetime(2026, 9, 1, 6, 0, tzinfo=tz),
            False,
            "informe",
        )
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row

        class _Ctx:
            def __enter__(self):
                return conn

            def __exit__(self, *args):
                pass

        mock_conn.return_value = _Ctx()
        hint = informe_shortfall_hint(article_count=3)
        self.assertIsNotNone(hint)
        self.assertIn("/clasificar", hint)
        self.assertIn("pendientes", hint)
        conn.close()


if __name__ == "__main__":
    unittest.main()
