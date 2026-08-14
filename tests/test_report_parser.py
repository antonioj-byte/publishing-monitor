"""Tests for Telegram report parsing with tags."""

from __future__ import annotations

import unittest

from bot.report_parser import parse_command_args, parse_free_text, parse_tag_command_args


class ReportParserTagTests(unittest.TestCase):
    def test_informe_country_only(self) -> None:
        parsed = parse_command_args(["7", "alemania"])
        assert parsed is not None
        self.assertEqual(parsed.days, 7)
        self.assertEqual(parsed.pais, "de")
        self.assertEqual(parsed.tags, [])

    def test_informe_tag_only(self) -> None:
        parsed = parse_command_args(["7", "ficcion"])
        assert parsed is not None
        self.assertEqual(parsed.tags, ["ficcion"])
        self.assertIsNone(parsed.pais)

    def test_informe_country_and_tag(self) -> None:
        parsed = parse_command_args(["7", "alemania", "poesia"])
        assert parsed is not None
        self.assertEqual(parsed.pais, "de")
        self.assertIn("poesia", parsed.tags)

    def test_tag_command(self) -> None:
        parsed = parse_tag_command_args(["ferias_premios", "14", "españa"])
        self.assertEqual(parsed.days, 14)
        self.assertIn("ferias_premios", parsed.tags)
        self.assertEqual(parsed.pais, "es")

    def test_free_text_with_tag(self) -> None:
        parsed = parse_free_text("informe últimos 7 días ficción en alemania")
        assert parsed is not None
        self.assertIn("ficcion", parsed.tags)
        self.assertEqual(parsed.pais, "de")


if __name__ == "__main__":
    unittest.main()
