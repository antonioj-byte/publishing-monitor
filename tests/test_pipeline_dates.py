"""Tests for shared pipeline date rules."""

from __future__ import annotations

import unittest

from reports.pipeline_dates import date_flags_for_mode, pending_date_sql


class PipelineDatesTests(unittest.TestCase):
    def test_daily_digest_uses_strict_publication(self) -> None:
        use_pub, strict = date_flags_for_mode("informe")
        self.assertTrue(use_pub)
        self.assertTrue(strict)

    def test_catalog_allows_ingesta_fallback(self) -> None:
        use_pub, strict = date_flags_for_mode("informe_pais")
        self.assertTrue(use_pub)
        self.assertFalse(strict)

    def test_today_strict_publication_sql(self) -> None:
        expr, extra = pending_date_sql(
            date_by_publication=True,
            strict_publication=True,
        )
        self.assertIn("fecha_publicacion", expr)
        self.assertIn("IS NOT NULL", extra)

    def test_ingesta_mode(self) -> None:
        expr, extra = pending_date_sql(
            date_by_publication=False,
            strict_publication=False,
        )
        self.assertIn("fecha_ingesta", expr)
        self.assertEqual(extra, "")


if __name__ == "__main__":
    unittest.main()
