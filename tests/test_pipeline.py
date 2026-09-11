"""Tests for report pipeline batch sizing."""

from __future__ import annotations

import unittest

from reports.pipeline import (
    _batches_for_daily_pending,
    _batches_for_filtered_pending,
    _batches_for_hoy_pending,
    _batches_for_telegram_mode,
    _max_classify_batches,
    _should_classify_for_filter,
)


class PipelineBatchTests(unittest.TestCase):
    def test_scales_with_pending_count(self) -> None:
        self.assertEqual(_max_classify_batches(0), 0)
        self.assertGreaterEqual(_max_classify_batches(103), 6)
        self.assertLessEqual(_max_classify_batches(5000), 60)

    def test_should_classify_for_country_or_tag_filter(self) -> None:
        from db.models import ReportFilter

        self.assertTrue(
            _should_classify_for_filter(
                "informe_pais",
                ReportFilter(days=1, pais="it", location_label="Italia"),
            )
        )
        self.assertTrue(
            _should_classify_for_filter(
                "informe_pais",
                ReportFilter(days=7, pais="de", location_label="Alemania"),
            )
        )
        self.assertTrue(
            _should_classify_for_filter(
                "informe_pais",
                ReportFilter(days=7, region="eu", location_label="Europa"),
            )
        )
        self.assertTrue(_should_classify_for_filter("informe_hoy", None))
        self.assertFalse(_should_classify_for_filter("informe", None))

    def test_batches_for_filtered_pending_scales_by_country_queue(self) -> None:
        self.assertEqual(_batches_for_filtered_pending(13), 1)
        self.assertEqual(_batches_for_filtered_pending(20), 1)
        self.assertEqual(_batches_for_filtered_pending(21), 2)
        self.assertEqual(_batches_for_filtered_pending(100), 5)
        self.assertEqual(_batches_for_filtered_pending(200), 5)

    def test_batches_for_daily_pending_caps_at_five(self) -> None:
        self.assertEqual(_batches_for_daily_pending(0), 0)
        self.assertEqual(_batches_for_daily_pending(20), 1)
        self.assertEqual(_batches_for_daily_pending(100), 5)
        self.assertEqual(_batches_for_daily_pending(500), 5)

    def test_batches_for_hoy_pending_caps_at_two(self) -> None:
        self.assertEqual(_batches_for_hoy_pending(0), 0)
        self.assertEqual(_batches_for_hoy_pending(20), 1)
        self.assertEqual(_batches_for_hoy_pending(40), 2)
        self.assertEqual(_batches_for_hoy_pending(100), 2)

    def test_batches_for_telegram_mode(self) -> None:
        self.assertEqual(_batches_for_telegram_mode("informe_hoy", 100), 2)
        self.assertEqual(_batches_for_telegram_mode("informe", 100), 5)
        self.assertEqual(_batches_for_telegram_mode("informe_pais", 100), 5)


if __name__ == "__main__":
    unittest.main()
