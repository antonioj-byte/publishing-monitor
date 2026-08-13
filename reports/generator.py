"""Generate Telegram-formatted editorial reports."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from bot.config import settings
from db.connection import get_connection
from db.models import Categoria

CATEGORY_HEADERS: dict[Categoria, str] = {
    "ideas": "📚 Ideas del mundo editorial",
    "noticias": "📰 Noticias del mundo editorial",
}

# (score, section title, max items per category block)
def _relevance_tiers() -> list[tuple[int, str, int]]:
    return [
        (5, "🔥 Destacado", settings.max_destacados),
        (4, "📌 Relevante", settings.max_relevantes),
        (3, "📋 Señales secundarias", settings.max_secundarios),
    ]


@dataclass
class ReportResult:
    text: str
    article_ids: list[int]
    mode: str
    truncated: bool = False
    total_matched: int = 0


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


def _fetch_articles(since: datetime, include_sent: bool = False) -> list[dict]:
    min_score = settings.min_relevance_score
    query = """
        SELECT a.id, a.titulo_original, a.titular_traducido, a.resumen_generado,
               a.url, a.categoria, a.relevance_score, m.region, m.nombre AS medio_nombre
        FROM articulos a
        JOIN medios m ON m.id = a.medio_id
        WHERE a.procesado = 1
          AND a.relevance_score >= ?
          AND a.fecha_ingesta >= ?
    """
    params: list = [min_score, since.astimezone(ZoneInfo("UTC")).isoformat()]
    if not include_sent:
        query += " AND a.enviado = 0"
    query += " ORDER BY a.relevance_score DESC, a.categoria, a.fecha_ingesta DESC"

    with get_connection() as conn:
        rows = conn.execute(query, params).fetchall()
    return [dict(r) for r in rows]


def _format_entry(item: dict) -> str:
    titular = item["titular_traducido"] or item["titulo_original"]
    resumen = item["resumen_generado"] or "(sin resumen)"
    medio = item.get("medio_nombre", "")
    source = f" — _{medio}_" if medio else ""
    return f"📰 {titular}{source}\n{resumen}\n🔗 {item['url']}"


def _apply_tier_limits(articles: list[dict]) -> tuple[list[dict], bool]:
    """Pick articles respecting per-tier caps and global max."""
    tiers = _relevance_tiers()
    selected: list[dict] = []
    seen_ids: set[int] = set()
    tier_counts: dict[int, int] = {t[0]: 0 for t in tiers}
    global_max = settings.max_articles_per_informe

    for item in articles:
        if len(selected) >= global_max:
            break
        score = item.get("relevance_score") or 3
        tier_limit = next((t[2] for t in tiers if t[0] == score), 0)
        if tier_limit and tier_counts.get(score, 0) >= tier_limit:
            continue
        if item["id"] in seen_ids:
            continue
        selected.append(item)
        seen_ids.add(item["id"])
        tier_counts[score] = tier_counts.get(score, 0) + 1

    truncated = len(selected) < len(articles)
    return selected, truncated


def build_report(mode: str = "informe") -> ReportResult:
    now = _tz_now()

    if mode == "informe_hoy":
        since = now.replace(hour=0, minute=0, second=0, microsecond=0)
        include_sent = True
    else:
        last = _last_cierre()
        since = last if last else now - timedelta(hours=24)
        include_sent = False

    articles = _fetch_articles(since, include_sent=include_sent)
    total_matched = len(articles)
    articles, truncated = _apply_tier_limits(articles)

    lines: list[str] = []
    article_ids: list[int] = []

    date_str = now.strftime("%d/%m/%Y")
    if mode == "informe_hoy":
        lines.append(f"📋 Informe de hoy — {date_str}")
    else:
        lines.append(f"📋 Informe editorial — {date_str}")
    if truncated:
        lines.append(
            f"_(Mostrando {len(articles)} de {total_matched} artículos priorizados por relevancia.)_"
        )
    lines.append("")

    if not articles:
        lines.append("_No hay artículos que cumplan los criterios en este periodo._")
        return ReportResult(
            text="\n".join(lines), article_ids=[], mode=mode,
            truncated=False, total_matched=total_matched,
        )

    for categoria in ("ideas", "noticias"):
        cat_items = [a for a in articles if a["categoria"] == categoria]
        if not cat_items:
            continue

        lines.append(CATEGORY_HEADERS[categoria])
        lines.append("")

        for score, tier_title, _ in _relevance_tiers():
            tier_items = [a for a in cat_items if (a.get("relevance_score") or 3) == score]
            if not tier_items:
                continue

            lines.append(tier_title)
            lines.append("")

            for item in tier_items:
                lines.append(_format_entry(item))
                lines.append("")
                article_ids.append(item["id"])

        lines.append("")

    while lines and lines[-1] == "":
        lines.pop()

    return ReportResult(
        text="\n".join(lines),
        article_ids=article_ids,
        mode=mode,
        truncated=truncated,
        total_matched=total_matched,
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
