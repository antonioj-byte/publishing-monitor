"""Tests for informal report intents and voice-oriented parsing."""

from __future__ import annotations

import unittest

from bot.request_intent import informal_ack, parse_user_request


class InformalRequestTests(unittest.TestCase):
    def test_informal_week_phrase(self) -> None:
        req = parse_user_request("dame ficción de la semana")
        self.assertEqual(req.kind, "filtered")
        assert req.filter is not None
        self.assertEqual(req.filter.days, 7)
        self.assertIn("ficcion", req.filter.tags)

    def test_que_hay_de_tag(self) -> None:
        req = parse_user_request("qué hay de literatura local")
        self.assertEqual(req.kind, "filtered")
        assert req.filter is not None
        self.assertIn("literatura_local", req.filter.tags)

    def test_hoy_informal(self) -> None:
        req = parse_user_request("ponme lo de hoy")
        self.assertEqual(req.kind, "hoy")

    def test_continuation_informal(self) -> None:
        req = parse_user_request("dame el resto")
        self.assertEqual(req.kind, "continuation")

    def test_voice_style_blob(self) -> None:
        req = parse_user_request("eh oye informe de poesía en francia esta semana")
        self.assertEqual(req.kind, "filtered")
        assert req.filter is not None
        self.assertEqual(req.filter.days, 7)
        self.assertIn("poesia", req.filter.tags)

    def test_informal_ack_filtered(self) -> None:
        req = parse_user_request("informe 7 ficcion")
        assert req.filter is not None
        text = informal_ack(req)
        self.assertIn("7 días", text)
        self.assertIn("ficción", text.lower())


if __name__ == "__main__":
    unittest.main()
