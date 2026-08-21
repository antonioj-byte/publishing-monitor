"""Transcribe Telegram voice notes for informal report requests."""

from __future__ import annotations

import logging

from ai.usage_tracking import record_llm_call
from bot.config import settings

logger = logging.getLogger(__name__)


class VoiceTranscriptionError(RuntimeError):
    """Voice could not be transcribed."""


def transcribe_voice_bytes(audio_bytes: bytes, *, mime_type: str = "audio/ogg") -> str:
    """Transcribe OGG/Opus voice from Telegram using Gemini."""
    api_key = settings.google_api_key.strip()
    if not api_key:
        raise VoiceTranscriptionError(
            "Para informes por voz necesitas GOOGLE_API_KEY en Railway (Gemini transcribe el audio)."
        )

    from google import genai
    from google.genai import types

    client = genai.Client(api_key=api_key)
    model = settings.gemini_model or "gemini-2.5-flash"
    prompt = (
        "Transcribe este mensaje de voz al castellano. "
        "Devuelve solo la transcripción literal, sin comentarios ni puntuación extra."
    )

    try:
        response = client.models.generate_content(
            model=model,
            contents=[
                types.Part.from_bytes(data=audio_bytes, mime_type=mime_type),
                prompt,
            ],
            config=types.GenerateContentConfig(
                max_output_tokens=300,
                temperature=0.1,
            ),
        )
    except Exception as exc:
        logger.exception("Gemini voice transcription failed")
        raise VoiceTranscriptionError(f"No pude transcribir el audio: {exc}") from exc

    text = (response.text or "").strip()
    if not text:
        raise VoiceTranscriptionError("La transcripción salió vacía. ¿Se oía bien el audio?")
    record_llm_call(
        operation="voice",
        provider="gemini",
        model=model,
        response=response,
        output_text=text,
    )
    return text
