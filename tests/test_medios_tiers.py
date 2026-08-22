"""Tests for canonical media tier lists."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from medios_tiers import get_tier


class MediosTierTests(unittest.TestCase):
    def test_tier1_prensa_especializada(self) -> None:
        self.assertEqual(get_tier("Publishers Weekly"), 1)
        self.assertEqual(get_tier("The Bookseller"), 1)
        self.assertEqual(get_tier("Publishnews"), 1)

    def test_tier1_revistas_literarias(self) -> None:
        self.assertEqual(get_tier("The New Yorker"), 1)
        self.assertEqual(get_tier("London Review of Books"), 1)

    def test_granta_is_tier2(self) -> None:
        self.assertEqual(get_tier("Granta", "ideas"), 2)

    def test_economist_culture_is_tier2(self) -> None:
        self.assertEqual(get_tier("The Economist Culture"), 2)

    def test_no_blanket_ideas_promotion(self) -> None:
        self.assertEqual(get_tier("Letras Libres", "ideas"), 2)


if __name__ == "__main__":
    unittest.main()
