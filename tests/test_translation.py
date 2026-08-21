"""Tests for untranslated-article detection."""

from __future__ import annotations

import unittest

from ai.translation import is_likely_untranslated, is_quota_original_fallback


class TranslationDetectionTests(unittest.TestCase):
    def test_quota_fallback_not_marked_untranslated(self) -> None:
        resumen = (
            "⚠️ Sin créditos en Gemini; mostrando texto original (inglés).\n\n"
            "A publisher announces books."
        )
        self.assertTrue(is_quota_original_fallback(resumen))
        self.assertFalse(
            is_likely_untranslated(
                idioma="en",
                titulo_original="Publisher news",
                titular_traducido=None,
                resumen_generado=resumen,
            )
        )

    def test_plain_english_still_untranslated(self) -> None:
        self.assertTrue(
            is_likely_untranslated(
                idioma="en",
                titulo_original="The publisher news",
                titular_traducido="The publisher news",
                resumen_generado="The publisher announces several books this week.",
            )
        )


if __name__ == "__main__":
    unittest.main()
