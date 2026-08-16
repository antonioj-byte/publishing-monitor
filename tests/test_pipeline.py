"""Tests for report pipeline batch sizing."""

from __future__ import annotations

import unittest

from reports.pipeline import _max_classify_batches, _should_classify_for_filter


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
        self.assertTrue(_should_classify_for_filter("informe_hoy", None))
        self.assertFalse(_should_classify_for_filter("informe", None))


if __name__ == "__main__":
    unittest.main()
