"""Telegram bot public profile (description / about)."""

from __future__ import annotations

import logging

from telegram import Bot

logger = logging.getLogger(__name__)

BOT_DESCRIPTION = (
    "Informes editoriales sobre libros, literatura e industria editorial. "
    "Comandos: /informe · /estado · /muestra · /reclasificar"
)

BOT_SHORT_DESCRIPTION = "Informes editoriales de libros y publishing"


async def sync_bot_profile(bot: Bot) -> None:
    """Overwrite bot About text on startup (recovers from profile spam/hijacks)."""
    try:
        await bot.set_my_description(BOT_DESCRIPTION)
        await bot.set_my_short_description(BOT_SHORT_DESCRIPTION)
        logger.info("Perfil público del bot actualizado (descripción + about)")
    except Exception:
        logger.exception("No se pudo actualizar el perfil público del bot")
