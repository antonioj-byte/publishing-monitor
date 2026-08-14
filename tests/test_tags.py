"""Tests for topical tag resolution."""

from __future__ import annotations

import unittest

from reports.tags import extract_tags_from_text, resolve_tag, validate_tags


class TagResolutionTests(unittest.TestCase):
    def test_resolve_spanish_aliases(self) -> None:
        key, label = resolve_tag("ficción")
        self.assertEqual(key, "ficcion")
        self.assertEqual(label, "Ficción")

    def test_extract_slug_with_underscore(self) -> None:
        keys, remainder = extract_tags_from_text("literatura_local")
        self.assertEqual(keys, ["literatura_local"])
        self.assertEqual(remainder, "")

    def test_extract_no_ficcion_slug(self) -> None:
        keys, _ = extract_tags_from_text("no_ficcion")
        self.assertEqual(keys, ["no_ficcion"])

    def test_extract_multiword_tag(self) -> None:
        keys, remainder = extract_tags_from_text("ferias y premios en alemania")
        self.assertIn("ferias_premios", keys)
        self.assertIn("alemania", remainder)

    def test_validate_tags_filters_unknown(self) -> None:
        self.assertEqual(validate_tags(["ficcion", "invalido", "poesia"]), ["ficcion", "poesia"])


if __name__ == "__main__":
    unittest.main()
