"""Tests for retag / backfill article selection."""

from __future__ import annotations

import sqlite3
import unittest
from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from bot.reclassify_service import mark_untagged_for_reclassify


class RetagSelectionTests(unittest.TestCase):
    def test_marks_pending_articles_without_tags(self) -> None:
        with TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "test.db"
            conn = sqlite3.connect(db_path)
            conn.executescript(
                """
                CREATE TABLE articulos (
                    id INTEGER PRIMARY KEY,
                    procesado INTEGER,
                    tags TEXT
                );
                INSERT INTO articulos VALUES
                    (1, 1, '["ficcion"]'),
                    (2, 0, NULL),
                    (3, 1, '[]'),
                    (4, 0, '[]');
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

            with patch("bot.reclassify_service.get_connection", test_connection):
                queued = mark_untagged_for_reclassify()

            conn = sqlite3.connect(db_path)
            rows = dict(conn.execute("SELECT id, procesado FROM articulos").fetchall())
            conn.close()

        self.assertEqual(queued, 3)
        self.assertEqual(rows[1], 1)
        self.assertEqual(rows[2], 0)
        self.assertEqual(rows[3], 0)
        self.assertEqual(rows[4], 0)


if __name__ == "__main__":
    unittest.main()
