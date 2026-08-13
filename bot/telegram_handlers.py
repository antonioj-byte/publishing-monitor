"""Telegram command handlers."""

from __future__ import annotations

import logging

from telegram import Update
from telegram.ext import ContextTypes

from reports.generator import build_report, record_informe, split_message

logger = logging.getLogger(__name__)


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "Bot editorial activo.\n\n"
        "Comandos:\n"
        "/informe — informe desde el último cierre (o 24h)\n"
        "/informe_hoy — solo lo recopilado hoy"
    )


async def informe_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _send_report(update, mode="informe", record=True)


async def informe_hoy_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _send_report(update, mode="informe_hoy", record=False)


async def _send_report(update: Update, mode: str, record: bool) -> None:
    if not update.message:
        return

    await update.message.reply_text("Generando informe…")

    try:
        report = build_report(mode=mode)
        chunks = split_message(report.text)

        for chunk in chunks:
            await update.message.reply_text(chunk, disable_web_page_preview=True)

        if record and report.article_ids:
            record_informe(report.article_ids, tipo="manual")

        if not report.article_ids:
            logger.info("Empty report for mode=%s", mode)
    except Exception as exc:
        logger.exception("Report generation failed")
        await update.message.reply_text(f"Error al generar el informe: {exc}")
