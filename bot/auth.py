"""Telegram authorization helpers."""

from __future__ import annotations

from telegram import Update

from bot.config import settings


def is_authorized(update: Update) -> bool:
    """Only the configured TELEGRAM_CHAT_ID may use commands."""
    allowed = settings.telegram_chat_id.strip()
    if not allowed:
        return True  # dev mode: no restriction if chat id unset

    chat = update.effective_chat
    if not chat:
        return False
    return str(chat.id) == allowed


def unauthorized_message(chat_id: int | str) -> str:
    return (
        "No autorizado. Este bot es de uso personal.\n"
        f"Tu chat_id es: {chat_id}\n"
        "Añádelo como TELEGRAM_CHAT_ID en .env si eres el propietario."
    )
