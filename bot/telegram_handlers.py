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
from bot.report_parser import parse_command_args, parse_free_text, parse_tag_command_args
from db.models import ReportFilter
from reports.generator import mark_articles_sent, record_informe, split_message
from reports.pipeline import build_editorial_report
from reports.paises import list_available_locations
from reports.session import load_session
from reports.tags import list_available_tags

logger = logging.getLogger(__name__)

_MORE_TEXT = re.compile(
    r"^(?:/informe_mas|informe\s+mas|informe\s+más|más\s+informaci[oó]n|"
    r"mas\s+informaci[oó]n|continuar|sigue|siguiente)\s*$",
    re.IGNORECASE,
)


def _filter_from_parsed(parsed) -> ReportFilter:
    return ReportFilter(
        days=parsed.days,
        pais=parsed.pais,
        region=parsed.region,
        location_label=parsed.location_label,
        tags=parsed.tags or None,
        tag_labels=parsed.tag_labels or None,
    )


def _filter_label(report_filter: ReportFilter | None) -> str:
    if not report_filter:
        return ""
    parts: list[str] = []
    if report_filter.location_label:
        parts.append(report_filter.location_label)
    if report_filter.tag_labels:
        parts.append(", ".join(report_filter.tag_labels))
    if report_filter.days:
        parts.append(f"{report_filter.days} días")
    return f" ({'; '.join(parts)})" if parts else ""


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
        "/informe <días> <país|tag> — ej. /informe 7 alemania · /informe 7 ficcion\n"
        "/tag <tag> <días> [<país>] — ej. /tag poesia 7 · /tag ferias_premios 14 españa\n"
        "/informe_mas — continuar el informe anterior\n"
        "/paises — países y regiones\n"
        "/tags — categorías editoriales\n"
        "/reclasificar — reclasificar todos los artículos (tags + resúmenes)\n\n"
        "Los informes tienen un máximo de ~2.500 palabras.\n"
        "Si hay más contenido, usa /informe_mas.\n\n"
        "También en texto libre:\n"
        "«informe últimos 7 días ficción en alemania»"
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


_RECLASSIFY_RUNNING = False


async def reclasificar_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    global _RECLASSIFY_RUNNING
    if not update.message:
        return
    if not is_authorized(update):
        await update.message.reply_text(
            unauthorized_message(update.effective_chat.id if update.effective_chat else "?")
        )
        return
    if _RECLASSIFY_RUNNING:
        await update.message.reply_text(
            "Ya hay una reclasificación en curso. Espera a que termine."
        )
        return

    from bot.reclassify_service import run_reclassify_all

    _RECLASSIFY_RUNNING = True
    await update.message.reply_text(
        "Reclasificación iniciada (todos los artículos, con tags).\n"
        "Puede tardar 1-2 horas. Te aviso cuando termine.\n"
        "El bot sigue respondiendo a /ping mientras tanto."
    )

    async def _job() -> None:
        global _RECLASSIFY_RUNNING
        try:
            stats = await asyncio.to_thread(
                run_reclassify_all,
                batch_size=20,
                delay=0.25,
                reset=True,
            )
            text = (
                f"Reclasificación terminada.\n"
                f"Total: {stats['total']}\n"
                f"Clasificados: {stats['classified']}\n"
                f"Fallidos: {stats['failed']}\n"
                f"Lotes: {stats['batches']}"
            )
        except Exception as exc:
            logger.exception("Reclassification failed")
            text = f"Error en reclasificación: {exc}"
        finally:
            _RECLASSIFY_RUNNING = False
        if update.message:
            await update.message.reply_text(text)

    asyncio.create_task(_job())


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


async def tags_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message:
        return
    if not is_authorized(update):
        await update.message.reply_text(
            unauthorized_message(update.effective_chat.id if update.effective_chat else "?")
        )
        return
    for chunk in split_message(list_available_tags()):
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
        report_filter = _filter_from_parsed(parsed)
        await _send_report(update, mode="informe_pais", record=False, report_filter=report_filter)
    else:
        await _send_report(update, mode="informe", record=True)


async def tag_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    args = context.args or []
    try:
        parsed = parse_tag_command_args(args)
    except ValueError as exc:
        if update.message:
            await update.message.reply_text(str(exc))
        return
    report_filter = _filter_from_parsed(parsed)
    await _send_report(update, mode="informe_pais", record=False, report_filter=report_filter)


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

    report_filter = _filter_from_parsed(parsed)
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
            "Genera uno con /informe, /tag o /informe 7 alemania."
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
    await update.message.reply_text(
        f"Clasificando y generando informe{_filter_label(report_filter)}…"
    )

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
