"""Tests for media outlet name resolution."""

from __future__ import annotations

import unittest

from reports.medios_lookup import (
    extract_medio_from_text,
    list_available_medios,
    resolve_medio,
)


class MediosLookupTests(unittest.TestCase):
    def test_resolve_canonical_name(self) -> None:
        self.assertEqual(resolve_medio("Les Inrocks"), "Les Inrocks")

    def test_resolve_alias_without_prefix(self) -> None:
        self.assertEqual(resolve_medio("inrocks"), "Les Inrocks")

    def test_resolve_le_monde_livres(self) -> None:
        self.assertEqual(resolve_medio("le monde livres"), "Le Monde Livres")

    def test_extract_from_free_text(self) -> None:
        medio, remainder = extract_medio_from_text("informe les inrocks ficcion")
        self.assertEqual(medio, "Les Inrocks")
        self.assertIn("ficcion", remainder)

    def test_list_available_includes_examples(self) -> None:
        text = list_available_medios(limit=5)
        self.assertIn("/informe 7 les inrocks", text)
        self.assertIn("Medios disponibles", text)


if __name__ == "__main__":
    unittest.main()
