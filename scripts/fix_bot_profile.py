#!/usr/bin/env python3
"""Restore Telegram bot public profile (About / description)."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bot.config import settings
from bot.profile import BOT_DESCRIPTION, BOT_SHORT_DESCRIPTION, sync_bot_profile
from telegram import Bot


async def main() -> None:
    token = settings.telegram_bot_token.strip()
    if not token:
        print("TELEGRAM_BOT_TOKEN no configurado")
        sys.exit(1)
    bot = Bot(token)
    me = await bot.get_me()
    print(f"Bot: @{me.username}")
    await sync_bot_profile(bot)
    print("Descripción:", BOT_DESCRIPTION)
    print("About corto:", BOT_SHORT_DESCRIPTION)
    print("Listo.")


if __name__ == "__main__":
    asyncio.run(main())
