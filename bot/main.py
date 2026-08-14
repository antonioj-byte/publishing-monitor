"""Main entrypoint: APScheduler + Telegram bot."""

from __future__ import annotations

import asyncio
import logging
import sys
import time

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from telegram.error import Conflict
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters
from zoneinfo import ZoneInfo

from ai.classify import classify_pending
from bot.config import settings
from bot.heartbeat import write_heartbeat
from bot.telegram_handlers import (
    free_text_report,
    help_command,
    informe_command,
    informe_hoy_command,
    informe_mas_command,
    paises_command,
    ping_command,
    start_command,
)
from db.connection import init_schema
from ingest.runner import ingest_all
from reports.generator import mark_articles_sent, record_informe, split_message
from reports.pipeline import build_editorial_report
from reports.prioritize import _compute_embeddings
from reports.session import load_session

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

_JOB_DEFAULTS = {
    "max_instances": 1,
    "coalesce": True,
    "misfire_grace_time": 300,
}


async def job_ingest() -> None:
    logger.info("Starting scheduled ingest")
    stats = await asyncio.to_thread(ingest_all)
    logger.info("Ingest done: %s", stats)


async def job_classify() -> None:
    """Classify one batch so scheduled work does not monopolize the process."""
    logger.info("Starting scheduled classification batch")
    stats = await asyncio.to_thread(classify_pending, limit=30)
    logger.info("Classification batch done: %s", stats)


async def job_cierre() -> None:
    logger.info("Starting cierre (ingest + classify batch)")
    await job_ingest()
    await job_classify()


async def job_informe_automatico(app: Application) -> None:
    logger.info("Starting automatic report")
    await job_cierre()

    chat_id = settings.telegram_chat_id
    if not chat_id:
        logger.error("TELEGRAM_CHAT_ID not set")
        return

    report = await asyncio.to_thread(
        build_editorial_report,
        "informe",
        chat_id=chat_id,
        classify_before_report=False,
    )
    session = load_session(chat_id)
    sent_count = 0

    while True:
        for chunk in split_message(report.text):
            await app.bot.send_message(
                chat_id=chat_id,
                text=chunk,
                disable_web_page_preview=True,
            )

        if report.article_ids:
            await asyncio.to_thread(mark_articles_sent, report.article_ids)
            sent_count += len(report.article_ids)

        if not report.has_more:
            complete_ids = session.article_ids if session else report.article_ids
            if complete_ids:
                await asyncio.to_thread(
                    record_informe,
                    complete_ids,
                    "automatico",
                )
            break

        session = load_session(chat_id)
        if not session:
            logger.error("Automatic report continuation session missing")
            break
        report = await asyncio.to_thread(
            build_editorial_report,
            continuation=session,
            chat_id=chat_id,
        )

    logger.info("Automatic report sent (%d articles)", sent_count)


async def _prewarm_embeddings_background() -> None:
    try:
        await asyncio.to_thread(
            _compute_embeddings,
            ["editorial news warmup"],
        )
        logger.info("Embedding model prewarmed")
    except Exception:
        logger.exception("Embedding prewarm failed")


async def _heartbeat_loop() -> None:
    while True:
        write_heartbeat(status="running")
        await asyncio.sleep(60)


async def _error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    error = context.error
    if isinstance(error, Conflict):
        logger.error(
            "Otra instancia del bot está usando el mismo token (409 Conflict). "
            "Saliendo para que launchd reinicie una sola instancia."
        )
        write_heartbeat(status="conflict", detail=str(error))
        sys.exit(1)
    logger.exception("Unhandled handler error: %s", error)


def setup_scheduler(app: Application) -> AsyncIOScheduler:
    tz = ZoneInfo(settings.timezone)
    scheduler = AsyncIOScheduler(timezone=tz, job_defaults=_JOB_DEFAULTS)

    for hour in (8, 11, 14, 17, 20, 23):
        scheduler.add_job(job_ingest, CronTrigger(hour=hour, minute=0, timezone=tz))

    scheduler.add_job(job_cierre, CronTrigger(hour=6, minute=0, timezone=tz))

    scheduler.add_job(
        job_informe_automatico,
        CronTrigger(hour=6, minute=30, timezone=tz),
        args=[app],
    )

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
        .concurrent_updates(True)
        .build()
    )
    app.add_error_handler(_error_handler)
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("ping", ping_command))
    app.add_handler(CommandHandler("informe", informe_command))
    app.add_handler(CommandHandler("informe_hoy", informe_hoy_command))
    app.add_handler(CommandHandler("informe_mas", informe_mas_command))
    app.add_handler(CommandHandler("paises", paises_command))
    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            free_text_report,
        )
    )
    return app


async def main_async() -> None:
    started = time.monotonic()
    init_schema()
    app = build_application()

    logger.info("Bot starting (timezone=%s, chat_id=%s)", settings.timezone, settings.telegram_chat_id)
    async with app:
        me = await app.bot.get_me()
        logger.info("Telegram conectado como @%s", me.username)

        webhook = await app.bot.get_webhook_info()
        if webhook.url:
            logger.warning("Webhook activo detectado (%s) — eliminando para usar polling", webhook.url)
        await app.bot.delete_webhook(drop_pending_updates=False)

        await app.start()
        await app.updater.start_polling(
            drop_pending_updates=False,
            poll_interval=0.5,
        )
        write_heartbeat(status="running", detail=f"@{me.username}")
        logger.info(
            "Polling activo — bot listo en %.1fs",
            time.monotonic() - started,
        )

        scheduler = setup_scheduler(app)
        scheduler.start()
        asyncio.create_task(_prewarm_embeddings_background())
        asyncio.create_task(_heartbeat_loop())

        try:
            while True:
                await asyncio.sleep(3600)
        finally:
            write_heartbeat(status="stopping")
            scheduler.shutdown(wait=False)
            await app.updater.stop()
            await app.stop()


def main() -> None:
    try:
        asyncio.run(main_async())
    except KeyboardInterrupt:
        logger.info("Shutting down")
        write_heartbeat(status="stopped")
        sys.exit(0)
    except Exception:
        logger.exception("Bot crashed")
        write_heartbeat(status="crashed")
        sys.exit(1)


if __name__ == "__main__":
    main()
