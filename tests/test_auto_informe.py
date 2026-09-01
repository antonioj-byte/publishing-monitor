"""Tests for automatic informe reliability helpers."""

from __future__ import annotations

import sqlite3
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo

from reports.generator import informe_automatico_sent_today


class AutoInformeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmp.name) / "test.db"
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            """
            CREATE TABLE informes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fecha_cierre TEXT NOT NULL,
                tipo TEXT NOT NULL,
                articulos_incluidos TEXT NOT NULL,
                enviado_at TEXT NOT NULL
            )
            """
        )
        conn.commit()
        conn.close()

    def tearDown(self) -> None:
        self.tmp.cleanup()

    @patch("reports.generator.settings")
    @patch("reports.generator.get_connection")
    def test_informe_automatico_sent_today_true(self, mock_conn, mock_settings) -> None:
        mock_settings.timezone = "Europe/Madrid"
        tz = ZoneInfo("Europe/Madrid")
        now = datetime.now(tz)
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute(
            "INSERT INTO informes (fecha_cierre, tipo, articulos_incluidos, enviado_at) VALUES (?, ?, ?, ?)",
            (
                now.isoformat(),
                "automatico",
                "[]",
                now.astimezone(ZoneInfo("UTC")).isoformat(),
            ),
        )
        conn.commit()

        class _Ctx:
            def __enter__(self):
                return conn

            def __exit__(self, *args):
                conn.close()

        mock_conn.return_value = _Ctx()
        self.assertTrue(informe_automatico_sent_today())

    @patch("reports.generator.settings")
    @patch("reports.generator.get_connection")
    def test_informe_automatico_sent_today_false_when_only_manual(self, mock_conn, mock_settings) -> None:
        mock_settings.timezone = "Europe/Madrid"
        tz = ZoneInfo("Europe/Madrid")
        now = datetime.now(tz)
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute(
            "INSERT INTO informes (fecha_cierre, tipo, articulos_incluidos, enviado_at) VALUES (?, ?, ?, ?)",
            (
                now.isoformat(),
                "manual",
                "[]",
                now.astimezone(ZoneInfo("UTC")).isoformat(),
            ),
        )
        conn.commit()

        class _Ctx:
            def __enter__(self):
                return conn

            def __exit__(self, *args):
                conn.close()

        mock_conn.return_value = _Ctx()
        self.assertFalse(informe_automatico_sent_today())


if __name__ == "__main__":
    unittest.main()
