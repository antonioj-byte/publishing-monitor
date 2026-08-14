"""Tests for unified /tags + /paises filter listing."""

from __future__ import annotations

import unittest

from bot.filters_info import list_available_filters


class FiltersInfoTests(unittest.TestCase):
    def test_includes_tags_and_countries(self) -> None:
        text = list_available_filters()
        self.assertIn("Tags editoriales", text)
        self.assertIn("Países con medios", text)
        self.assertIn("ficcion", text)
        self.assertIn("/informe 7 ficcion", text)
        self.assertNotIn("/tag ", text)
        self.assertNotIn("/paises", text)


if __name__ == "__main__":
    unittest.main()
