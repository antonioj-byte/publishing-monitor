"""Tests for unified /tags + /paises filter listing."""

from __future__ import annotations

import sqlite3
import unittest
from unittest.mock import MagicMock, patch

from bot.filters_info import list_available_filters


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
        INSERT OR IGNORE INTO medios (id, nombre, url_site, metodo, categoria_default, idioma, region, pais)
        VALUES (1, 'Les Inrocks', 'https://example.com', 'rss', 'noticias', 'fr', 'eu', 'fr');
        """
    )
    conn.commit()


class FiltersInfoTests(unittest.TestCase):
    def setUp(self) -> None:
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        _seed_db(self.conn)
        cm = MagicMock()
        cm.__enter__.return_value = self.conn
        cm.__exit__.return_value = False
        self._conn_patch = patch("reports.paises.get_connection", return_value=cm)
        self._conn_patch.start()

    def tearDown(self) -> None:
        self._conn_patch.stop()
        self.conn.close()

    def test_includes_tags_and_countries(self) -> None:
        text = list_available_filters()
        self.assertIn("Tags editoriales", text)
        self.assertIn("Países con medios", text)
        self.assertIn("ficcion", text)
        self.assertIn("/informe 7 ficcion", text)
        self.assertIn("/medios", text)
        self.assertIn("les inrocks", text)
        self.assertNotIn("/tag ", text)
        self.assertNotIn("/paises", text)


if __name__ == "__main__":
    unittest.main()
