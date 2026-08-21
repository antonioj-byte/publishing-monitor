"""Tests for API usage tracking and /gasto formatting."""

from __future__ import annotations

import sqlite3
import tempfile
import unittest
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from ai.usage_tracking import (
    estimate_cost_usd,
    format_gasto_text,
    record_api_usage,
)
from bot.config import settings


class UsageTrackingTests(unittest.TestCase):
    def test_estimate_cost_usd_gemini(self) -> None:
        cost = estimate_cost_usd(
            provider="gemini",
            model="gemini-2.5-flash",
            input_tokens=1_000_000,
            output_tokens=0,
        )
        self.assertAlmostEqual(cost, 0.30, places=4)

    def test_format_gasto_includes_periods(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "test.db"
            conn = sqlite3.connect(db_path)
            conn.executescript(
                """
                CREATE TABLE articulos (
                    id INTEGER PRIMARY KEY,
                    procesado INTEGER
                );
                INSERT INTO articulos VALUES (1, 1), (2, 1);
                CREATE TABLE api_usage_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL DEFAULT (datetime('now')),
                    operation TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    model TEXT,
                    input_tokens INTEGER NOT NULL DEFAULT 0,
                    output_tokens INTEGER NOT NULL DEFAULT 0,
                    estimated_usd REAL NOT NULL DEFAULT 0
                );
                INSERT INTO api_usage_events (
                    operation, provider, model, input_tokens, output_tokens, estimated_usd
                ) VALUES ('classify', 'gemini', 'gemini-2.5-flash', 1000, 200, 0.0008);
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

            gemini_settings = replace(
                settings,
                classify_provider="gemini",
                google_api_key="test-key",
                anthropic_api_key="",
            )

            with (
                patch("db.connection.init_schema"),
                patch("db.connection.get_connection", test_connection),
                patch("ai.usage_tracking.get_connection", test_connection),
                patch("ai.classify.settings", gemini_settings),
                patch("ai.classify.get_provider") as mock_provider,
            ):
                mock_provider.return_value.primary_model = "gemini-2.5-flash"
                text = format_gasto_text(days=30)

        self.assertIn("Gasto API estimado", text)
        self.assertIn("Clasificación", text)
        self.assertIn("Últimos 7 días", text)
        self.assertIn("gemini", text)

    def test_record_api_usage_persists(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "test.db"
            object.__setattr__(settings, "database_path", db_path)
            conn = sqlite3.connect(db_path)
            conn.execute(
                """
                CREATE TABLE api_usage_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL DEFAULT (datetime('now')),
                    operation TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    model TEXT,
                    input_tokens INTEGER NOT NULL DEFAULT 0,
                    output_tokens INTEGER NOT NULL DEFAULT 0,
                    estimated_usd REAL NOT NULL DEFAULT 0
                )
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

            with patch("ai.usage_tracking.get_connection", test_connection):
                record_api_usage(
                    operation="classify",
                    provider="gemini",
                    model="gemini-2.5-flash",
                    input_tokens=500,
                    output_tokens=100,
                    estimated_usd=0.0005,
                )

            conn = sqlite3.connect(db_path)
            count = conn.execute("SELECT COUNT(*) FROM api_usage_events").fetchone()[0]
            conn.close()
            self.assertEqual(count, 1)


if __name__ == "__main__":
    unittest.main()
