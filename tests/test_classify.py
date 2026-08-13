"""Tests for resilient article classification."""

from __future__ import annotations

import unittest
from dataclasses import replace
from unittest.mock import Mock, patch

import anthropic
import httpx

import ai.classify as classify
from bot.config import settings


class ClassificationFallbackTests(unittest.TestCase):
    def tearDown(self) -> None:
        classify._API_AUTH_FAILED = False

    def test_invalid_api_key_falls_back_offline_for_current_and_later_articles(
        self,
    ) -> None:
        request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
        response = httpx.Response(401, request=request)
        auth_error = anthropic.AuthenticationError(
            "invalid key",
            response=response,
            body=None,
        )
        client = Mock()
        client.messages.create.side_effect = auth_error
        api_settings = replace(settings, anthropic_api_key="invalid")

        with (
            patch("ai.classify.settings", api_settings),
            patch("ai.classify.anthropic.Anthropic", return_value=client) as factory,
        ):
            first = classify.classify_article(
                titulo="New publishing merger",
                resumen="Two book publishers combine their imprints.",
                medio="Publishers Weekly",
                categoria_default="noticias",
                idioma="en",
            )
            second = classify.classify_article(
                titulo="New literary prize",
                resumen="A novelist wins a major book award.",
                medio="Publishers Weekly",
                categoria_default="noticias",
                idioma="en",
            )

        self.assertTrue(first.en_alcance)
        self.assertTrue(second.en_alcance)
        self.assertEqual(factory.call_count, 1)
        self.assertTrue(classify._API_AUTH_FAILED)


if __name__ == "__main__":
    unittest.main()
