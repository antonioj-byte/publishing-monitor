"""Tests for the unified LLM provider abstraction (ai/llm_provider.py)."""

from __future__ import annotations

import unittest
from unittest.mock import Mock, patch

import anthropic
import httpx

from ai.llm_provider import (
    AnthropicProvider,
    GeminiProvider,
    LLMAuthError,
    LLMQuotaError,
    get_provider,
)
from bot.config import settings
from dataclasses import replace


class GeminiProviderTests(unittest.TestCase):
    def _provider(self, api_key: str = "test-key") -> GeminiProvider:
        return GeminiProvider(
            api_key=api_key, model="gemini-2.5-flash", fallback_model="gemini-3.1-flash-lite"
        )

    def test_generate_json_returns_response_text(self) -> None:
        provider = self._provider()
        response = Mock(text='{"ok": true}')
        client = Mock()
        client.models.generate_content.return_value = response

        with patch.object(GeminiProvider, "_client", return_value=client):
            result = provider.generate_json(system_prompt="sys", user_msg="hi")

        self.assertEqual(result, '{"ok": true}')

    def test_generate_json_falls_back_to_second_model_on_generic_error(self) -> None:
        provider = self._provider()
        response = Mock(text='{"ok": true}')
        client = Mock()
        client.models.generate_content.side_effect = [
            RuntimeError("temporary 503"),
            response,
        ]

        with patch.object(GeminiProvider, "_client", return_value=client):
            result = provider.generate_json(system_prompt="sys", user_msg="hi")

        self.assertEqual(result, '{"ok": true}')
        self.assertEqual(client.models.generate_content.call_count, 2)

    def test_generate_json_raises_llm_auth_error_on_invalid_key(self) -> None:
        provider = self._provider()
        client = Mock()
        client.models.generate_content.side_effect = RuntimeError("401 invalid api key")

        with patch.object(GeminiProvider, "_client", return_value=client):
            with self.assertRaises(LLMAuthError):
                provider.generate_json(system_prompt="sys", user_msg="hi")
        # Should not retry the fallback model for a fatal auth error.
        self.assertEqual(client.models.generate_content.call_count, 1)

    def test_generate_json_raises_llm_quota_error_on_quota_exhausted(self) -> None:
        provider = self._provider()
        client = Mock()
        client.models.generate_content.side_effect = RuntimeError("RESOURCE_EXHAUSTED quota")

        with patch.object(GeminiProvider, "_client", return_value=client):
            with self.assertRaises(LLMQuotaError):
                provider.generate_json(system_prompt="sys", user_msg="hi")

    def test_verify_api_rejects_missing_key(self) -> None:
        provider = self._provider(api_key="")
        with self.assertRaises(LLMAuthError):
            provider.verify_api()

    def test_verify_api_succeeds(self) -> None:
        provider = self._provider()
        client = Mock()
        client.models.generate_content.return_value = Mock(text="ok")

        with patch.object(GeminiProvider, "_client", return_value=client):
            provider.verify_api()  # should not raise

    def test_client_is_reused_across_calls(self) -> None:
        provider = self._provider()
        client = Mock()
        client.models.generate_content.return_value = Mock(text='{"ok": true}')

        with patch.object(GeminiProvider, "_client", return_value=client) as factory:
            provider.generate_json(system_prompt="sys", user_msg="a")
            provider.generate_json(system_prompt="sys", user_msg="b")

        self.assertEqual(factory.call_count, 2)
        self.assertEqual(client.models.generate_content.call_count, 2)

    def test_models_to_try_deduplicates_identical_primary_and_fallback(self) -> None:
        provider = GeminiProvider(
            api_key="k",
            model="gemini-2.5-flash",
            fallback_model="gemini-2.5-flash",
        )
        self.assertEqual(provider._models_to_try(), ("gemini-2.5-flash",))

    def test_verify_api_reports_all_model_failures(self) -> None:
        provider = self._provider()
        client = Mock()
        client.models.generate_content.side_effect = [
            RuntimeError("primary down"),
            RuntimeError("fallback down"),
        ]

        with patch.object(GeminiProvider, "_client", return_value=client):
            with self.assertRaises(RuntimeError) as ctx:
                provider.verify_api()

        message = str(ctx.exception)
        self.assertIn("primary down", message)
        self.assertIn("fallback down", message)


class AnthropicProviderTests(unittest.TestCase):
    def _provider(self, api_key: str = "test-key") -> AnthropicProvider:
        return AnthropicProvider(api_key=api_key)

    def test_generate_json_returns_text_block(self) -> None:
        provider = self._provider()
        text_block = Mock(type="text", text='{"ok": true}')
        response = Mock(content=[text_block])
        client = Mock()
        client.messages.create.return_value = response

        with patch.object(AnthropicProvider, "_client", return_value=client):
            result = provider.generate_json(system_prompt="sys", user_msg="hi")

        self.assertEqual(result, '{"ok": true}')

    def test_generate_json_raises_llm_auth_error(self) -> None:
        provider = self._provider()
        request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
        response = httpx.Response(401, request=request)
        auth_error = anthropic.AuthenticationError("invalid key", response=response, body=None)
        client = Mock()
        client.messages.create.side_effect = auth_error

        with patch.object(AnthropicProvider, "_client", return_value=client):
            with self.assertRaises(LLMAuthError):
                provider.generate_json(system_prompt="sys", user_msg="hi")

    def test_generate_json_falls_back_on_not_found(self) -> None:
        provider = self._provider()
        request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
        response = httpx.Response(404, request=request)
        not_found = anthropic.NotFoundError("model not found", response=response, body=None)
        text_block = Mock(type="text", text='{"ok": true}')
        ok_response = Mock(content=[text_block])
        client = Mock()
        client.messages.create.side_effect = [not_found, ok_response]

        with patch.object(AnthropicProvider, "_client", return_value=client):
            result = provider.generate_json(system_prompt="sys", user_msg="hi")

        self.assertEqual(result, '{"ok": true}')
        self.assertEqual(client.messages.create.call_count, 2)

    def test_verify_api_rejects_missing_key(self) -> None:
        provider = self._provider(api_key="")
        with self.assertRaises(LLMAuthError):
            provider.verify_api()


class ProviderFactoryTests(unittest.TestCase):
    def test_get_provider_returns_gemini_when_configured(self) -> None:
        gemini_settings = replace(
            settings,
            classify_provider="gemini",
            google_api_key="key",
            gemini_model="gemini-2.5-flash",
            gemini_fallback_model="gemini-3.1-flash-lite",
        )
        provider = get_provider(gemini_settings)
        self.assertIsInstance(provider, GeminiProvider)
        self.assertEqual(provider.name, "gemini")
        self.assertEqual(provider.primary_model, "gemini-2.5-flash")

    def test_get_provider_returns_anthropic_when_configured(self) -> None:
        anthropic_settings = replace(
            settings, classify_provider="anthropic", anthropic_api_key="key"
        )
        provider = get_provider(anthropic_settings)
        self.assertIsInstance(provider, AnthropicProvider)
        self.assertEqual(provider.name, "anthropic")
        self.assertEqual(provider.primary_model, "claude-haiku-4-5")


if __name__ == "__main__":
    unittest.main()
