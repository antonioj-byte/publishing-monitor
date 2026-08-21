"""Telegram command handlers."""

from __future__ import annotations

import asyncio
import logging
import re
from datetime import datetime
from functools import partial
from io import BytesIO

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from bot.auth import is_authorized, unauthorized_message
from bot.config import settings
from bot.db_export import export_database_bytes
from bot.filters_info import list_available_filters
from reports.medios_lookup import list_available_medios
from bot.pipeline_status import (
    format_diagnostico_text,
    format_estado_text,
    format_muestra_text,
)
from bot.report_parser import parse_command_args
from bot.request_intent import UserRequest, informal_ack, parse_user_request
from bot.voice_transcribe import VoiceTranscriptionError, transcribe_voice_bytes
from bot.github_pr import format_latest_pr_line
from bot.reclassify_service import run_backfill_tags, run_reclassify_all
from bot.restart_service import detect_restart_method, restart_bot, restart_method_hint
from ai.classify import active_model, active_provider
from ai.llm_provider import get_provider
from ai.usage_tracking import format_gasto_text
from bot.version import BOT_VERSION
from db.models import ReportFilter
from reports.generator import (
    _fetch_articles,
    mark_articles_sent,
    record_informe,
    split_message,
)
from reports.markdown_export import build_markdown_report, markdown_filename
from reports.pipeline import build_editorial_report
from reports.session import load_session

logger = logging.getLogger(__name__)


async def _dispatch_user_request(
    update: Update,
    request: UserRequest,
    *,
    status_message: str | None = None,
) -> None:
    if request.kind == "unknown":
        if update.message:
            await update.message.reply_text(informal_ack(request))
        return
    if request.kind == "continuation":
        if status_message and update.message:
            await update.message.reply_text(status_message)
        await _send_continuation(update)
        return
    if request.kind == "hoy":
        await _send_report(
            update,
            mode="informe_hoy",
            record=False,
            status_message=status_message or informal_ack(request),
        )
        return
    if request.kind == "daily":
        await _send_report(
            update,
            mode="informe",
            record=True,
            status_message=status_message or informal_ack(request),
        )
        return
    if request.kind == "filtered" and request.filter:
        report_filter = _filter_from_parsed(request.filter)
        await _send_report(
            update,
            mode="informe_pais",
            record=False,
            report_filter=report_filter,
            status_message=status_message or informal_ack(request),
        )


async def _handle_natural_language(
    update: Update,
    text: str,
    *,
    heard_from_voice: bool = False,
) -> None:
    if not update.message:
        return
    if not is_authorized(update):
        return

    request = parse_user_request(text)
    if request.kind == "unknown":
        if heard_from_voice:
            await update.message.reply_text(
                f"He oído: «{text}»\n"
                "No lo he interpretado como informe. Prueba algo como "
                "«informe de ficción de la semana» o «qué hay hoy»."
            )
        return

    prefix = informal_ack(request)
    if heard_from_voice:
        prefix = f"He oído: «{text}»\n{prefix}"
    await _dispatch_user_request(update, request, status_message=prefix)


def _filter_from_parsed(parsed) -> ReportFilter:
    return ReportFilter(
        days=parsed.days,
        pais=parsed.pais,
        region=parsed.region,
        location_label=parsed.location_label,
        medio_nombre=parsed.medio_nombre,
        tags=parsed.tags or None,
        tag_labels=parsed.tag_labels or None,
    )


def _filter_label(report_filter: ReportFilter | None) -> str:
    if not report_filter:
        return ""
    parts: list[str] = []
    if report_filter.medio_nombre:
        parts.append(report_filter.medio_nombre)
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
        "/informe — informe diario (desde último cierre)\n"
        "/informe <filtros> — ej. /informe 7 ficcion · /informe alemania · /informe 7 les inrocks\n"
        "/informe_hoy — publicados hoy en web\n"
        "/informe_mas — continuar el informe anterior\n"
        "/informe_md — descargar informe en Markdown (.md)\n"
        "/descargar — Markdown del último informe generado\n"
        "/descargar_db — descargar la base de datos SQLite (.db)\n"
        "/estado — resumen de la base de datos\n"
        "/gasto — gasto API estimado del bot (/gasto 7 · /gasto 90)\n"
        "/muestra — últimos artículos clasificados (/muestra ruido)\n"
        "/diagnostico — por qué un informe sale vacío\n"
        "/tags — tags editoriales y países disponibles\n"
        "/medios — medios disponibles para filtrar informes\n"
        "/reclasificar — reclasificar artículos sin tags\n"
        "/reclasificar todo — reclasificar todos desde cero\n"
        "/reiniciar — reiniciar el bot\n\n"
        "Los informes tienen un máximo de ~2.500 palabras.\n"
        "Si hay más contenido, usa /informe_mas.\n\n"
        "También en texto libre o **nota de voz** (habla normal, sin comandos):\n"
        "«dame ficción de la semana» · «informe de hoy» · "
        "«qué hay de literatura local»"
    )


async def ping_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message:
        return
    if not is_authorized(update):
        await update.message.reply_text(
            unauthorized_message(update.effective_chat.id if update.effective_chat else "?")
        )
        return
    pr_line = await asyncio.to_thread(format_latest_pr_line)
    await update.message.reply_text(
        f"pong — bot operativo (v{BOT_VERSION})\n"
        f"{pr_line}\n"
        f"Clasificación: {active_provider()} ({active_model()})"
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await start_command(update, context)


async def estado_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message:
        return
    if not is_authorized(update):
        await update.message.reply_text(
            unauthorized_message(update.effective_chat.id if update.effective_chat else "?")
        )
        return
    try:
        text = await asyncio.to_thread(format_estado_text)
    except Exception as exc:
        logger.exception("estado failed")
        text = f"Error en /estado: {exc}"
    await update.message.reply_text(text)


async def gasto_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message:
        return
    if not is_authorized(update):
        await update.message.reply_text(
            unauthorized_message(update.effective_chat.id if update.effective_chat else "?")
        )
        return
    days = 30
    for arg in context.args or []:
        if arg.isdigit():
            days = max(1, min(365, int(arg)))
            break
    try:
        text = await asyncio.to_thread(format_gasto_text, days=days)
    except Exception as exc:
        logger.exception("gasto failed")
        text = f"Error en /gasto: {exc}"
    await update.message.reply_text(text, disable_web_page_preview=True)


async def diagnostico_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message:
        return
    if not is_authorized(update):
        await update.message.reply_text(
            unauthorized_message(update.effective_chat.id if update.effective_chat else "?")
        )
        return
    args = context.args or []
    report_filter = None
    if args:
        try:
            parsed = parse_command_args(args)
        except ValueError as exc:
            await update.message.reply_text(str(exc))
            return
        if parsed:
            report_filter = _filter_from_parsed(parsed)
    try:
        text = await asyncio.to_thread(format_diagnostico_text, report_filter)
    except Exception as exc:
        logger.exception("diagnostico failed")
        text = f"Error en /diagnostico: {exc}"
    await update.message.reply_text(text)


async def muestra_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message:
        return
    if not is_authorized(update):
        await update.message.reply_text(
            unauthorized_message(update.effective_chat.id if update.effective_chat else "?")
        )
        return
    args = [a.lower() for a in (context.args or [])]
    only_untagged = any(a in ("sin_tags", "sin-tags", "untagged") for a in args)
    only_noise = any(a in ("ruido", "noise", "fuera") for a in args)
    limit = 5
    for arg in args:
        if arg.isdigit():
            limit = int(arg)
            break
    try:
        text = await asyncio.to_thread(
            format_muestra_text,
            limit=limit,
            only_untagged=only_untagged,
            only_noise=only_noise,
        )
    except Exception as exc:
        logger.exception("muestra failed")
        text = f"Error en /muestra: {exc}"
    await update.message.reply_text(text)


_RECLASSIFY_RUNNING = False
_RESTART_RUNNING = False


def _classify_api_hint() -> str:
    provider = get_provider(settings)
    return f"Revisa {provider.key_env_name} y créditos en Railway ({provider.setup_url}) "


def _format_reclassify_result(stats: dict[str, int], *, full_reset: bool) -> str:
    if stats.get("queued", 0) == 0 and not full_reset:
        with_tags = stats.get("with_tags", 0)
        total = stats.get("total", 0)
        untagged = stats.get("untagged", 0)
        if untagged > 0:
            return (
                f"Hay {untagged} artículos sin tags pero no se pudieron encolar.\n"
                f"Con tags: {with_tags} de {total}."
            )
        return (
            f"Todos los artículos tienen tags ({with_tags} de {total})."
        )
    if stats.get("with_tags", 0) == 0 and stats.get("classified", 0) == 0:
        scope = "completa" if full_reset else "parcial"
        return (
            f"Reclasificación {scope} abortada.\n"
            f"En cola: {stats.get('queued', stats.get('total', 0))}\n"
            f"Con tags: {stats.get('with_tags', 0)}\n"
            f"Fallidos: {stats.get('failed', 0)}\n\n"
            f"{_classify_api_hint()}"
            "y vuelve a ejecutar /reclasificar."
        )
    if stats.get("with_tags", 0) == 0:
        return (
            f"Reclasificación terminada sin tags.\n"
            f"En cola: {stats.get('queued', stats.get('total', 0))}\n"
            f"Con tags: {stats.get('with_tags', 0)}\n"
            f"Fallidos: {stats.get('failed', 0)}\n\n"
            "La API no asignó tags. Revisa créditos y vuelve a intentarlo."
        )
    label = "completa" if full_reset else "parcial"
    lines = [
        f"Reclasificación {label} terminada.",
        f"Con tags: {stats['with_tags']}",
        f"Procesados: {stats['classified']}",
        f"Fallidos: {stats['failed']}",
        f"Lotes: {stats['batches']}",
    ]
    if full_reset:
        lines.insert(1, f"Total en BD: {stats.get('total', 0)}")
    else:
        lines.insert(1, f"En cola (sin tags): {stats.get('queued', 0)}")
    return "\n".join(lines)


async def _run_reclassify_job(
    update: Update,
    *,
    full_reset: bool,
    runner,
    start_message: str,
) -> None:
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

    await update.message.reply_text(start_message)
    _RECLASSIFY_RUNNING = True

    async def _job() -> None:
        global _RECLASSIFY_RUNNING
        try:
            stats = await asyncio.to_thread(runner)
            text = _format_reclassify_result(stats, full_reset=full_reset)
        except Exception as exc:
            logger.exception("reclasificar failed")
            text = f"Error en /reclasificar: {exc}"
        finally:
            _RECLASSIFY_RUNNING = False
        if update.message:
            await update.message.reply_text(text)

    asyncio.create_task(_job())


async def reiniciar_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    global _RESTART_RUNNING
    if not update.message:
        return
    if not is_authorized(update):
        await update.message.reply_text(
            unauthorized_message(update.effective_chat.id if update.effective_chat else "?")
        )
        return
    if _RESTART_RUNNING:
        await update.message.reply_text("Ya hay un reinicio en curso.")
        return

    method = detect_restart_method()
    await update.message.reply_text(
        "Reiniciando bot…\n"
        f"Método: {restart_method_hint(method)}.\n"
        "En ~10 s prueba /ping."
    )

    _RESTART_RUNNING = True

    async def _job() -> None:
        global _RESTART_RUNNING
        try:
            await restart_bot(context.application, delay_seconds=2.0)
        except Exception:
            logger.exception("Restart failed")
            _RESTART_RUNNING = False
            if update.message:
                await update.message.reply_text(
                    "No pude reiniciar automáticamente. "
                    "Arranca el bot manualmente con ./deploy/start-bot.sh"
                )

    asyncio.create_task(_job())


async def reclasificar_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    args = [a.lower() for a in (context.args or [])]
    full_reset = args and args[0] in ("todo", "all", "todos")
    if full_reset:
        await _run_reclassify_job(
            update,
            full_reset=True,
            runner=lambda: run_reclassify_all(batch_size=20, delay=0.25, reset=True),
            start_message=(
                "Reclasificación completa iniciada (todos los artículos).\n"
                "Puede tardar 1-2 horas. Te aviso cuando termine.\n"
                "El bot sigue respondiendo a /ping mientras tanto."
            ),
        )
    else:
        await _run_reclassify_job(
            update,
            full_reset=False,
            runner=lambda: run_backfill_tags(batch_size=20, delay=0.25),
            start_message=(
                "Reclasificación iniciada (artículos sin tags).\n"
                "Puede tardar 1-2 horas. Te aviso cuando termine.\n"
                "El bot sigue respondiendo a /ping mientras tanto."
            ),
        )


async def retag_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Alias silencioso de /reclasificar (compatibilidad)."""
    await reclasificar_command(update, context)


async def unknown_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message:
        return
    if not is_authorized(update):
        await update.message.reply_text(
            unauthorized_message(update.effective_chat.id if update.effective_chat else "?")
        )
        return
    cmd = update.message.text.split()[0] if update.message.text else "?"
    await update.message.reply_text(
        f"Comando {cmd} no reconocido en esta versión (v{BOT_VERSION}).\n"
        "Prueba /start para ver los comandos disponibles.\n"
        "Si acabas de actualizar, espera 1-2 min al redeploy de Railway."
    )


async def filtros_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Lista tags editoriales y países/regiones (comando informativo unificado)."""
    if not update.message:
        return
    if not is_authorized(update):
        await update.message.reply_text(
            unauthorized_message(update.effective_chat.id if update.effective_chat else "?")
        )
        return
    for chunk in split_message(list_available_filters()):
        await update.message.reply_text(chunk, disable_web_page_preview=True)


async def tags_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await filtros_command(update, context)


async def paises_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await filtros_command(update, context)


async def medios_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message:
        return
    if not is_authorized(update):
        await update.message.reply_text(
            unauthorized_message(update.effective_chat.id if update.effective_chat else "?")
        )
        return
    for chunk in split_message(list_available_medios()):
        await update.message.reply_text(chunk, disable_web_page_preview=True)


async def tag_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Compatibilidad: /tag redirige a /informe."""
    await informe_command(update, context)


async def _reply_markdown_document(
    message,
    *,
    articles: list[dict],
    mode: str,
    report_filter: ReportFilter | None,
) -> None:
    md = build_markdown_report(articles, mode=mode, report_filter=report_filter)
    filename = markdown_filename(mode=mode, report_filter=report_filter)
    payload = BytesIO(md.encode("utf-8"))
    payload.name = filename
    await message.reply_document(
        document=payload,
        filename=filename,
        caption=f"📄 Informe Markdown — {len(articles)} artículo(s)",
    )


async def informe_md_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    args = context.args or []
    try:
        parsed = parse_command_args(args)
    except ValueError as exc:
        if update.message:
            await update.message.reply_text(str(exc))
        return

    if parsed:
        report_filter = _filter_from_parsed(parsed)
        await _send_report(
            update,
            mode="informe_pais",
            record=False,
            report_filter=report_filter,
            markdown_only=True,
        )
    else:
        await _send_report(update, mode="informe", record=False, markdown_only=True)


async def descargar_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.effective_chat:
        return
    if not is_authorized(update):
        await update.message.reply_text(
            unauthorized_message(str(update.effective_chat.id))
        )
        return

    chat_id = str(update.effective_chat.id)
    session = load_session(chat_id)
    if not session or not session.article_ids:
        await update.message.reply_text(
            "No hay un informe reciente para descargar.\n"
            "Genera uno con /informe o /informe_md."
        )
        return

    try:
        since = datetime.fromisoformat(session.since_iso)
        articles = await asyncio.to_thread(
            _fetch_articles,
            since,
            include_sent=session.include_sent,
            report_filter=session.report_filter,
            article_ids=session.article_ids,
        )
        if not articles:
            await update.message.reply_text("El informe guardado no tiene artículos exportables.")
            return
        await _reply_markdown_document(
            update.message,
            articles=articles,
            mode=session.mode,
            report_filter=session.report_filter,
        )
    except Exception as exc:
        logger.exception("Markdown download failed")
        await update.message.reply_text(f"Error al generar el Markdown: {exc}")


async def descargar_db_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message:
        return
    if not is_authorized(update):
        await update.message.reply_text(
            unauthorized_message(update.effective_chat.id if update.effective_chat else "?")
        )
        return

    await update.message.reply_text("Preparando copia de la base de datos…")
    try:
        payload, filename = await asyncio.to_thread(export_database_bytes)
        size_mb = len(payload.getvalue()) / (1024 * 1024)
        await update.message.reply_document(
            document=payload,
            filename=filename,
            caption=(
                f"Base de datos editorial ({size_mb:.1f} MB)\n"
                "Ábrela con DB Browser for SQLite (sqlitebrowser.org)."
            ),
        )
    except FileNotFoundError as exc:
        await update.message.reply_text(str(exc))
    except Exception as exc:
        logger.exception("Database download failed")
        await update.message.reply_text(f"Error al exportar la base de datos: {exc}")


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


async def informe_hoy_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _send_report(update, mode="informe_hoy", record=False)


async def informe_mas_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _send_continuation(update)


async def free_text_report(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.message.text:
        return
    await _handle_natural_language(update, update.message.text.strip())


async def voice_report(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.message.voice:
        return
    if not is_authorized(update):
        await update.message.reply_text(
            unauthorized_message(update.effective_chat.id if update.effective_chat else "?")
        )
        return

    await update.message.reply_text("Un momento, escucho tu audio…")
    voice = update.message.voice
    try:
        tg_file = await context.bot.get_file(voice.file_id)
        buffer = BytesIO()
        await tg_file.download_to_memory(out=buffer)
        transcript = await asyncio.to_thread(
            transcribe_voice_bytes,
            buffer.getvalue(),
            mime_type="audio/ogg",
        )
    except VoiceTranscriptionError as exc:
        await update.message.reply_text(str(exc))
        return
    except Exception as exc:
        logger.exception("Voice report failed")
        await update.message.reply_text(f"No pude procesar el audio: {exc}")
        return

    await _handle_natural_language(update, transcript, heard_from_voice=True)


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
            "Genera uno con /informe o /informe 7 ficcion."
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
    *,
    markdown_only: bool = False,
    status_message: str | None = None,
) -> None:
    if not update.message or not update.effective_chat:
        return

    if not is_authorized(update):
        await update.message.reply_text(
            unauthorized_message(str(update.effective_chat.id))
        )
        return

    chat_id = str(update.effective_chat.id)
    if status_message:
        status = status_message
    else:
        label = "Markdown" if markdown_only else "informe"
        if settings.classify_before_telegram_report:
            status = f"Clasificando y generando {label}{_filter_label(report_filter)}…"
        else:
            status = f"Generando {label}{_filter_label(report_filter)}…"
    await update.message.reply_text(status)

    classify_cap = 1 if settings.classify_before_telegram_report else None
    try:
        report = await asyncio.to_thread(
            partial(
                build_editorial_report,
                mode=mode,
                report_filter=report_filter,
                chat_id=chat_id,
                classify_before_report=settings.classify_before_telegram_report,
                max_classify_batches=classify_cap,
                use_embedding_prioritization=settings.prioritize_before_telegram_report,
            )
        )

        export_articles = report.export_articles or []
        if markdown_only:
            if not export_articles:
                await update.message.reply_text(
                    "Informe vacío — no hay artículos para exportar en Markdown."
                )
                return
            await _reply_markdown_document(
                update.message,
                articles=export_articles,
                mode=report.mode,
                report_filter=report_filter,
            )
            if not export_articles:
                logger.info("Empty markdown export for mode=%s filter=%s", mode, report_filter)
            return

        chunks = split_message(report.text)

        for chunk in chunks:
            await _reply_report_chunk(update.message, chunk)

        if report.has_more and export_articles:
            await update.message.reply_text(
                f"Informe truncado en Telegram ({len(report.article_ids)} de "
                f"{len(export_articles)} artículos).\n"
                "Usa /informe_md o /descargar para el Markdown completo."
            )

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
