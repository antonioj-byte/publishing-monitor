"""Tests for retranslation helpers."""

from __future__ import annotations

import sqlite3
import unittest
from tempfile import TemporaryDirectory
from unittest.mock import patch

from ai.translation import is_likely_untranslated
from bot.retranslate_service import find_untranslated_ids


class RetranslateServiceTests(unittest.TestCase):
    def test_find_untranslated_detects_english_summary(self) -> None:
        with TemporaryDirectory() as temp_dir:
            db_path = temp_dir + "/test.db"
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
                    titular_traducido TEXT,
                    resumen_generado TEXT,
                    resumen_raw TEXT,
                    idioma TEXT,
                    procesado INTEGER,
                    fecha_ingesta TEXT
                );
                INSERT INTO medios VALUES (1, 'The Atlantic', 'noticias', 2, 'us', 'us');
                INSERT INTO articulos VALUES (
                    1, 1, 'Tallying', NULL,
                    'The poem explores memory and the body in English prose here.',
                    'The poem explores memory and the body in English prose here.',
                    'en', 1, '2026-08-23T10:00:00'
                );
                """
            )
            conn.commit()
            conn.close()

            with patch("bot.retranslate_service.get_connection") as mock_conn:
                cm = mock_conn.return_value
                test_conn = sqlite3.connect(db_path)
                test_conn.row_factory = sqlite3.Row
                cm.__enter__.return_value = test_conn
                cm.__exit__.return_value = False
                with patch("bot.retranslate_service.init_schema"):
                    ids = find_untranslated_ids(limit=5)

            self.assertEqual(ids, [1])

    def test_offline_placeholder_counts_as_untranslated(self) -> None:
        self.assertTrue(
            is_likely_untranslated(
                idioma="en",
                titulo_original="Title",
                titular_traducido="[EN] Title",
                resumen_generado=(
                    "Resumen no disponible en castellano (clasificación offline)."
                ),
            )
        )


if __name__ == "__main__":
    unittest.main()
