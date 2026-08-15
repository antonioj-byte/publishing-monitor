"""Tests for database export helper."""

from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from bot.db_export import export_database_bytes


class DatabaseExportTests(unittest.TestCase):
    def test_export_database_bytes_creates_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "editorial.db"
            with sqlite3.connect(db_path) as conn:
                conn.execute("CREATE TABLE articulos (id INTEGER PRIMARY KEY, titulo TEXT)")
                conn.execute("INSERT INTO articulos (titulo) VALUES ('Hola')")
                conn.commit()

            with patch("bot.db_export.settings") as mock_settings:
                mock_settings.database_path = str(db_path)
                payload, filename = export_database_bytes()

            self.assertTrue(filename.startswith("editorial-"))
            self.assertTrue(filename.endswith(".db"))

            with tempfile.NamedTemporaryFile(suffix=".db") as out:
                out.write(payload.getvalue())
                out.flush()
                with sqlite3.connect(out.name) as conn:
                    count = conn.execute("SELECT COUNT(*) FROM articulos").fetchone()[0]
            self.assertEqual(count, 1)

    def test_export_database_bytes_missing_file(self) -> None:
        with patch("bot.db_export.settings") as mock_settings:
            mock_settings.database_path = "/tmp/no-existe-editorial.db"
            with self.assertRaises(FileNotFoundError):
                export_database_bytes()


if __name__ == "__main__":
    unittest.main()
