"""Tests for the explicit ReportMode enum (reports/report_modes.py)."""

from __future__ import annotations

import unittest

from reports.report_modes import ReportMode


class ReportModeTests(unittest.TestCase):
    def test_from_str_matches_known_modes(self) -> None:
        self.assertEqual(ReportMode.from_str("informe"), ReportMode.DAILY_DIGEST)
        self.assertEqual(ReportMode.from_str("informe_pais"), ReportMode.CATALOG)
        self.assertEqual(ReportMode.from_str("informe_hoy"), ReportMode.TODAY)
        self.assertEqual(ReportMode.from_str("informe_mas"), ReportMode.CONTINUATION)

    def test_from_str_defaults_to_daily_digest_for_unknown_value(self) -> None:
        self.assertEqual(ReportMode.from_str("algo_desconocido"), ReportMode.DAILY_DIGEST)

    def test_str_equality_with_legacy_string_constants(self) -> None:
        # ReportMode is a str subclass so existing `mode == "informe_pais"`
        # comparisons across the codebase keep working unchanged.
        self.assertEqual(ReportMode.CATALOG, "informe_pais")
        self.assertTrue(ReportMode.CATALOG == "informe_pais")
        self.assertIn(ReportMode.TODAY, ("informe_hoy", "informe_pais"))

    def test_is_catalog_only_true_for_catalog_mode(self) -> None:
        self.assertTrue(ReportMode.CATALOG.is_catalog)
        self.assertFalse(ReportMode.DAILY_DIGEST.is_catalog)
        self.assertFalse(ReportMode.TODAY.is_catalog)
        self.assertFalse(ReportMode.CONTINUATION.is_catalog)

    def test_uses_publication_date_excludes_continuation(self) -> None:
        self.assertTrue(ReportMode.DAILY_DIGEST.uses_publication_date)
        self.assertTrue(ReportMode.CATALOG.uses_publication_date)
        self.assertTrue(ReportMode.TODAY.uses_publication_date)
        self.assertFalse(ReportMode.CONTINUATION.uses_publication_date)

    def test_strict_publication_date_only_for_today_and_digest(self) -> None:
        self.assertTrue(ReportMode.TODAY.strict_publication_date)
        self.assertTrue(ReportMode.DAILY_DIGEST.strict_publication_date)
        self.assertFalse(ReportMode.CATALOG.strict_publication_date)
        self.assertFalse(ReportMode.CONTINUATION.strict_publication_date)


if __name__ == "__main__":
    unittest.main()
