"""Tests for Telegram report parsing with tags."""

from __future__ import annotations

import unittest

from bot.report_parser import DEFAULT_FILTER_DAYS, parse_command_args, parse_free_text


class ReportParserTagTests(unittest.TestCase):
    def test_no_args_returns_none_for_daily_informe(self) -> None:
        self.assertIsNone(parse_command_args([]))

    def test_informe_country_only_defaults_days(self) -> None:
        parsed = parse_command_args(["alemania"])
        assert parsed is not None
        self.assertEqual(parsed.days, DEFAULT_FILTER_DAYS)
        self.assertEqual(parsed.pais, "de")
        self.assertEqual(parsed.tags, [])

    def test_informe_country_with_days(self) -> None:
        parsed = parse_command_args(["7", "alemania"])
        assert parsed is not None
        self.assertEqual(parsed.days, 7)
        self.assertEqual(parsed.pais, "de")
        self.assertEqual(parsed.tags, [])

    def test_informe_tag_only_defaults_days(self) -> None:
        parsed = parse_command_args(["ficcion"])
        assert parsed is not None
        self.assertEqual(parsed.days, DEFAULT_FILTER_DAYS)
        self.assertEqual(parsed.tags, ["ficcion"])
        self.assertIsNone(parsed.pais)

    def test_informe_tag_with_days_flexible_order(self) -> None:
        parsed = parse_command_args(["ficcion", "7"])
        assert parsed is not None
        self.assertEqual(parsed.days, 7)
        self.assertEqual(parsed.tags, ["ficcion"])

    def test_informe_days_only(self) -> None:
        parsed = parse_command_args(["7"])
        assert parsed is not None
        self.assertEqual(parsed.days, 7)
        self.assertEqual(parsed.tags, [])
        self.assertIsNone(parsed.pais)

    def test_free_text_country_before_days(self) -> None:
        parsed = parse_free_text("informe alemania no ficción 7 días")
        assert parsed is not None
        self.assertEqual(parsed.pais, "de")
        self.assertIn("no_ficcion", parsed.tags)

    def test_informe_tag_slug_with_underscore(self) -> None:
        parsed = parse_command_args(["7", "literatura_local"])
        assert parsed is not None
        self.assertEqual(parsed.tags, ["literatura_local"])
        self.assertIsNone(parsed.pais)

    def test_informe_country_and_single_tag(self) -> None:
        parsed = parse_command_args(["7", "alemania", "poesia"])
        assert parsed is not None
        self.assertEqual(parsed.pais, "de")
        self.assertEqual(parsed.tags, ["poesia"])

    def test_informe_keeps_only_first_tag(self) -> None:
        parsed = parse_command_args(["7", "ficcion", "poesia"])
        assert parsed is not None
        self.assertEqual(parsed.tags, ["ficcion"])

    def test_tag_command_style_via_informe(self) -> None:
        parsed = parse_command_args(["ferias_premios", "14", "españa"])
        self.assertEqual(parsed.days, 14)
        self.assertIn("ferias_premios", parsed.tags)
        self.assertEqual(parsed.pais, "es")

    def test_free_text_with_tag(self) -> None:
        parsed = parse_free_text("informe últimos 7 días ficción en alemania")
        assert parsed is not None
        self.assertIn("ficcion", parsed.tags)
        self.assertEqual(parsed.pais, "de")

    def test_informe_medio_only_defaults_days(self) -> None:
        parsed = parse_command_args(["les", "inrocks"])
        assert parsed is not None
        self.assertEqual(parsed.days, DEFAULT_FILTER_DAYS)
        self.assertEqual(parsed.medio_nombre, "Les Inrocks")
        self.assertIsNone(parsed.pais)

    def test_informe_medio_with_days(self) -> None:
        parsed = parse_command_args(["7", "les", "inrocks"])
        assert parsed is not None
        self.assertEqual(parsed.days, 7)
        self.assertEqual(parsed.medio_nombre, "Les Inrocks")

    def test_informe_medio_and_tag(self) -> None:
        parsed = parse_command_args(["7", "les", "inrocks", "ficcion"])
        assert parsed is not None
        self.assertEqual(parsed.medio_nombre, "Les Inrocks")
        self.assertEqual(parsed.tags, ["ficcion"])

    def test_informe_le_monde_livres(self) -> None:
        parsed = parse_command_args(["le", "monde", "livres"])
        assert parsed is not None
        self.assertEqual(parsed.medio_nombre, "Le Monde Livres")

    def test_free_text_medio(self) -> None:
        parsed = parse_free_text("informe últimos 7 días les inrocks")
        assert parsed is not None
        self.assertEqual(parsed.medio_nombre, "Les Inrocks")
        self.assertEqual(parsed.days, 7)


if __name__ == "__main__":
    unittest.main()
