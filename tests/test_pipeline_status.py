"""Tests for pipeline/database status helpers."""

from __future__ import annotations

import json
import sqlite3
import unittest
from unittest.mock import MagicMock, patch

from bot.pipeline_status import collect_overview_stats, format_estado_text, format_muestra_text


def _seed_db(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS medios (
            id INTEGER PRIMARY KEY,
            nombre TEXT NOT NULL UNIQUE,
            url_site TEXT NOT NULL,
            metodo TEXT NOT NULL,
            categoria_default TEXT NOT NULL,
            idioma TEXT NOT NULL,
            region TEXT NOT NULL,
            pais TEXT NOT NULL DEFAULT 'xx',
            tier INTEGER NOT NULL DEFAULT 2,
            activo INTEGER NOT NULL DEFAULT 1
        );
        CREATE TABLE IF NOT EXISTS articulos (
            id INTEGER PRIMARY KEY,
            medio_id INTEGER NOT NULL,
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
        CREATE TABLE IF NOT EXISTS informes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha_cierre TEXT NOT NULL,
            tipo TEXT NOT NULL,
            articulos_incluidos TEXT NOT NULL,
            enviado_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        DELETE FROM articulos;
        DELETE FROM medios;
        DELETE FROM informes;
        """
    )
    conn.execute(
        """
        INSERT INTO medios (id, nombre, url_site, metodo, categoria_default, idioma, region, pais, tier)
        VALUES (1, 'Test Medio', 'https://example.com', 'rss', 'noticias', 'es', 'eu', 'es', 1)
        """
    )
    conn.execute(
        """
        INSERT INTO articulos (
            id, medio_id, url, titulo_original, fecha_ingesta, categoria, idioma,
            resumen_generado, relevance_score, hash_contenido, procesado, enviado, tags
        ) VALUES
        (1, 1, 'https://example.com/a1', 'Libro uno', '2026-08-14T10:00:00', 'noticias', 'es',
         'Resumen del libro uno.', 4, 'hash1', 1, 0, ?),
        (2, 1, 'https://example.com/a2', 'Libro dos', '2026-08-13T10:00:00', 'noticias', 'es',
         'Resumen del libro dos.', 3, 'hash2', 1, 0, '[]'),
        (3, 1, 'https://example.com/a3', 'Libro tres', '2026-08-12T10:00:00', 'noticias', 'es',
         NULL, NULL, 'hash3', 0, 0, NULL)
        """,
        (json.dumps(["ficcion", "literatura_local"]),),
    )
    conn.commit()


class PipelineStatusTests(unittest.TestCase):
    def setUp(self) -> None:
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        _seed_db(self.conn)
        cm = MagicMock()
        cm.__enter__.return_value = self.conn
        cm.__exit__.return_value = False
        self._conn_patch = patch("bot.pipeline_status.get_connection", return_value=cm)
        self._gen_conn_patch = patch("reports.generator.get_connection", return_value=cm)
        self._init_patch = patch("bot.pipeline_status.init_schema")
        self._conn_patch.start()
        self._gen_conn_patch.start()
        self._init_patch.start()

    def tearDown(self) -> None:
        self._init_patch.stop()
        self._gen_conn_patch.stop()
        self._conn_patch.stop()
        self.conn.close()

    def test_collect_overview_stats(self) -> None:
        stats = collect_overview_stats()
        self.assertEqual(stats.total, 3)
        self.assertEqual(stats.pending, 1)
        self.assertEqual(stats.classified, 2)
        self.assertEqual(stats.with_tags, 1)
        self.assertEqual(stats.missing_tags, 1)

    def test_format_estado_text_includes_counts(self) -> None:
        text = format_estado_text()
        self.assertIn("Artículos totales: 3", text)
        self.assertIn("pendientes clasificar: 1", text)
        self.assertIn("con tags editoriales: 1", text)

    def test_format_muestra_text_lists_classified_articles(self) -> None:
        text = format_muestra_text(limit=2)
        self.assertIn("Libro uno", text)
        self.assertIn("Ficción", text)
        self.assertIn("Score 4", text)

    def test_format_muestra_text_only_untagged(self) -> None:
        text = format_muestra_text(limit=5, only_untagged=True)
        self.assertIn("Libro dos", text)
        self.assertNotIn("Libro uno", text)


if __name__ == "__main__":
    unittest.main()
