"""Telegram command handlers."""

from __future__ import annotations

import asyncio
import logging
import re
from functools import partial

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from bot.auth import is_authorized, unauthorized_message
from bot.report_parser import parse_command_args, parse_free_text
from db.models import ReportFilter
from reports.generator import mark_articles_sent, record_informe, split_message
from reports.pipeline import build_editorial_report
from reports.paises import list_available_locations
from reports.session import load_session

logger = logging.getLogger(__name__)

_MORE_TEXT = re.compile(
    r"^(?:/informe_mas|informe\s+mas|informe\s+más|más\s+informaci[oó]n|"
    r"mas\s+informaci[oó]n|continuar|sigue|siguiente)\s*$",
    re.IGNORECASE,
)


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
        "/ping — comprobar latencia\n"
        "/informe — informe desde el último cierre (o 24h)\n"
        "/informe_hoy — publicados hoy en web (fecha de publicación)\n"
        "/informe <días> <país> — ej. /informe 7 alemania\n"
        "/informe_mas — continuar el informe anterior\n"
        "/paises — países y regiones disponibles\n\n"
        "Los informes tienen un máximo de ~2.500 palabras.\n"
        "Si hay más contenido, usa /informe_mas.\n\n"
        "También en texto libre:\n"
        "«informe últimos 7 días en alemania»"
    )


async def ping_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message:
        return
    if not is_authorized(update):
        await update.message.reply_text(
            unauthorized_message(update.effective_chat.id if update.effective_chat else "?")
        )
        return
    await update.message.reply_text("pong — bot operativo")


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await start_command(update, context)


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


async def informe_mas_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _send_continuation(update)


async def free_text_report(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.message.text:
        return
    if not is_authorized(update):
        return

    text = update.message.text.strip()
    if _MORE_TEXT.match(text):
        await _send_continuation(update)
        return

    try:
        parsed = parse_free_text(text)
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


async def _reply_report_chunk(message, chunk: str) -> None:
    await message.reply_text(
        chunk,
        parse_mode=ParseMode.HTML,
        disable_web_page_preview=True,
    )


async def _send_continuation(update: Update) -> None:
    if not update.message or not update.effective_chat:
        return
    if not is_authorized(update):
        await update.message.reply_text(
            unauthorized_message(str(update.effective_chat.id))
        )
        return

    chat_id = str(update.effective_chat.id)
    session = load_session(chat_id)
    if not session or session.cursor >= len(session.article_ids):
        await update.message.reply_text(
            "No hay un informe anterior pendiente de continuar.\n"
            "Genera uno con /informe o /informe 7 alemania."
        )
        return

    await update.message.reply_text("Generando continuación del informe…")
    try:
        report = await asyncio.to_thread(
            partial(
                build_editorial_report,
                continuation=session,
                chat_id=chat_id,
            )
        )
        for chunk in split_message(report.text):
            await _reply_report_chunk(update.message, chunk)
        if session.mode == "informe" and report.article_ids:
            await asyncio.to_thread(mark_articles_sent, report.article_ids)
            if not report.has_more:
                await asyncio.to_thread(
                    record_informe,
                    session.article_ids,
                    "manual",
                )
                logger.info("Report continuation complete for chat=%s", chat_id)
    except Exception as exc:
        logger.exception("Report continuation failed")
        await update.message.reply_text(f"Error al generar la continuación: {exc}")


async def _send_report(
    update: Update,
    mode: str,
    record: bool,
    report_filter: ReportFilter | None = None,
) -> None:
    if not update.message or not update.effective_chat:
        return

    if not is_authorized(update):
        await update.message.reply_text(
            unauthorized_message(str(update.effective_chat.id))
        )
        return

    chat_id = str(update.effective_chat.id)
    label = ""
    if report_filter and report_filter.location_label:
        label = f" ({report_filter.location_label}, {report_filter.days} días)"
    await update.message.reply_text(f"Clasificando y generando informe{label}…")

    try:
        report = await asyncio.to_thread(
            partial(
                build_editorial_report,
                mode=mode,
                report_filter=report_filter,
                chat_id=chat_id,
            )
        )
        chunks = split_message(report.text)

        for chunk in chunks:
            await _reply_report_chunk(update.message, chunk)

        if record and report.article_ids:
            if report.has_more:
                await asyncio.to_thread(mark_articles_sent, report.article_ids)
            else:
                await asyncio.to_thread(
                    record_informe,
                    report.article_ids,
                    "manual",
                )

        if not report.article_ids:
            logger.info("Empty report for mode=%s filter=%s", mode, report_filter)
    except Exception as exc:
        logger.exception("Report generation failed")
        await update.message.reply_text(f"Error al generar el informe: {exc}")
