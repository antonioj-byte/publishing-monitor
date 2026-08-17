"""Tests for medios.csv → SQLite sync."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from db.connection import get_connection, init_schema
from scripts.load_medios import load_medios


class LoadMediosTests(unittest.TestCase):
    def test_load_medios_reports_inserted_names(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "test.db"
            csv_path = Path(tmp) / "medios.csv"
            csv_path.write_text(
                "nombre,url_site,url_rss,url_scraping,metodo,categoria_default,"
                "idioma,region,pais,activo\n"
                "Test Medio,https://example.com,https://example.com/rss,,rss,"
                "noticias,es,eu,es,true\n",
                encoding="utf-8",
            )

            import bot.config as config

            old_db = config.settings.database_path
            object.__setattr__(config.settings, "database_path", db_path)
            try:
                init_schema()
                stats = load_medios(csv_path)
                self.assertEqual(stats["inserted"], 1)
                self.assertIn("Test Medio", stats["inserted_names"])

                stats2 = load_medios(csv_path)
                self.assertEqual(stats2["inserted"], 0)
                self.assertEqual(stats2["inserted_names"], [])

                with get_connection() as conn:
                    count = conn.execute(
                        "SELECT COUNT(*) FROM medios WHERE nombre = ?", ("Test Medio",)
                    ).fetchone()[0]
                self.assertEqual(count, 1)
            finally:
                object.__setattr__(config.settings, "database_path", old_db)


if __name__ == "__main__":
    unittest.main()
