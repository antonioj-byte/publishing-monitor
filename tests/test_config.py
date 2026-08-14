"""Tests for bot configuration helpers."""

from __future__ import annotations

import unittest

from bot.config import normalize_gemini_model


class GeminiModelNormalizationTests(unittest.TestCase):
    def test_remaps_retired_flash_lite(self) -> None:
        self.assertEqual(
            normalize_gemini_model("gemini-2.5-flash-lite"),
            "gemini-3.1-flash-lite",
        )

    def test_keeps_current_models(self) -> None:
        self.assertEqual(normalize_gemini_model("gemini-2.5-flash"), "gemini-2.5-flash")
        self.assertEqual(
            normalize_gemini_model("gemini-3.1-flash-lite"),
            "gemini-3.1-flash-lite",
        )


if __name__ == "__main__":
    unittest.main()
