"""Google Gemini classification client."""

from __future__ import annotations

import logging

from google import genai
from google.genai import types

from bot.config import settings

logger = logging.getLogger(__name__)


def _client() -> genai.Client:
    return genai.Client(api_key=settings.google_api_key)


def generate_json(*, system_prompt: str, user_msg: str, model: str) -> str:
    response = _client().models.generate_content(
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


def verify_gemini_api() -> None:
    if not settings.google_api_key:
        raise RuntimeError(
            "GOOGLE_API_KEY no configurada. Obtén una en "
            "https://aistudio.google.com/apikey y añádela en Railway → Variables."
        )

    last_error: Exception | None = None
    for model in (settings.gemini_model, settings.gemini_fallback_model):
        try:
            _client().models.generate_content(
                model=model,
                contents="Responde solo: ok",
                config=types.GenerateContentConfig(max_output_tokens=10),
            )
            logger.info("Gemini API OK (modelo %s)", model)
            return
        except Exception as exc:
            last_error = exc
            err = str(exc).lower()
            if "api key" in err or "permission" in err or "401" in err:
                raise RuntimeError(
                    "GOOGLE_API_KEY inválida. Crea una nueva en "
                    "https://aistudio.google.com/apikey"
                ) from exc
            if "quota" in err or "billing" in err or "resource_exhausted" in err:
                raise RuntimeError(
                    "Cuota de Gemini agotada. Revisa billing en Google AI Studio."
                ) from exc
            logger.warning("Gemini model %s unavailable: %s", model, exc)
            continue

    raise RuntimeError(f"Ningún modelo Gemini disponible: {last_error}")
