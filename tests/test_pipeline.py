"""Tests for report pipeline batch sizing."""

from __future__ import annotations

import unittest

from reports.pipeline import _max_classify_batches


class PipelineBatchTests(unittest.TestCase):
    def test_scales_with_pending_count(self) -> None:
        self.assertEqual(_max_classify_batches(0), 5)
        self.assertGreaterEqual(_max_classify_batches(103), 7)
        self.assertLessEqual(_max_classify_batches(5000), 60)


if __name__ == "__main__":
    unittest.main()
