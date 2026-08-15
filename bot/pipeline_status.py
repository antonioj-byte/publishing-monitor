"""Pipeline and database status helpers for Telegram and CLI diagnostics."""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
from zoneinfo import ZoneInfo

from ai.classify import active_model, active_provider
from bot.config import settings
from db.connection import get_connection, init_schema
from db.models import ReportFilter
from medios_tiers import TIER1_ALL
from reports.generator import (
    _count_country_candidates,
    _count_tag_candidates,
    _fetch_articles,
    _resolve_window,
)
from reports.prioritize import limit_batch_for_prioritization, prioritize_articles
from reports.tags import tag_labels


@dataclass(frozen=True)
class OverviewStats:
    total: int
    pending: int
    classified: int
    relevant: int
    with_tags: int
    missing_tags: int
    sent: int
    active_medios: int
    tier1_medios: int
    last_ingest: str | None
    score_counts: dict[int, int]
    top_tags: list[tuple[str, int]]


def collect_overview_stats() -> OverviewStats:
    init_schema()
    with get_connection() as conn:
        total = conn.execute("SELECT COUNT(*) FROM articulos").fetchone()[0]
        pending = conn.execute(
            "SELECT COUNT(*) FROM articulos WHERE procesado = 0"
        ).fetchone()[0]
        classified = conn.execute(
            "SELECT COUNT(*) FROM articulos WHERE procesado = 1"
        ).fetchone()[0]
        relevant = conn.execute(
            """
            SELECT COUNT(*) FROM articulos
            WHERE procesado = 1 AND relevance_score >= ?
            """,
            (settings.min_relevance_score,),
        ).fetchone()[0]
        with_tags = conn.execute(
            """
            SELECT COUNT(*) FROM articulos
            WHERE procesado = 1
              AND tags IS NOT NULL AND tags != '' AND tags != '[]'
            """
        ).fetchone()[0]
        missing_tags = conn.execute(
            """
            SELECT COUNT(*) FROM articulos
            WHERE procesado = 1
              AND (tags IS NULL OR tags = '' OR tags = '[]')
            """
        ).fetchone()[0]
        sent = conn.execute(
            "SELECT COUNT(*) FROM articulos WHERE enviado = 1"
        ).fetchone()[0]
        active_medios = conn.execute(
            "SELECT COUNT(*) FROM medios WHERE activo = 1"
        ).fetchone()[0]
        tier1_medios = conn.execute(
            "SELECT COUNT(*) FROM medios WHERE tier = 1"
        ).fetchone()[0]
        last_ingest = conn.execute(
            "SELECT MAX(fecha_ingesta) FROM articulos"
        ).fetchone()[0]
        score_rows = conn.execute(
            """
            SELECT relevance_score, COUNT(*) AS n
            FROM articulos
            WHERE procesado = 1 AND relevance_score IS NOT NULL
            GROUP BY relevance_score
            ORDER BY relevance_score DESC
            """
        ).fetchall()
        tag_rows = conn.execute(
            """
            SELECT tags FROM articulos
            WHERE procesado = 1
              AND tags IS NOT NULL AND tags != '' AND tags != '[]'
            """
        ).fetchall()

    tag_counter: Counter[str] = Counter()
    for row in tag_rows:
        try:
            keys = json.loads(row["tags"])
        except (TypeError, json.JSONDecodeError):
            continue
        if isinstance(keys, list):
            tag_counter.update(k for k in keys if isinstance(k, str))

    labeled_tags = [
        (tag_labels([slug])[0] if tag_labels([slug]) else slug, count)
        for slug, count in tag_counter.most_common(8)
    ]

    return OverviewStats(
        total=total,
        pending=pending,
        classified=classified,
        relevant=relevant,
        with_tags=with_tags,
        missing_tags=missing_tags,
        sent=sent,
        active_medios=active_medios,
        tier1_medios=tier1_medios,
        last_ingest=last_ingest,
        score_counts={row["relevance_score"]: row["n"] for row in score_rows},
        top_tags=labeled_tags,
    )


def format_estado_text() -> str:
    stats = collect_overview_stats()
    since, _, mode = _resolve_window("informe", None)
    provider = active_provider()
    api_ok = settings.has_classify_api()

    lines = [
        "Estado de la base de datos",
        "",
        f"Artículos totales: {stats.total}",
        f"  pendientes clasificar: {stats.pending}",
        f"  clasificados: {stats.classified}",
        f"  score ≥ {settings.min_relevance_score}: {stats.relevant}",
        f"  con tags editoriales: {stats.with_tags}",
        f"  sin tags (procesados): {stats.missing_tags}",
        f"  ya enviados en informe: {stats.sent}",
        "",
        f"Medios activos: {stats.active_medios}",
        f"Medios Tier 1 en BD: {stats.tier1_medios} (canon: {len(TIER1_ALL)})",
        f"Última ingesta: {stats.last_ingest or '—'}",
        "",
        f"Ventana informe ({mode}): desde {since.isoformat()}",
        f"Clasificación: {provider} ({active_model()})",
        f"API configurada: {'sí' if api_ok else 'NO — modo offline'}",
    ]

    if stats.score_counts:
        score_line = ", ".join(
            f"{score}→{count}" for score, count in sorted(stats.score_counts.items(), reverse=True)
        )
        lines.extend(["", f"Distribución scores: {score_line}"])

    if stats.top_tags:
        lines.append("")
        lines.append("Tags más frecuentes:")
        for label, count in stats.top_tags:
            lines.append(f"  • {label}: {count}")

    warnings: list[str] = []
    if stats.missing_tags:
        warnings.append(f"{stats.missing_tags} clasificados sin tags → /reclasificar")
    if stats.pending:
        warnings.append(f"{stats.pending} sin clasificar → /reclasificar")
    if not api_ok:
        key = "GOOGLE_API_KEY" if provider == "gemini" else "ANTHROPIC_API_KEY"
        warnings.append(f"Sin {key} → clasificación offline")
    if stats.tier1_medios != len(TIER1_ALL):
        warnings.append("Tiers desincronizados (contacta soporte si persiste)")

    if warnings:
        lines.extend(["", "Avisos:"])
        lines.extend(f"  ⚠ {w}" for w in warnings)

    lines.extend(
        [
            "",
            "Ver artículos recientes: /muestra",
            "Diagnóstico con filtros: /diagnostico 7 ficcion",
        ]
    )
    return "\n".join(lines)


def format_diagnostico_text(report_filter: ReportFilter | None) -> str:
    init_schema()
    if report_filter and (report_filter.tags or report_filter.pais or report_filter.region):
        return _format_filtered_diagnostico(report_filter)
    return _format_default_diagnostico()


def _format_default_diagnostico() -> str:
    stats = collect_overview_stats()
    since, _, mode = _resolve_window("informe", None)
    since_iso = since.astimezone(ZoneInfo("UTC")).isoformat()

    with get_connection() as conn:
        raw = conn.execute(
            """
            SELECT COUNT(*) FROM articulos a
            WHERE a.procesado = 1 AND a.relevance_score >= ?
              AND a.fecha_ingesta >= ? AND a.enviado = 0
            """,
            (settings.min_relevance_score, since_iso),
        ).fetchone()[0]

    articles = _fetch_articles(since, include_sent=False)
    batch, _total = limit_batch_for_prioritization(articles)
    result = prioritize_articles(batch)

    lines = [
        "Diagnóstico del informe diario",
        "",
        f"Ventana ({mode}): desde {since.isoformat()}",
        f"Artículos totales: {stats.total}",
        f"  pendientes: {stats.pending}",
        f"  con tags: {stats.with_tags}",
        f"  sin tags: {stats.missing_tags}",
        "",
        "Etapas del informe:",
        f"  1. SQL (score≥{settings.min_relevance_score}, ventana): {raw}",
        f"  2. Tras filtro editorial: {len(articles)}",
        f"  3. Batch priorización (max {settings.prioritize_max_batch}): {len(batch)}",
        f"  4. Eventos sobre umbral ({settings.prioritize_score_threshold}): {result.events_above_threshold}",
        f"  5. Artículos en informe: {len(result.articles)}",
    ]

    if stats.missing_tags:
        lines.append("")
        lines.append("⚠ Hay artículos clasificados sin tags → /reclasificar")
    if stats.pending:
        lines.append("⚠ Hay artículos sin clasificar → /reclasificar")
    if raw and not result.articles:
        lines.append("⚠ Nada supera el umbral de priorización. Prueba /informe 7 <tag>")

    return "\n".join(lines)


def _format_filtered_diagnostico(report_filter: ReportFilter) -> str:
    since, include_sent, mode = _resolve_window("informe_pais", report_filter)
    use_pub_date = mode in ("informe_pais", "informe_hoy")

    if report_filter.tags and not report_filter.pais and not report_filter.region:
        tag_label = ", ".join(report_filter.tag_labels or report_filter.tags or [])
        with_tag, in_window, missing_tags, pending = _count_tag_candidates(
            report_filter,
            since,
            date_by_publication=use_pub_date,
            strict_publication=False,
        )
        header = f"Diagnóstico tag: {tag_label} ({report_filter.days} días)"
        stage1 = with_tag
    else:
        in_window, pending, total_geo = _count_country_candidates(
            report_filter, since, date_by_publication=use_pub_date
        )
        header = f"Diagnóstico país: {report_filter.location_label} ({report_filter.days} días)"
        stage1 = in_window
        missing_tags = 0
        with_tag = total_geo

    articles = _fetch_articles(
        since,
        include_sent=include_sent,
        report_filter=report_filter,
        date_by_publication=use_pub_date,
    )
    batch, _total = limit_batch_for_prioritization(articles)
    result = prioritize_articles(batch)

    lines = [
        header,
        "",
        f"Ventana desde: {since.isoformat()}",
        f"Filtro fecha: {'publicación' if use_pub_date else 'ingesta'}",
    ]

    if report_filter.tags and not report_filter.pais and not report_filter.region:
        lines.extend(
            [
                f"Con tag en ventana: {with_tag}",
                f"Clasificados en ventana: {in_window}",
                f"Sin tags (procesados): {missing_tags}",
                f"Pendientes clasificar: {pending}",
            ]
        )
    else:
        lines.extend(
            [
                f"Artículos del país: {with_tag}",
                f"  clasificados en ventana: {in_window}",
                f"  pendientes clasificar: {pending}",
            ]
        )

    lines.extend(
        [
            "",
            "Etapas del informe:",
            f"  1. SQL (score≥{settings.min_relevance_score}): {stage1}",
            f"  2. Tras filtro editorial: {len(articles)}",
            f"  3. Batch priorización: {len(batch)}",
            f"  4. Eventos sobre umbral: {result.events_above_threshold}",
            f"  5. Artículos en informe: {len(result.articles)}",
        ]
    )

    if missing_tags:
        lines.append("")
        lines.append("⚠ Artículos clasificados sin tags → /reclasificar")
    elif pending:
        lines.append("")
        lines.append("⚠ Artículos sin clasificar → /reclasificar")
    elif stage1 and not articles:
        lines.append("")
        lines.append("⚠ Hay candidatos pero el filtro editorial los descartó todos")
    elif stage1 and not result.articles:
        lines.append("")
        lines.append("⚠ Ningún evento supera el umbral. Prueba más días o /muestra")

    return "\n".join(lines)


def format_muestra_text(*, limit: int = 5, only_untagged: bool = False) -> str:
    init_schema()
    limit = max(1, min(limit, 15))

    conditions = ["a.procesado = 1"]
    if only_untagged:
        conditions.append("(a.tags IS NULL OR a.tags = '' OR a.tags = '[]')")
    where = " AND ".join(conditions)

    with get_connection() as conn:
        rows = conn.execute(
            f"""
            SELECT a.id, a.titulo_original, a.resumen_generado, a.relevance_score,
                   a.tags, a.fecha_ingesta, a.fecha_publicacion, m.nombre AS medio
            FROM articulos a
            JOIN medios m ON m.id = a.medio_id
            WHERE {where}
            ORDER BY a.fecha_ingesta DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()

    if not rows:
        if only_untagged:
            return "No hay artículos clasificados sin tags."
        return "No hay artículos clasificados todavía."

    title = "Últimos sin tags" if only_untagged else "Últimos clasificados"
    lines = [f"{title} (máx. {limit}):", ""]

    for row in rows:
        try:
            tag_keys = json.loads(row["tags"] or "[]")
        except (TypeError, json.JSONDecodeError):
            tag_keys = []
        labels = tag_labels(tag_keys) if isinstance(tag_keys, list) else []
        tag_text = ", ".join(labels) if labels else "—"
        summary = (row["resumen_generado"] or row["titulo_original"] or "")[:160]
        if len(summary) >= 160:
            summary += "…"
        pub = row["fecha_publicacion"] or row["fecha_ingesta"] or "—"
        lines.extend(
            [
                f"#{row['id']} · {row['medio']}",
                f"{row['titulo_original'][:120]}",
                f"Score {row['relevance_score'] or '?'} · Tags: {tag_text}",
                f"Fecha: {pub}",
                f"{summary}",
                "",
            ]
        )

    lines.append("Estado general: /estado")
    return "\n".join(lines).strip()
