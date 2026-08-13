"""Generate Telegram-formatted editorial reports."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from ai.editorial_filter import filter_editorial_scope
from ai.translation import is_likely_untranslated
from bot.config import settings
from db.connection import get_connection
from db.models import Categoria, ReportFilter
from medios_tiers import get_tier, tier_label
from reports.session import ReportSession, save_session
from reports.prioritize import events_to_trends, limit_batch_for_prioritization, prioritize_articles

CATEGORY_HEADERS: dict[Categoria, str] = {
    "ideas": "📚 Ideas del mundo editorial",
    "noticias": "📰 Noticias del mundo editorial",
}

MORE_FOOTER = (
    "\n\n---\n"
    "_Quedan {remaining} artículos más "
    f"(límite: {settings.max_report_words:,} palabras por envío)._\n"
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
        return now - timedelta(days=report_filter.days), True, "informe_pais"
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
) -> tuple[int, int, int]:
    """Return (classified relevant in window, pending, total for country/region)."""
    since_iso = since.astimezone(ZoneInfo("UTC")).isoformat()
    date_col = (
        "COALESCE(a.fecha_publicacion, a.fecha_ingesta)"
        if date_by_publication
        else "a.fecha_ingesta"
    )
    geo = "m.pais = ?" if report_filter.pais else "m.region = ?"
    geo_val = report_filter.pais or report_filter.region

    with get_connection() as conn:
        in_window = conn.execute(
            f"""
            SELECT COUNT(*) FROM articulos a
            JOIN medios m ON m.id = a.medio_id
            WHERE {geo} AND a.procesado = 1 AND a.relevance_score >= ?
              AND {date_col} >= ?
            """,
            (geo_val, settings.min_relevance_score, since_iso),
        ).fetchone()[0]
        pending = conn.execute(
            f"""
            SELECT COUNT(*) FROM articulos a
            JOIN medios m ON m.id = a.medio_id
            WHERE {geo} AND a.procesado = 0 AND {date_col} >= ?
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


def _empty_country_message(
    report_filter: ReportFilter,
    since: datetime,
    *,
    date_by_publication: bool,
) -> str:
    in_window, pending, total_geo = _count_country_candidates(
        report_filter, since, date_by_publication=date_by_publication
    )
    label = report_filter.location_label or "la zona"
    lines = [
        f"_No hay artículos editoriales de {label} "
        f"en los últimos {report_filter.days} días._",
        "",
        f"En base de datos: {total_geo} artículos de {label}, "
        f"{in_window} clasificados en ventana, {pending} pendientes de clasificar.",
    ]
    if pending:
        lines.append("Espera a que termine la clasificación o ejecuta: `python3 scripts/classify_pending.py`")
    elif total_geo == 0:
        lines.append("No hay artículos ingeridos de ese país. Ejecuta: `python3 scripts/run_ingest_once.py`")
    else:
        lines.append(
            f"Prueba un periodo más amplio: `/informe 7 {label.split()[0].lower()}` "
            "o revisa el filtro editorial con `python3 scripts/diagnose_pipeline.py`."
        )
    return "\n".join(lines)


def _fetch_articles(
    since: datetime,
    include_sent: bool = False,
    report_filter: ReportFilter | None = None,
    article_ids: list[int] | None = None,
    *,
    date_by_publication: bool = False,
) -> list[dict]:
    min_score = settings.min_relevance_score
    query = """
        SELECT a.id, a.titulo_original, a.titular_traducido, a.resumen_generado,
               a.resumen_raw, a.idioma, a.url, a.categoria, a.relevance_score,
               a.fecha_publicacion, a.fecha_ingesta,
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
        since_iso = since.astimezone(ZoneInfo("UTC")).isoformat()
        if date_by_publication:
            query += " AND COALESCE(a.fecha_publicacion, a.fecha_ingesta) >= ?"
        else:
            query += " AND a.fecha_ingesta >= ?"
        params.append(since_iso)

    if report_filter:
        if report_filter.pais:
            query += " AND m.pais = ?"
            params.append(report_filter.pais)
        elif report_filter.region:
            query += " AND m.region = ?"
            params.append(report_filter.region)

    if not include_sent:
        query += " AND a.enviado = 0"

    query += " ORDER BY a.relevance_score DESC, a.categoria, a.fecha_ingesta DESC"

    with get_connection() as conn:
        rows = conn.execute(query, params).fetchall()
    articles = [dict(r) for r in rows]

    for article in articles:
        article["medio_tier"] = get_tier(
            article.get("medio_nombre", ""),
        )

    articles = filter_editorial_scope(articles)

    if article_ids:
        order = {aid: idx for idx, aid in enumerate(article_ids)}
        articles.sort(key=lambda a: order.get(a["id"], 999999))

    return articles


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


def _format_entry(item: dict, *, show_tier: bool = False) -> str:
    untranslated = is_likely_untranslated(
        idioma=item.get("idioma", "es"),
        titulo_original=item.get("titulo_original", ""),
        titular_traducido=item.get("titular_traducido"),
        resumen_generado=item.get("resumen_generado"),
        resumen_raw=item.get("resumen_raw"),
    )
    titular = item["titular_traducido"] or item["titulo_original"]
    if untranslated:
        resumen = (
            "_(Traducción al castellano pendiente — "
            "ejecuta `python3 scripts/reclassify_untranslated.py`)_"
        )
    else:
        resumen = item["resumen_generado"] or "(sin resumen)"
    medio = item.get("medio_nombre", "")
    tier_suffix = ""
    if show_tier:
        tier_num = item.get("medio_tier") or 2
        tier_suffix = f" · {tier_label(tier_num)}"
    source = f" — _{medio}{tier_suffix}_" if medio else ""
    return f"📰 {titular}{source}\n{resumen}\n🔗 {item['url']}"


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
            tier_num = item.get("medio_tier") or 2
            medios_parts.append(f"{name} (T{tier_num})")
        medios_parts.sort()
        medios = ", ".join(medios_parts)
        label = trend["topic_label"].replace("|", " · ")
        score_note = ""
        if trend.get("event_score") is not None:
            score_note = f" · puntuación {trend['event_score']:.2f}"
        lines.append(f"• _{label}_{score_note} — {len(trend['medios'])} medios: {medios}")
        if trend.get("event_explanation"):
            lines.append(f"  _({trend['event_explanation']})_")
        lines.append("")
        for item in trend["articles"][:2]:
            lines.append(_format_entry(item))
            lines.append("")
    return lines


def _header_lines(mode: str, report_filter: ReportFilter | None, now: datetime) -> list[str]:
    date_str = now.strftime("%d/%m/%Y")
    if mode == "informe_pais" and report_filter:
        lines = [
            f"📋 Informe — {report_filter.location_label} "
            f"(últimos {report_filter.days} días) — {date_str}"
        ]
    elif mode == "informe_hoy":
        lines = [f"📋 Informe de hoy — {date_str}"]
    elif mode == "informe_mas":
        lines = [f"📋 Informe (continuación) — {date_str}"]
    else:
        lines = [f"📋 Informe editorial — {date_str}"]
    lines.append(
        "_Tier 1/2 = autoridad del medio · Destacado/Relevante = prioridad del artículo_"
    )
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

        blocks_to_add.extend([_format_entry(item, show_tier=True), ""])

        prospective = word_count + _word_count("\n".join(blocks_to_add))
        if article_ids and prospective > word_budget:
            break

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
            f"\n\n_⚠️ {untranslated_count} artículo(s) sin traducir al castellano. "
            "Ejecuta `python3 scripts/reclassify_untranslated.py --yes`._"
        )

    return "\n".join(lines), article_ids, new_cursor, has_more, untranslated_count


def build_report(
    mode: str = "informe",
    report_filter: ReportFilter | None = None,
    *,
    continuation: ReportSession | None = None,
    chat_id: str | None = None,
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
        use_pub_date = mode in ("informe_pais", "informe_hoy")
        articles = _fetch_articles(
            since,
            include_sent=include_sent,
            report_filter=report_filter,
            date_by_publication=use_pub_date,
        )
        if not articles:
            now = _tz_now()
            lines = _header_lines(mode, report_filter, now)
            lines.append("")
            if mode == "informe_pais" and report_filter:
                lines.append(
                    _empty_country_message(
                        report_filter,
                        since,
                        date_by_publication=use_pub_date,
                    )
                )
            else:
                lines.append("_No hay artículos que cumplan los criterios en este periodo._")
            return ReportResult(
                text="\n".join(lines),
                article_ids=[],
                mode=mode,
                total_matched=0,
            )

        batch, total_fetched = limit_batch_for_prioritization(articles)
        prioritization = prioritize_articles(batch)
        total_matched = total_fetched
        if not prioritization.articles:
            now = _tz_now()
            lines = _header_lines(mode, report_filter, now)
            lines.append("")
            lines.append(
                "_No hay eventos editoriales que superen el umbral de priorización "
                f"({settings.prioritize_score_threshold:.2f}) en este periodo._"
            )
            return ReportResult(
                text="\n".join(lines),
                article_ids=[],
                mode=mode,
                total_matched=total_matched,
            )

        trends = events_to_trends(prioritization.events)
        ordered = _order_articles(prioritization.articles)
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
    )


def split_message(text: str, max_len: int = 4000) -> list[str]:
    if len(text) <= max_len:
        return [text]

    chunks: list[str] = []
    current: list[str] = []
    current_len = 0

    for block in text.split("\n\n"):
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
