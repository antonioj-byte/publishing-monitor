"""Generate Telegram-formatted editorial reports."""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from ai.editorial_filter import apply_keyword_scope_filter, filter_editorial_scope
from ai.translation import is_likely_untranslated
from bot.config import settings
from db.connection import get_connection
from db.models import Categoria, ReportFilter
from medios_tiers import get_tier
from reports.dates import catalog_window_start, publication_since_iso, publication_within_window
from reports.pipeline_dates import pending_date_sql
from reports.medios_lookup import lookup_medio_id
from reports.session import ReportSession, save_session
from reports.telegram_format import esc, format_article_entry
from reports.prioritize import (
    _article_priority_key,
    events_to_trends,
    limit_batch_for_prioritization,
    prioritize_articles,
)
from reports.report_modes import ReportMode

logger = logging.getLogger(__name__)

_PENDING_CLASSIFY_HINT = (
    "Ejecuta `/reclasificar` (o espera al cron de clasificación, minuto :15 de cada franja). "
    "Luego repite el informe."
)


def _format_window_start(since: datetime) -> str:
    return since.astimezone(ZoneInfo(settings.timezone)).strftime("%d/%m/%Y")


def _wider_period_hint(days: int | None, label: str) -> str:
    slug = label.lower()
    current = days or 7
    if current >= 30:
        return f"Prueba otro filtro o `/diagnostico {current} {slug}`."
    if current >= 14:
        return f"Prueba un periodo más amplio: `/informe 30 {slug}`."
    if current >= 7:
        return f"Prueba un periodo más amplio: `/informe 14 {slug}`."
    return f"Prueba un periodo más amplio: `/informe 7 {slug}`."

CATEGORY_HEADERS: dict[Categoria, str] = {
    "ideas": "📚 Ideas del mundo editorial",
    "noticias": "📰 Noticias del mundo editorial",
}

MORE_FOOTER = (
    "\n\n---\n"
    "<i>Quedan {remaining} artículos más "
    f"(límite: {settings.max_report_words:,} palabras por envío).</i>\n"
    "Usa /informe_mas para continuar."
)


@dataclass
class ReportResult:
    text: str
    article_ids: list[int]
    mode: str
    truncated: bool = False
    total_matched: int = 0
    has_more: bool = False
    remaining_count: int = 0
    untranslated_count: int = 0
    word_count: int = 0
    export_articles: list[dict] | None = None


def _relevance_tiers() -> list[tuple[int, str, int]]:
    """Report sections by article relevance score (NOT media tier)."""
    return [
        (5, "🔥 Destacado (score 5)", settings.max_destacados),
        (4, "📌 Relevante (score 4)", settings.max_relevantes),
        (3, "📋 Secundarias (score 3)", settings.max_secundarios),
    ]


def _word_count(text: str) -> int:
    return len(re.findall(r"\S+", text))


def _tz_now() -> datetime:
    return datetime.now(ZoneInfo(settings.timezone))


def _last_cierre() -> datetime | None:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT fecha_cierre FROM informes ORDER BY id DESC LIMIT 1"
        ).fetchone()
    if not row:
        return None
    return datetime.fromisoformat(row["fecha_cierre"])


def _resolve_window(
    mode: str,
    report_filter: ReportFilter | None,
) -> tuple[datetime, bool, str]:
    now = _tz_now()
    if report_filter and report_filter.days:
        since = catalog_window_start(report_filter.days, now)
        return since, True, "informe_pais"
    if mode == "informe_hoy":
        since = now.replace(hour=0, minute=0, second=0, microsecond=0)
        return since, True, "informe_hoy"
    last = _last_cierre()
    since = last if last else now - timedelta(hours=24)
    return since, False, mode


def _count_country_candidates(
    report_filter: ReportFilter,
    since: datetime,
    *,
    date_by_publication: bool,
    strict_publication: bool = False,
) -> tuple[int, int, int]:
    """Return (classified relevant in window, pending, total for country/region)."""
    since_iso = publication_since_iso(since)
    date_expr, pub_filter = pending_date_sql(
        date_by_publication=date_by_publication,
        strict_publication=strict_publication,
    )
    geo = "m.pais = ?" if report_filter.pais else "m.region = ?"
    geo_val = report_filter.pais or report_filter.region

    with get_connection() as conn:
        in_window = conn.execute(
            f"""
            SELECT COUNT(*) FROM articulos a
            JOIN medios m ON m.id = a.medio_id
            WHERE {geo} AND a.procesado = 1 AND a.relevance_score >= ?
              {pub_filter}
              AND {date_expr} >= ?
            """,
            (geo_val, settings.min_relevance_score, since_iso),
        ).fetchone()[0]
        pending = conn.execute(
            f"""
            SELECT COUNT(*) FROM articulos a
            JOIN medios m ON m.id = a.medio_id
            WHERE {geo} AND a.procesado = 0
              {pub_filter}
              AND {date_expr} >= ?
            """,
            (geo_val, since_iso),
        ).fetchone()[0]
        total_geo = conn.execute(
            f"""
            SELECT COUNT(*) FROM articulos a
            JOIN medios m ON m.id = a.medio_id
            WHERE {geo}
            """,
            (geo_val,),
        ).fetchone()[0]
    return in_window, pending, total_geo


def _count_medio_candidates(
    report_filter: ReportFilter,
    since: datetime,
    *,
    date_by_publication: bool,
    strict_publication: bool = False,
) -> tuple[int, int, int]:
    """Return (classified relevant in window, pending, total for medio)."""
    since_iso = publication_since_iso(since)
    date_expr, pub_filter = pending_date_sql(
        date_by_publication=date_by_publication,
        strict_publication=strict_publication,
    )
    medio = report_filter.medio_nombre

    with get_connection() as conn:
        in_window = conn.execute(
            f"""
            SELECT COUNT(*) FROM articulos a
            JOIN medios m ON m.id = a.medio_id
            WHERE m.nombre = ? AND a.procesado = 1 AND a.relevance_score >= ?
              {pub_filter}
              AND {date_expr} >= ?
            """,
            (medio, settings.min_relevance_score, since_iso),
        ).fetchone()[0]
        pending = conn.execute(
            f"""
            SELECT COUNT(*) FROM articulos a
            JOIN medios m ON m.id = a.medio_id
            WHERE m.nombre = ? AND a.procesado = 0
              {pub_filter}
              AND {date_expr} >= ?
            """,
            (medio, since_iso),
        ).fetchone()[0]
        total_medio = conn.execute(
            """
            SELECT COUNT(*) FROM articulos a
            JOIN medios m ON m.id = a.medio_id
            WHERE m.nombre = ?
            """,
            (medio,),
        ).fetchone()[0]
    return in_window, pending, total_medio


def _article_has_tags(raw_tags: str, wanted: set[str]) -> bool:
    try:
        tags = json.loads(raw_tags)
    except (json.JSONDecodeError, TypeError):
        return False
    if not isinstance(tags, list):
        return False
    return any(tag in wanted for tag in tags)


def _fetch_sql_rows(
    since: datetime,
    *,
    include_sent: bool,
    report_filter: ReportFilter | None,
    date_by_publication: bool,
    strict_publication: bool,
    apply_tags: bool = True,
) -> list[dict]:
    """Load classified articles from SQL without post-filters."""
    min_score = settings.min_relevance_score
    since_iso = publication_since_iso(since)
    query = """
        SELECT a.id, a.titulo_original, a.titular_traducido, a.resumen_generado,
               a.resumen_raw, a.relevance_score, a.tags, a.enviado,
               m.pais, m.region
        FROM articulos a
        JOIN medios m ON m.id = a.medio_id
        WHERE a.procesado = 1 AND a.relevance_score >= ?
    """
    params: list[object] = [min_score]

    date_expr, pub_filter = pending_date_sql(
        date_by_publication=date_by_publication,
        strict_publication=strict_publication,
    )
    if pub_filter:
        query += f" {pub_filter}"
    query += f" AND {date_expr} >= ?"
    params.append(since_iso)

    if report_filter:
        if report_filter.pais:
            query += " AND m.pais = ?"
            params.append(report_filter.pais)
        elif report_filter.region:
            query += " AND m.region = ?"
            params.append(report_filter.region)
        if report_filter.medio_nombre:
            query += " AND m.nombre = ?"
            params.append(report_filter.medio_nombre)
        if apply_tags and report_filter.tags:
            placeholders = ",".join("?" * len(report_filter.tags))
            query += f"""
              AND a.tags IS NOT NULL
              AND EXISTS (
                SELECT 1 FROM json_each(a.tags) je
                WHERE je.value IN ({placeholders})
              )
            """
            params.extend(report_filter.tags)

    if not include_sent:
        query += " AND a.enviado = 0"

    with get_connection() as conn:
        rows = conn.execute(query, params).fetchall()
    return [dict(row) for row in rows]


def _diagnose_empty_fetch(
    since: datetime,
    *,
    include_sent: bool,
    report_filter: ReportFilter | None,
    date_by_publication: bool,
    strict_publication: bool,
) -> dict[str, int]:
    """Explain why SQL has candidates but the report query returned none."""
    base_rows = _fetch_sql_rows(
        since,
        include_sent=True,
        report_filter=report_filter,
        date_by_publication=date_by_publication,
        strict_publication=strict_publication,
        apply_tags=False,
    )
    with_tags_rows = base_rows
    if report_filter and report_filter.tags:
        tag_set = set(report_filter.tags)
        with_tags_rows = [
            row
            for row in base_rows
            if row.get("tags")
            and row["tags"] not in ("", "[]")
            and _article_has_tags(row["tags"], tag_set)
        ]

    unsent_rows = [row for row in with_tags_rows if not row.get("enviado")]
    keyword_rows = filter_editorial_scope(with_tags_rows)
    working_rows = unsent_rows if not include_sent else with_tags_rows
    keyword_unsent = filter_editorial_scope(working_rows)

    missing_tags = sum(
        1
        for row in base_rows
        if not row.get("tags") or row["tags"] in ("", "[]")
    )

    return {
        "sql_total": len(base_rows),
        "with_tags": len(with_tags_rows),
        "unsent": len(unsent_rows),
        "blocked_tags": max(0, len(base_rows) - len(with_tags_rows)),
        "blocked_enviado": max(0, len(with_tags_rows) - len(unsent_rows)),
        "blocked_keyword": max(0, len(working_rows) - len(keyword_unsent)),
        "missing_tags": missing_tags,
    }


def _count_tag_candidates(
    report_filter: ReportFilter,
    since: datetime,
    *,
    date_by_publication: bool,
    strict_publication: bool = False,
) -> tuple[int, int, int, int]:
    """Return (with tag in window, classified in window, missing tags, pending)."""
    since_iso = publication_since_iso(since)
    date_expr, pub_filter = pending_date_sql(
        date_by_publication=date_by_publication,
        strict_publication=strict_publication,
    )
    tag_keys = report_filter.tags or []
    placeholders = ",".join("?" * len(tag_keys))

    with get_connection() as conn:
        with_tag = conn.execute(
            f"""
            SELECT COUNT(*) FROM articulos a
            WHERE a.procesado = 1 AND a.relevance_score >= ?
              {pub_filter}
              AND {date_expr} >= ?
              AND a.tags IS NOT NULL AND a.tags != '' AND a.tags != '[]'
              AND EXISTS (
                SELECT 1 FROM json_each(a.tags) je
                WHERE je.value IN ({placeholders})
              )
            """,
            (settings.min_relevance_score, since_iso, *tag_keys),
        ).fetchone()[0]
        in_window = conn.execute(
            f"""
            SELECT COUNT(*) FROM articulos a
            WHERE a.procesado = 1 AND a.relevance_score >= ?
              {pub_filter}
              AND {date_expr} >= ?
            """,
            (settings.min_relevance_score, since_iso),
        ).fetchone()[0]
        missing_tags = conn.execute(
            """
            SELECT COUNT(*) FROM articulos
            WHERE procesado = 1
              AND (tags IS NULL OR tags = '' OR tags = '[]')
            """
        ).fetchone()[0]
        pending = conn.execute(
            f"""
            SELECT COUNT(*) FROM articulos a
            WHERE a.procesado = 0
              {pub_filter}
              AND {date_expr} >= ?
            """,
            (since_iso,),
        ).fetchone()[0]
    return with_tag, in_window, missing_tags, pending


def _empty_tag_message(
    report_filter: ReportFilter,
    since: datetime,
    *,
    date_by_publication: bool,
    strict_publication: bool = False,
) -> str:
    with_tag, in_window, missing_tags, pending = _count_tag_candidates(
        report_filter,
        since,
        date_by_publication=date_by_publication,
        strict_publication=strict_publication,
    )
    tag_label = ", ".join(report_filter.tag_labels or report_filter.tags or ["tag"])
    lines = [
        f"<i>No hay artículos de {esc(tag_label)} "
        f"en los últimos {report_filter.days} días.</i>",
        "",
        f"Ventana: desde {_format_window_start(since)}.",
        f"En base de datos: {with_tag} con tag en ventana, "
        f"{in_window} clasificados en ventana (cualquier tag), "
        f"{pending} pendientes de clasificar.",
    ]
    if missing_tags:
        lines.append(
            f"{missing_tags} artículo(s) clasificados sin tags editoriales "
            "(clasificación anterior a tags o modo offline). "
            "Ejecuta `/retag` (recomendado) o `/reclasificar`."
        )
    elif pending:
        lines.append(
            f"Hay {pending} artículo(s) sin clasificar en este periodo. "
            f"{_PENDING_CLASSIFY_HINT}"
        )
    elif in_window and not with_tag:
        lines.append(
            "Hay artículos en la ventana, pero ninguno tiene este tag. "
            "Prueba otro periodo (`/informe 14 ficcion`) o revisa `/tags`."
        )
    elif with_tag:
        lines.append(
            "Hay artículos con este tag en ventana, pero fueron "
            "descartados por el filtro editorial o priorización."
        )
    else:
        lines.append(
            "Prueba un periodo más amplio o revisa con "
            "`python3 scripts/diagnose_pipeline.py 7 ficcion`."
        )
    return "\n".join(lines)


def _empty_medio_message(
    report_filter: ReportFilter,
    since: datetime,
    *,
    date_by_publication: bool,
    strict_publication: bool = False,
) -> str:
    label = report_filter.medio_nombre or "el medio"
    if not lookup_medio_id(label):
        return "\n".join(
            [
                f"<i>No hay artículos de {esc(label)} en la base de datos.</i>",
                "",
                "El medio está en el catálogo (medios.csv) pero aún no se ha "
                "sincronizado con la BD de producción.",
                "Tras el redeploy el bot lo registra e ingiere artículos al arrancar; "
                "vuelve a pedir el informe en 2-3 minutos.",
            ]
        )

    in_window, pending, total_medio = _count_medio_candidates(
        report_filter,
        since,
        date_by_publication=date_by_publication,
        strict_publication=strict_publication,
    )
    label = report_filter.medio_nombre or "el medio"
    lines = [
        f"<i>No hay artículos editoriales de {esc(label)} "
        f"en los últimos {report_filter.days} días.</i>",
        "",
        f"Ventana: desde {_format_window_start(since)}.",
        f"En base de datos: {total_medio} artículos de {label} en total, "
        f"{in_window} clasificados en ventana, {pending} pendientes de clasificar.",
    ]
    if pending:
        lines.append(
            f"Hay {pending} artículo(s) de {label} sin clasificar en este periodo. "
            f"{_PENDING_CLASSIFY_HINT}"
        )
        if report_filter.days and report_filter.days < 7:
            slug = label.lower().replace(" ", " ")
            lines.append(f"Prueba un periodo más amplio: `/informe 7 {slug}`.")
    elif total_medio == 0:
        lines.append(
            "No hay artículos ingeridos de ese medio. Revisa `/medios` "
            "o ejecuta `python3 scripts/run_ingest_once.py`."
        )
    elif in_window:
        diag = _diagnose_empty_fetch(
            since,
            include_sent=True,
            report_filter=report_filter,
            date_by_publication=date_by_publication,
            strict_publication=strict_publication,
        )
        if report_filter.tags and diag["blocked_tags"]:
            lines.append(
                f"{diag['blocked_tags']} artículo(s) en ventana no tienen el tag pedido."
            )
        elif diag["blocked_keyword"]:
            lines.append(
                "Hay artículos clasificados en ventana, pero el filtro editorial "
                "los descartó."
            )
        else:
            lines.append(
                "Hay artículos clasificados en ventana, pero fueron "
                "descartados por priorización o ya enviados."
            )
    else:
        slug = label.lower().replace(" ", " ")
        lines.append(
            "Ningún artículo cae en esta ventana "
            "(publicación e ingesta anteriores al inicio indicado)."
        )
        lines.append(_wider_period_hint(report_filter.days, slug))
        lines.append(f"Más detalle: `/diagnostico {report_filter.days or 7} {slug}`.")
    return "\n".join(lines)


def _count_today_candidates(since: datetime) -> dict[str, int]:
    """Counts for /informe_hoy diagnostics (strict publication date)."""
    since_iso = publication_since_iso(since)
    min_score = settings.min_relevance_score
    with get_connection() as conn:
        published_today = conn.execute(
            """
            SELECT COUNT(*) FROM articulos
            WHERE fecha_publicacion IS NOT NULL AND fecha_publicacion != ''
              AND fecha_publicacion >= ?
            """,
            (since_iso,),
        ).fetchone()[0]
        relevant = conn.execute(
            """
            SELECT COUNT(*) FROM articulos
            WHERE procesado = 1 AND relevance_score >= ?
              AND fecha_publicacion IS NOT NULL AND fecha_publicacion != ''
              AND fecha_publicacion >= ?
            """,
            (min_score, since_iso),
        ).fetchone()[0]
        low_score = conn.execute(
            """
            SELECT COUNT(*) FROM articulos
            WHERE procesado = 1 AND relevance_score < ?
              AND fecha_publicacion IS NOT NULL AND fecha_publicacion != ''
              AND fecha_publicacion >= ?
            """,
            (min_score, since_iso),
        ).fetchone()[0]
        pending = conn.execute(
            """
            SELECT COUNT(*) FROM articulos
            WHERE procesado = 0
              AND fecha_publicacion IS NOT NULL AND fecha_publicacion != ''
              AND fecha_publicacion >= ?
            """,
            (since_iso,),
        ).fetchone()[0]
        ingested_today = conn.execute(
            """
            SELECT COUNT(*) FROM articulos
            WHERE fecha_ingesta >= ?
            """,
            (since_iso,),
        ).fetchone()[0]
    return {
        "published_today": published_today,
        "relevant": relevant,
        "low_score": low_score,
        "pending": pending,
        "ingested_today": ingested_today,
    }


def _empty_today_message(since: datetime) -> str:
    stats = _count_today_candidates(since)
    min_score = settings.min_relevance_score
    lines = [
        "<i>No hay artículos publicados hoy que cumplan los criterios "
        f"(score ≥ {min_score}, alcance editorial).</i>",
        "",
        "En base de datos (fecha de publicación = hoy):",
        f"  · {stats['published_today']} con fecha de hoy",
        f"  · {stats['relevant']} clasificados con score ≥ {min_score}",
        f"  · {stats['low_score']} clasificados pero descartados (score bajo / fuera de alcance)",
        f"  · {stats['pending']} pendientes de clasificar",
        f"  · {stats['ingested_today']} ingeridos hoy (pueden ser de días anteriores)",
    ]
    if stats["published_today"] == 0:
        lines.extend(
            [
                "",
                "Todavía no hay artículos con fecha de publicación de hoy en la BD.",
                "Prueba `/informe` (desde el último cierre) o `/informe 2`.",
                "Nota: `/muestra` ordena por ingesta, no por publicación.",
            ]
        )
    elif stats["pending"]:
        lines.extend(
            [
                "",
                "Hay artículos de hoy sin clasificar. "
                f"{_PENDING_CLASSIFY_HINT}",
            ]
        )
    elif stats["low_score"] and not stats["relevant"]:
        lines.extend(
            [
                "",
                "Hay artículos de hoy pero fuera de alcance editorial (ruido). "
                "Revisa `/muestra ruido`.",
            ]
        )
    elif stats["relevant"]:
        lines.extend(
            [
                "",
                "Hay candidatos con score alto pero el filtro editorial los descartó. "
                "Prueba `/diagnostico`.",
            ]
        )
    return "\n".join(lines)


def _empty_country_message(
    report_filter: ReportFilter,
    since: datetime,
    *,
    date_by_publication: bool,
    strict_publication: bool = False,
) -> str:
    in_window, pending, total_geo = _count_country_candidates(
        report_filter,
        since,
        date_by_publication=date_by_publication,
        strict_publication=strict_publication,
    )
    label = report_filter.location_label or "la zona"
    lines = [
        f"<i>No hay artículos editoriales de {esc(label)} "
        f"en los últimos {report_filter.days} días.</i>",
        "",
        f"Ventana: desde {_format_window_start(since)}.",
        f"En base de datos: {total_geo} artículos de {label} en total, "
        f"{in_window} clasificados en ventana, {pending} pendientes de clasificar.",
    ]
    if pending:
        lines.append(
            f"Hay {pending} artículo(s) de {label} sin clasificar en este periodo. "
            f"{_PENDING_CLASSIFY_HINT}"
        )
        if report_filter.days and report_filter.days < 7:
            lines.append(
                f"Prueba un periodo más amplio: `/informe 7 {label.lower()}`."
            )
    elif total_geo == 0:
        lines.append(
            "No hay artículos ingeridos de ese país. Ejecuta: "
            "`python3 scripts/run_ingest_once.py`"
        )
    elif in_window:
        diag = _diagnose_empty_fetch(
            since,
            include_sent=True,
            report_filter=report_filter,
            date_by_publication=date_by_publication,
            strict_publication=strict_publication,
        )
        if report_filter.tags and diag["blocked_tags"]:
            lines.append(
                f"{diag['blocked_tags']} artículo(s) en ventana no tienen el tag pedido."
            )
            if diag["missing_tags"]:
                lines.append(
                    f"{diag['missing_tags']} clasificados sin tags — ejecuta `/retag`."
                )
        elif diag["blocked_enviado"]:
            lines.append(
                "Hay artículos clasificados, pero ya se enviaron en un informe anterior. "
                f"{_wider_period_hint(report_filter.days, label)}"
            )
        elif diag["blocked_keyword"]:
            lines.append(
                "Hay artículos clasificados en la ventana, pero el filtro editorial "
                "por palabras clave los descartó. Ejecuta `/reclasificar` para "
                "revisarlos con Claude."
            )
        else:
            lines.append(
                "Hay artículos clasificados en la ventana, pero no pasaron los filtros "
                "del informe. Revisa con "
                f"`python3 scripts/diagnose_pipeline.py {report_filter.days} {label.lower()}`."
            )
    else:
        lines.append(
            f"Ninguno de los {total_geo} artículos cae en esta ventana "
            "(publicación e ingesta anteriores al inicio indicado)."
        )
        lines.append(_wider_period_hint(report_filter.days, label))
        lines.append(
            f"Más detalle: `/diagnostico {report_filter.days or 7} {label.lower()}`."
        )
    return "\n".join(lines)


def _fetch_articles(
    since: datetime,
    include_sent: bool = False,
    report_filter: ReportFilter | None = None,
    article_ids: list[int] | None = None,
    *,
    date_by_publication: bool = False,
    strict_publication: bool = False,
) -> list[dict]:
    min_score = settings.min_relevance_score
    query = """
        SELECT a.id, a.titulo_original, a.titular_traducido, a.resumen_generado,
               a.resumen_raw, a.idioma, a.url, a.categoria, a.relevance_score,
               a.fecha_publicacion, a.fecha_ingesta, a.tags,
               m.region, m.pais, m.nombre AS medio_nombre, m.tier AS medio_tier
        FROM articulos a
        JOIN medios m ON m.id = a.medio_id
        WHERE a.procesado = 1
          AND a.relevance_score >= ?
    """
    params: list = [min_score]

    if article_ids:
        placeholders = ",".join("?" * len(article_ids))
        query += f" AND a.id IN ({placeholders})"
        params.extend(article_ids)
    else:
        since_iso = publication_since_iso(since)
        date_expr, pub_filter = pending_date_sql(
            date_by_publication=date_by_publication,
            strict_publication=strict_publication,
        )
        if pub_filter:
            query += f" {pub_filter}"
        query += f" AND {date_expr} >= ?"
        params.append(since_iso)

    if report_filter:
        if report_filter.pais:
            query += " AND m.pais = ?"
            params.append(report_filter.pais)
        elif report_filter.region:
            query += " AND m.region = ?"
            params.append(report_filter.region)
        if report_filter.medio_nombre:
            query += " AND m.nombre = ?"
            params.append(report_filter.medio_nombre)
        if report_filter.tags:
            placeholders = ",".join("?" * len(report_filter.tags))
            query += f"""
              AND a.tags IS NOT NULL
              AND EXISTS (
                SELECT 1 FROM json_each(a.tags) je
                WHERE je.value IN ({placeholders})
              )
            """
            params.extend(report_filter.tags)

    # A continuation uses a persisted snapshot of IDs. Keep already-shown IDs
    # in that snapshot so its cursor still addresses the same ordered list.
    if not include_sent and not article_ids:
        query += " AND a.enviado = 0"

    query += " ORDER BY a.relevance_score DESC, a.categoria, a.fecha_ingesta DESC"

    with get_connection() as conn:
        rows = conn.execute(query, params).fetchall()
    articles = [dict(r) for r in rows]

    for article in articles:
        article["medio_tier"] = get_tier(
            article.get("medio_nombre", ""),
        )

    articles = apply_keyword_scope_filter(articles)

    if date_by_publication and strict_publication and not article_ids:
        articles = [
            a
            for a in articles
            if publication_within_window(a.get("fecha_publicacion"), since)
        ]

    if article_ids:
        order = {aid: idx for idx, aid in enumerate(article_ids)}
        articles.sort(key=lambda a: order.get(a["id"], 999999))

    return articles


def _is_catalog_report(report_filter: ReportFilter | None, mode: str) -> bool:
    """Multi-day tag/country reports browse a catalog; not breaking-news digests."""
    if not ReportMode.from_str(mode).is_catalog or not report_filter:
        return False
    days = report_filter.days or 0
    if days <= 1:
        return False
    return bool(
        report_filter.tags
        or report_filter.pais
        or report_filter.region
        or report_filter.medio_nombre
    )


def _order_catalog_articles(articles: list[dict]) -> list[dict]:
    """Order catalog reports by score tier and recency — no event collapse."""
    ordered: list[dict] = []
    seen_ids: set[int] = set()
    for categoria in ("ideas", "noticias"):
        cat_items = [a for a in articles if a.get("categoria") == categoria]
        for score, _, _ in _relevance_tiers():
            tier_items = sorted(
                [a for a in cat_items if (a.get("relevance_score") or 3) == score],
                key=_article_priority_key,
            )
            for article in tier_items:
                if article["id"] not in seen_ids:
                    seen_ids.add(article["id"])
                    ordered.append(article)
    extras = sorted(
        [a for a in articles if a["id"] not in seen_ids],
        key=_article_priority_key,
    )
    ordered.extend(extras)
    return ordered


def _order_articles(articles: list[dict]) -> list[dict]:
    """Order by event score, then category and relevance."""
    ordered: list[dict] = []
    seen_event_ids: set[int] = set()
    event_order: list[int] = []
    for article in articles:
        eid = article.get("event_id")
        if eid is not None and eid not in seen_event_ids:
            seen_event_ids.add(eid)
            event_order.append(eid)

    for event_id in event_order:
        event_articles = [a for a in articles if a.get("event_id") == event_id]
        for categoria in ("ideas", "noticias"):
            cat_items = [a for a in event_articles if a["categoria"] == categoria]
            for score, _, _ in _relevance_tiers():
                tier_items = [
                    a for a in cat_items if (a.get("relevance_score") or 3) == score
                ]
                ordered.extend(tier_items)

    orphans = [a for a in articles if a.get("event_id") is None]
    if orphans:
        for categoria in ("ideas", "noticias"):
            cat_items = [a for a in orphans if a["categoria"] == categoria]
            for score, _, _ in _relevance_tiers():
                tier_items = [
                    a for a in cat_items if (a.get("relevance_score") or 3) == score
                ]
                ordered.extend(tier_items)
    return ordered


def _collapse_events_for_report(articles: list[dict]) -> list[dict]:
    """
    One article per editorial event in the report body.

    Multi-source events are summarized in 📡 En varios medios; the body keeps
    the best single entry so trade press does not fill the word budget.
    """
    by_event: dict[int, list[dict]] = {}
    orphans: list[dict] = []
    event_order: list[int] = []

    for article in articles:
        event_id = article.get("event_id")
        if event_id is None:
            orphans.append(article)
            continue
        if event_id not in by_event:
            event_order.append(event_id)
        by_event.setdefault(event_id, []).append(article)

    collapsed: list[dict] = []
    for event_id in event_order:
        cluster = by_event[event_id]
        best = min(cluster, key=_article_priority_key)
        collapsed.append(best)

    collapsed.extend(orphans)
    return collapsed


def _round_robin_by_medio(candidates: list[dict], limit: int) -> list[dict]:
    """Pick up to `limit` articles rotating across medios (fair source mix)."""
    if limit <= 0 or not candidates:
        return []

    by_medio: dict[str, list[dict]] = {}
    for article in candidates:
        medio = article.get("medio_nombre") or "?"
        by_medio.setdefault(medio, []).append(article)

    medio_counts: dict[str, int] = {name: 0 for name in by_medio}
    max_per_medio = max(1, settings.max_articles_per_medio)
    picked: list[dict] = []

    while len(picked) < limit:
        progressed = False
        for medio in sorted(
            by_medio.keys(),
            key=lambda name: (medio_counts[name], name),
        ):
            if medio_counts[medio] >= max_per_medio:
                continue
            queue = by_medio[medio]
            if not queue:
                continue
            picked.append(queue.pop(0))
            medio_counts[medio] += 1
            progressed = True
            if len(picked) >= limit:
                break
        if not progressed:
            break

    return picked


def _apply_report_limits(articles: list[dict]) -> list[dict]:
    """Apply score/total limits with round-robin across medios within each tier."""
    per_score_limits = {score: limit for score, _, limit in _relevance_tiers()}
    by_score: dict[int, list[dict]] = {}
    for article in articles:
        score = int(article.get("relevance_score") or 3)
        by_score.setdefault(score, []).append(article)

    limited: list[dict] = []
    total_limit = max(0, settings.max_articles_per_informe)

    for score, _, _ in _relevance_tiers():
        score_limit = max(0, per_score_limits.get(score, 0))
        if score_limit <= 0:
            continue
        tier_picks = _round_robin_by_medio(by_score.get(score, []), score_limit)
        for article in tier_picks:
            if total_limit and len(limited) >= total_limit:
                return limited
            limited.append(article)

    return limited


def _format_entry(item: dict, *, show_tier: bool = False) -> str:
    return format_article_entry(item)


def _format_trends_section(trends: list[dict], max_trends: int = 5) -> list[str]:
    if not trends:
        return []

    lines = ["📡 En varios medios", ""]
    for trend in trends[:max_trends]:
        medios_parts: list[str] = []
        seen: set[str] = set()
        for item in trend["articles"]:
            name = item.get("medio_nombre", "")
            if not name or name in seen:
                continue
            seen.add(name)
            medios_parts.append(name)
        medios_parts.sort()
        medios = esc(", ".join(medios_parts))
        label = esc(trend["topic_label"].replace("|", " · "))
        score_note = ""
        if trend.get("event_score") is not None:
            score_note = f" · puntuación {trend['event_score']:.2f}"
        lines.append(f"• <i>{label}{score_note}</i> — {len(trend['medios'])} medios: {medios}")
        if trend.get("event_explanation"):
            lines.append(f"  <i>({esc(trend['event_explanation'])})</i>")
        lines.append("")
    return lines


def _header_lines(mode: str, report_filter: ReportFilter | None, now: datetime) -> list[str]:
    date_str = now.strftime("%d/%m/%Y")
    tag_part = ""
    if report_filter and report_filter.tag_labels:
        tag_part = ", ".join(report_filter.tag_labels)

    if mode == "informe_pais" and report_filter:
        if report_filter.medio_nombre:
            title = (
                f"📋 Informe — {report_filter.medio_nombre} "
                f"(últimos {report_filter.days} días)"
            )
        elif report_filter.location_label:
            title = (
                f"📋 Informe — {report_filter.location_label} "
                f"(últimos {report_filter.days} días)"
            )
        elif tag_part:
            title = f"📋 Informe — {tag_part} (últimos {report_filter.days} días)"
        else:
            title = f"📋 Informe (últimos {report_filter.days} días)"
        if tag_part and (
            report_filter.location_label or report_filter.medio_nombre
        ):
            title += f" · {tag_part}"
        elif tag_part and not report_filter.medio_nombre and not report_filter.location_label:
            pass
        lines = [f"{title} — {date_str}"]
    elif mode == "informe_hoy":
        lines = [
            f"📋 Informe de hoy — {date_str}",
            "<i>Solo artículos publicados en web hoy (fecha de publicación).</i>",
        ]
    elif mode == "informe_mas":
        lines = [f"📋 Informe (continuación) — {date_str}"]
    else:
        lines = [
            f"📋 Informe editorial — {date_str}",
            "<i>Artículos publicados desde el último cierre.</i>",
        ]
    return lines


def _append_within_word_limit(
    lines: list[str],
    block: str,
    *,
    max_words: int,
    current_words: int,
) -> tuple[bool, int]:
    """Append block if it fits; return (appended, new_word_count)."""
    block_words = _word_count(block)
    if current_words > 0 and current_words + block_words > max_words:
        return False, current_words
    lines.append(block)
    return True, current_words + block_words


def _build_pages(
    *,
    mode: str,
    report_filter: ReportFilter | None,
    since: datetime,
    include_sent: bool,
    ordered_articles: list[dict],
    trends: list[dict],
    start_cursor: int = 0,
    include_trends: bool = True,
    max_words: int | None = None,
) -> tuple[str, list[int], int, bool, int]:
    word_budget = max_words or settings.max_report_words
    now = _tz_now()
    lines: list[str] = _header_lines(mode, report_filter, now)
    lines.append("")
    word_count = _word_count("\n".join(lines))
    article_ids: list[int] = []
    untranslated_count = 0

    if include_trends and start_cursor == 0:
        trend_text = "\n".join(_format_trends_section(trends))
        if trend_text:
            added, word_count = _append_within_word_limit(
                lines, trend_text, max_words=word_budget, current_words=word_count
            )
            if not added and ordered_articles:
                pass  # skip trends if no room; articles more important

    flat_continuation = start_cursor > 0
    current_category: str | None = None
    current_tier: int | None = None

    for idx in range(start_cursor, len(ordered_articles)):
        item = ordered_articles[idx]
        score = item.get("relevance_score") or 3
        categoria = item["categoria"]

        blocks_to_add: list[str] = []
        if not flat_continuation:
            if categoria != current_category:
                blocks_to_add.extend([CATEGORY_HEADERS[categoria], ""])
                current_category = categoria
                current_tier = None

            tier_title = next(t[1] for t in _relevance_tiers() if t[0] == score)
            if score != current_tier:
                blocks_to_add.extend([tier_title, ""])
                current_tier = score

        blocks_to_add.extend([_format_entry(item), ""])

        prospective = word_count + _word_count("\n".join(blocks_to_add))
        if article_ids and prospective > word_budget:
            break
        if not article_ids and prospective > word_budget:
            # Always advance the cursor. A single oversized entry is preferable
            # to an endless /informe_mas loop at the same position.
            lines.extend(blocks_to_add)
            word_count = prospective
            article_ids.append(item["id"])
            if is_likely_untranslated(
                idioma=item.get("idioma", "es"),
                titulo_original=item.get("titulo_original", ""),
                titular_traducido=item.get("titular_traducido"),
                resumen_generado=item.get("resumen_generado"),
                resumen_raw=item.get("resumen_raw"),
            ):
                untranslated_count += 1
            continue

        for block in blocks_to_add:
            added, word_count = _append_within_word_limit(
                lines, block, max_words=word_budget, current_words=word_count
            )
            if not added:
                break
        else:
            article_ids.append(item["id"])
            if is_likely_untranslated(
                idioma=item.get("idioma", "es"),
                titulo_original=item.get("titulo_original", ""),
                titular_traducido=item.get("titular_traducido"),
                resumen_generado=item.get("resumen_generado"),
                resumen_raw=item.get("resumen_raw"),
            ):
                untranslated_count += 1
            continue
        break

    while lines and lines[-1] == "":
        lines.pop()

    new_cursor = start_cursor + len(article_ids)
    has_more = new_cursor < len(ordered_articles)
    if has_more:
        lines.append(MORE_FOOTER.format(remaining=len(ordered_articles) - new_cursor))

    if untranslated_count:
        lines.append(
            f"\n\n<i>⚠️ {untranslated_count} artículo(s) sin traducir al castellano. "
            "Ejecuta python3 scripts/reclassify_untranslated.py --yes</i>"
        )

    body = "\n".join(lines)
    return body, article_ids, new_cursor, has_more, untranslated_count


def build_report(
    mode: str = "informe",
    report_filter: ReportFilter | None = None,
    *,
    continuation: ReportSession | None = None,
    chat_id: str | None = None,
    use_embedding_prioritization: bool = True,
) -> ReportResult:
    if continuation:
        since = datetime.fromisoformat(continuation.since_iso)
        include_sent = continuation.include_sent
        mode = continuation.mode
        report_filter = continuation.report_filter
        all_ids = continuation.article_ids
        articles = _fetch_articles(
            since,
            include_sent=include_sent,
            report_filter=report_filter,
            article_ids=all_ids,
        )
        trends: list[dict] = []
        ordered = articles
        start_cursor = continuation.cursor
        include_trends = False
        display_mode = "informe_mas"
    else:
        since, include_sent, resolved_mode = _resolve_window(mode, report_filter)
        mode = resolved_mode
        report_mode = ReportMode.from_str(mode)
        use_pub_date = report_mode.uses_publication_date
        strict_publication = report_mode.strict_publication_date
        articles = _fetch_articles(
            since,
            include_sent=include_sent,
            report_filter=report_filter,
            date_by_publication=use_pub_date,
            strict_publication=strict_publication,
        )
        if not articles:
            now = _tz_now()
            lines = _header_lines(mode, report_filter, now)
            lines.append("")
            if mode == "informe_pais" and report_filter:
                if report_filter.tags and not report_filter.pais and not report_filter.region and not report_filter.medio_nombre:
                    lines.append(
                        _empty_tag_message(
                            report_filter,
                            since,
                            date_by_publication=use_pub_date,
                            strict_publication=strict_publication,
                        )
                    )
                elif report_filter.medio_nombre:
                    lines.append(
                        _empty_medio_message(
                            report_filter,
                            since,
                            date_by_publication=use_pub_date,
                            strict_publication=strict_publication,
                        )
                    )
                elif report_filter.pais or report_filter.region:
                    lines.append(
                        _empty_country_message(
                            report_filter,
                            since,
                            date_by_publication=use_pub_date,
                            strict_publication=strict_publication,
                        )
                    )
                else:
                    lines.append(
                        "<i>No hay artículos que cumplan los criterios en este periodo.</i>"
                    )
            else:
                if mode == "informe_hoy":
                    lines.append(_empty_today_message(since))
                else:
                    lines.append(
                        "<i>No hay artículos que cumplan los criterios en este periodo.</i>"
                    )
            return ReportResult(
                text="\n".join(lines),
                article_ids=[],
                mode=mode,
                total_matched=0,
            )

        batch, _ = limit_batch_for_prioritization(articles)
        catalog = _is_catalog_report(report_filter, mode)
        recency_window_days = (
            report_filter.days if catalog and report_filter and report_filter.days else None
        )
        if use_embedding_prioritization:
            prioritization = prioritize_articles(batch, recency_window_days=recency_window_days)
            if not prioritization.articles and not catalog:
                now = _tz_now()
                lines = _header_lines(mode, report_filter, now)
                lines.append("")
                lines.append(
                    "<i>No hay eventos editoriales que superen el umbral de priorización "
                    f"({settings.prioritize_score_threshold:.2f}) en este periodo.</i>"
                )
                return ReportResult(
                    text="\n".join(lines),
                    article_ids=[],
                    mode=mode,
                    total_matched=0,
                )

            trends = events_to_trends(prioritization.events)
            if catalog:
                ordered = _apply_report_limits(_order_catalog_articles(batch))
            else:
                collapsed = _collapse_events_for_report(prioritization.articles)
                ordered = _apply_report_limits(_order_articles(collapsed))
        else:
            logger.info("Prioritization: skipped embeddings (fast Telegram path)")
            trends = []
            ordered = _apply_report_limits(_order_catalog_articles(batch))
        total_matched = len(ordered)
        all_ids = [a["id"] for a in ordered]
        start_cursor = 0
        include_trends = True
        display_mode = mode

    text, shown_ids, new_cursor, has_more, untranslated = _build_pages(
        mode=display_mode,
        report_filter=report_filter,
        since=since,
        include_sent=include_sent,
        ordered_articles=ordered,
        trends=trends,
        start_cursor=start_cursor,
        include_trends=include_trends,
    )

    if chat_id and ordered:
        save_session(
            ReportSession(
                chat_id=chat_id,
                mode=mode,
                since_iso=since.isoformat(),
                include_sent=include_sent,
                report_filter=report_filter,
                article_ids=all_ids,
                cursor=new_cursor,
                trends_included=include_trends or bool(continuation and continuation.trends_included),
            )
        )

    total = len(continuation.article_ids) if continuation else total_matched
    truncated = has_more or (shown_ids and total > new_cursor)

    return ReportResult(
        text=text,
        article_ids=shown_ids,
        mode=display_mode,
        truncated=truncated,
        total_matched=total,
        has_more=has_more,
        remaining_count=max(0, total - new_cursor),
        untranslated_count=untranslated,
        word_count=_word_count(text),
        export_articles=ordered if ordered else None,
    )


def split_message(text: str, max_len: int = 4000) -> list[str]:
    if len(text) <= max_len:
        return [text]

    chunks: list[str] = []
    current: list[str] = []
    current_len = 0

    for block in text.split("\n\n"):
        if len(block) > max_len:
            if current:
                chunks.append("\n\n".join(current))
                current = []
                current_len = 0
            chunks.extend(
                block[start : start + max_len]
                for start in range(0, len(block), max_len)
            )
            continue

        block_len = len(block) + 2
        if current_len + block_len > max_len and current:
            chunks.append("\n\n".join(current))
            current = [block]
            current_len = block_len
        else:
            current.append(block)
            current_len += block_len

    if current:
        chunks.append("\n\n".join(current))
    return chunks


def record_informe(article_ids: list[int], tipo: str = "manual") -> None:
    now = _tz_now()
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO informes (fecha_cierre, tipo, articulos_incluidos, enviado_at)
            VALUES (?, ?, ?, ?)
            """,
            (
                now.isoformat(),
                tipo,
                json.dumps(article_ids),
                now.astimezone(ZoneInfo("UTC")).isoformat(),
            ),
        )
        if article_ids:
            placeholders = ",".join("?" * len(article_ids))
            conn.execute(
                f"UPDATE articulos SET enviado = 1 WHERE id IN ({placeholders})",
                article_ids,
            )
        conn.commit()


def mark_articles_sent(article_ids: list[int]) -> None:
    if not article_ids:
        return
    with get_connection() as conn:
        placeholders = ",".join("?" * len(article_ids))
        conn.execute(
            f"UPDATE articulos SET enviado = 1 WHERE id IN ({placeholders})",
            article_ids,
        )
        conn.commit()
