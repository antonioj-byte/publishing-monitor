"""Main entrypoint: APScheduler + Telegram bot."""

from __future__ import annotations

import asyncio
import logging
import sys

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from telegram.ext import Application, CommandHandler
from zoneinfo import ZoneInfo

from ai.classify import classify_pending
from bot.config import settings
from bot.telegram_handlers import informe_command, informe_hoy_command, start_command
from db.connection import init_schema
from ingest.runner import ingest_all
from reports.generator import build_report, record_informe, split_message

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


async def job_ingest() -> None:
    logger.info("Starting scheduled ingest")
    stats = await asyncio.to_thread(ingest_all)
    logger.info("Ingest done: %s", stats)


async def job_classify() -> None:
    logger.info("Starting scheduled classification")
    stats = await asyncio.to_thread(classify_pending, 30)
    logger.info("Classification done: %s", stats)


async def job_cierre() -> None:
    logger.info("Starting cierre (ingest + classify)")
    await job_ingest()
    await job_classify()


async def job_informe_automatico(app: Application) -> None:
    logger.info("Starting automatic report")
    await job_cierre()

    report = await asyncio.to_thread(build_report, "informe")
    chat_id = settings.telegram_chat_id
    if not chat_id:
        logger.error("TELEGRAM_CHAT_ID not set")
        return

    for chunk in split_message(report.text):
        await app.bot.send_message(
            chat_id=chat_id,
            text=chunk,
            disable_web_page_preview=True,
        )

    if report.article_ids:
        await asyncio.to_thread(record_informe, report.article_ids, "automatico")

    logger.info("Automatic report sent (%d articles)", len(report.article_ids))


def setup_scheduler(app: Application) -> AsyncIOScheduler:
    tz = ZoneInfo(settings.timezone)
    scheduler = AsyncIOScheduler(timezone=tz)

    # Ingest every 3 hours between 08:00 and 23:00
    for hour in (8, 11, 14, 17, 20, 23):
        scheduler.add_job(job_ingest, CronTrigger(hour=hour, minute=0, timezone=tz))

    # Cierre at 06:00
    scheduler.add_job(job_cierre, CronTrigger(hour=6, minute=0, timezone=tz))

    # Automatic report at 06:30
    scheduler.add_job(
        job_informe_automatico,
        CronTrigger(hour=6, minute=30, timezone=tz),
        args=[app],
    )

    # Classify after each ingest window (offset 15 min)
    for hour in (8, 11, 14, 17, 20, 23):
        scheduler.add_job(job_classify, CronTrigger(hour=hour, minute=15, timezone=tz))

    return scheduler


def validate_settings() -> None:
    missing = []
    if not settings.telegram_bot_token:
        missing.append("TELEGRAM_BOT_TOKEN")
    if not settings.telegram_chat_id:
        missing.append("TELEGRAM_CHAT_ID")
    if missing:
        raise RuntimeError(
            "Faltan variables en .env: " + ", ".join(missing) + "\n"
            "1. Crea bot con @BotFather → /newbot\n"
            "2. Envía /start al bot\n"
            "3. python3 scripts/get_telegram_chat_id.py"
        )


def build_application() -> Application:
    validate_settings()

    app = (
        Application.builder()
        .token(settings.telegram_bot_token)
        .build()
    )
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("informe", informe_command))
    app.add_handler(CommandHandler("informe_hoy", informe_hoy_command))
    return app


async def main_async() -> None:
    init_schema()
    app = build_application()
    scheduler = setup_scheduler(app)
    scheduler.start()

    logger.info("Bot starting (timezone=%s, chat_id=%s)", settings.timezone, settings.telegram_chat_id)
    async with app:
        await app.start()
        await app.updater.start_polling(drop_pending_updates=True)
        try:
            while True:
                await asyncio.sleep(3600)
        finally:
            scheduler.shutdown(wait=False)
            await app.updater.stop()
            await app.stop()


def main() -> None:
    try:
        asyncio.run(main_async())
    except KeyboardInterrupt:
        logger.info("Shutting down")
        sys.exit(0)


if __name__ == "__main__":
    main()
