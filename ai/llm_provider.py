"""Unified LLM provider abstraction for article classification.

Encapsulates all vendor-specific SDK calls (Gemini, Anthropic) behind a
common interface so callers (ai/classify.py, bot handlers, diagnostic
scripts) never import `anthropic` or `google.genai` directly.
"""

from __future__ import annotations

import logging
from typing import Protocol

logger = logging.getLogger(__name__)

_GEMINI_CLIENT = None
_GEMINI_CLIENT_KEY: str | None = None


class LLMAuthError(RuntimeError):
    """Invalid/missing API key or credentials rejected by the provider."""


class LLMQuotaError(RuntimeError):
    """API quota, billing, or credit balance exhausted."""


class LLMProvider(Protocol):
    name: str
    label: str
    key_env_name: str
    setup_url: str

    @property
    def primary_model(self) -> str: ...

    def generate_json(self, *, system_prompt: str, user_msg: str) -> str:
        """Return raw JSON text from the model, trying fallback models on failure.

        Raises LLMAuthError / LLMQuotaError for fatal credential/billing issues,
        or RuntimeError if every model failed for other reasons.
        """
        ...

    def verify_api(self) -> None:
        """Raise RuntimeError (or a subclass) if the provider cannot classify."""
        ...


class GeminiProvider:
    name = "gemini"
    label = "Gemini API"
    key_env_name = "GOOGLE_API_KEY"
    setup_url = "https://aistudio.google.com/apikey"

    def __init__(self, *, api_key: str, model: str, fallback_model: str) -> None:
        self._api_key = api_key
        self._model = model
        self._fallback_model = fallback_model

    def _models_to_try(self) -> tuple[str, ...]:
        models: list[str] = []
        for model in (self._model, self._fallback_model):
            if model and model not in models:
                models.append(model)
        return tuple(models)

    @property
    def primary_model(self) -> str:
        return self._model

    def _client(self):
        global _GEMINI_CLIENT, _GEMINI_CLIENT_KEY
        from google import genai

        if _GEMINI_CLIENT is not None and _GEMINI_CLIENT_KEY == self._api_key:
            return _GEMINI_CLIENT

        _GEMINI_CLIENT = genai.Client(api_key=self._api_key)
        _GEMINI_CLIENT_KEY = self._api_key
        return _GEMINI_CLIENT

    def _classify_error(self, exc: Exception) -> Exception | None:
        err = str(exc).lower()
        if "api key" in err or "permission" in err or "401" in err:
            return LLMAuthError(
                f"{self.key_env_name} inválida. Crea una nueva en {self.setup_url}"
            )
        if "quota" in err or "billing" in err or "resource_exhausted" in err:
            return LLMQuotaError(
                "Cuota de Gemini agotada. Revisa billing en Google AI Studio."
            )
        return None

    def generate_json(self, *, system_prompt: str, user_msg: str) -> str:
        from google.genai import types

        client = self._client()
        errors: list[str] = []
        for model in self._models_to_try():
            try:
                response = client.models.generate_content(
                    model=model,
                    contents=user_msg,
                    config=types.GenerateContentConfig(
                        system_instruction=system_prompt,
                        max_output_tokens=600,
                        temperature=0.2,
                        response_mime_type="application/json",
                    ),
                )
                text = (response.text or "").strip()
                if not text:
                    raise RuntimeError("Gemini devolvió respuesta vacía")
                return text
            except Exception as exc:
                mapped = self._classify_error(exc)
                if mapped is not None:
                    raise mapped from exc
                errors.append(f"{model}: {exc}")
                logger.warning("Gemini model %s failed: %s", model, exc)
                continue
        raise RuntimeError(f"Gemini classification failed: {'; '.join(errors)}")

    def verify_api(self) -> None:
        from google.genai import types

        if not self._api_key:
            raise LLMAuthError(
                f"{self.key_env_name} no configurada. Obtén una en "
                f"{self.setup_url} y añádela en Railway → Variables."
            )

        client = self._client()
        errors: list[str] = []
        for model in self._models_to_try():
            try:
                client.models.generate_content(
                    model=model,
                    contents="Responde solo: ok",
                    config=types.GenerateContentConfig(max_output_tokens=10),
                )
                logger.info("Gemini API OK (modelo %s)", model)
                return
            except Exception as exc:
                mapped = self._classify_error(exc)
                if mapped is not None:
                    raise mapped from exc
                errors.append(f"{model}: {exc}")
                logger.warning("Gemini model %s unavailable: %s", model, exc)
                continue

        raise RuntimeError(f"Ningún modelo Gemini disponible: {'; '.join(errors)}")


class AnthropicProvider:
    name = "anthropic"
    label = "Anthropic API"
    key_env_name = "ANTHROPIC_API_KEY"
    setup_url = "https://console.anthropic.com"

    MODEL = "claude-haiku-4-5"
    FALLBACK_MODEL = "claude-sonnet-5"

    def __init__(self, *, api_key: str) -> None:
        self._api_key = api_key

    @property
    def primary_model(self) -> str:
        return self.MODEL

    def _client(self):
        import anthropic

        return anthropic.Anthropic(api_key=self._api_key)

    def _classify_error(self, exc: Exception) -> Exception | None:
        import anthropic

        if isinstance(exc, anthropic.AuthenticationError):
            return LLMAuthError(
                f"{self.key_env_name} inválida. Renueva la clave en console.anthropic.com."
            )
        if isinstance(exc, anthropic.BadRequestError) and "credit balance" in str(exc).lower():
            return LLMQuotaError(
                "Créditos de Anthropic agotados. Recarga en "
                "console.anthropic.com → Plans & Billing."
            )
        return None

    def generate_json(self, *, system_prompt: str, user_msg: str) -> str:
        import anthropic

        client = self._client()
        last_error: Exception | None = None
        for model in (self.MODEL, self.FALLBACK_MODEL):
            try:
                response = client.messages.create(
                    model=model,
                    max_tokens=600,
                    system=system_prompt,
                    messages=[{"role": "user", "content": user_msg}],
                )
                block = next(b for b in response.content if b.type == "text")
                return block.text
            except anthropic.NotFoundError as exc:
                last_error = exc
                continue
            except anthropic.APIError as exc:
                mapped = self._classify_error(exc)
                if mapped is not None:
                    raise mapped from exc
                last_error = exc
                if model == self.FALLBACK_MODEL:
                    raise RuntimeError(f"Anthropic API error: {exc}") from exc
                continue
        raise RuntimeError(f"Anthropic classification failed: {last_error}")

    def verify_api(self) -> None:
        import anthropic

        if not self._api_key:
            raise LLMAuthError(
                f"{self.key_env_name} no configurada. Añádela en Railway → Variables."
            )

        client = self._client()
        last_error: Exception | None = None
        for model in (self.MODEL, self.FALLBACK_MODEL):
            try:
                client.messages.create(
                    model=model,
                    max_tokens=20,
                    messages=[{"role": "user", "content": "Responde solo: ok"}],
                )
                return
            except anthropic.NotFoundError as exc:
                last_error = exc
                continue
            except anthropic.APIError as exc:
                mapped = self._classify_error(exc)
                if mapped is not None:
                    raise mapped from exc
                last_error = exc
                if model == self.FALLBACK_MODEL:
                    raise RuntimeError(f"Anthropic API error: {exc}") from exc
                continue

        raise RuntimeError(f"Ningún modelo Anthropic disponible: {last_error}")


def get_provider(settings) -> LLMProvider:
    """Build the LLM provider configured in `settings.classify_provider`."""
    if settings.classify_provider == "gemini":
        return GeminiProvider(
            api_key=settings.google_api_key,
            model=settings.gemini_model,
            fallback_model=settings.gemini_fallback_model,
        )
    return AnthropicProvider(api_key=settings.anthropic_api_key)
