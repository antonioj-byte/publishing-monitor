"""Telegram command handlers."""

from __future__ import annotations

import logging

from telegram import Update
from telegram.ext import ContextTypes

from bot.auth import is_authorized, unauthorized_message
from bot.report_parser import parse_command_args, parse_free_text
from db.models import ReportFilter
from reports.generator import build_report, record_informe, split_message
from reports.paises import list_available_locations

logger = logging.getLogger(__name__)


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message:
        return
    if not is_authorized(update):
        await update.message.reply_text(
            unauthorized_message(update.effective_chat.id if update.effective_chat else "?")
        )
        return
    await update.message.reply_text(
        "Bot editorial activo.\n\n"
        "Comandos:\n"
        "/informe — informe desde el último cierre (o 24h)\n"
        "/informe_hoy — solo lo recopilado hoy\n"
        "/informe <días> <país> — ej. /informe 7 alemania\n"
        "/paises — países y regiones disponibles\n\n"
        "También puedes escribir en texto libre:\n"
        "«informe últimos 7 días en alemania»"
    )


async def paises_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message:
        return
    if not is_authorized(update):
        await update.message.reply_text(
            unauthorized_message(update.effective_chat.id if update.effective_chat else "?")
        )
        return
    for chunk in split_message(list_available_locations()):
        await update.message.reply_text(chunk, disable_web_page_preview=True)


async def informe_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    args = context.args or []
    try:
        parsed = parse_command_args(args)
    except ValueError as exc:
        if update.message:
            await update.message.reply_text(str(exc))
        return

    if parsed:
        report_filter = ReportFilter(
            days=parsed.days,
            pais=parsed.pais,
            region=parsed.region,
            location_label=parsed.location_label,
        )
        await _send_report(update, mode="informe_pais", record=False, report_filter=report_filter)
    else:
        await _send_report(update, mode="informe", record=True)


async def informe_hoy_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _send_report(update, mode="informe_hoy", record=False)


async def free_text_report(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.message.text:
        return
    if not is_authorized(update):
        return

    try:
        parsed = parse_free_text(update.message.text)
    except ValueError as exc:
        await update.message.reply_text(str(exc))
        return

    if not parsed:
        return

    report_filter = ReportFilter(
        days=parsed.days,
        pais=parsed.pais,
        region=parsed.region,
        location_label=parsed.location_label,
    )
    await _send_report(update, mode="informe_pais", record=False, report_filter=report_filter)


async def _send_report(
    update: Update,
    mode: str,
    record: bool,
    report_filter: ReportFilter | None = None,
) -> None:
    if not update.message:
        return

    if not is_authorized(update):
        await update.message.reply_text(
            unauthorized_message(update.effective_chat.id if update.effective_chat else "?")
        )
        return

    label = ""
    if report_filter and report_filter.location_label:
        label = f" ({report_filter.location_label}, {report_filter.days} días)"
    await update.message.reply_text(f"Generando informe{label}…")

    try:
        report = build_report(mode=mode, report_filter=report_filter)
        chunks = split_message(report.text)

        for chunk in chunks:
            await update.message.reply_text(chunk, disable_web_page_preview=True)

        if record and report.article_ids:
            record_informe(report.article_ids, tipo="manual")

        if not report.article_ids:
            logger.info("Empty report for mode=%s filter=%s", mode, report_filter)
    except Exception as exc:
        logger.exception("Report generation failed")
        await update.message.reply_text(f"Error al generar el informe: {exc}")
