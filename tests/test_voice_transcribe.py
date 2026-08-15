"""Tests for voice transcription helper."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from bot.voice_transcribe import VoiceTranscriptionError, transcribe_voice_bytes


class VoiceTranscribeTests(unittest.TestCase):
    def test_requires_google_api_key(self) -> None:
        with patch("bot.voice_transcribe.settings") as settings:
            settings.google_api_key = ""
            settings.gemini_model = "gemini-2.5-flash"
            with self.assertRaises(VoiceTranscriptionError):
                transcribe_voice_bytes(b"fake")

    def test_returns_transcript(self) -> None:
        response = MagicMock()
        response.text = "informe de ficción de la semana"
        client = MagicMock()
        client.models.generate_content.return_value = response

        with (
            patch("bot.voice_transcribe.settings") as settings,
            patch("google.genai.Client", return_value=client),
        ):
            settings.google_api_key = "test-key"
            settings.gemini_model = "gemini-2.5-flash"
            text = transcribe_voice_bytes(b"audio-bytes")

        self.assertEqual(text, "informe de ficción de la semana")


if __name__ == "__main__":
    unittest.main()
