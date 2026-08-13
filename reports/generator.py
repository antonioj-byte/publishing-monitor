"""Generate Telegram-formatted editorial reports."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from bot.config import settings
from db.connection import get_connection
from db.models import Categoria, Region

REGION_LABELS: dict[Region, str] = {
    "eu": "Europa",
    "us": "Estados Unidos",
    "uk": "Reino Unido",
    "latam": "Latinoamérica",
    "ca": "Canadá",
    "apac": "Asia-Pacífico",
}

CATEGORY_HEADERS: dict[Categoria, str] = {
    "ideas": "📚 Ideas del mundo editorial",
    "noticias": "📰 Noticias del mundo editorial",
}


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
               a.url, a.categoria, m.region, m.nombre AS medio_nombre
        FROM articulos a
        JOIN medios m ON m.id = a.medio_id
        WHERE a.procesado = 1
          AND a.relevance_score >= ?
          AND a.fecha_ingesta >= ?
    """
    params: list = [min_score, since.astimezone(ZoneInfo("UTC")).isoformat()]
    if not include_sent:
        query += " AND a.enviado = 0"
    query += " ORDER BY a.categoria, m.region, a.relevance_score DESC, a.fecha_ingesta DESC"

    with get_connection() as conn:
        rows = conn.execute(query, params).fetchall()
    return [dict(r) for r in rows]


def _format_entry(item: dict) -> str:
    titular = item["titular_traducido"] or item["titulo_original"]
    resumen = item["resumen_generado"] or "(sin resumen)"
    return f"📰 {titular}\n{resumen}\n🔗 {item['url']}"


def _group_by_region(items: list[dict]) -> dict[str, list[dict]]:
    grouped: dict[str, list[dict]] = {}
    for item in items:
        region = item["region"]
        grouped.setdefault(region, []).append(item)
    return grouped


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
    max_items = settings.max_articles_per_informe
    truncated = total_matched > max_items
    if truncated:
        articles = articles[:max_items]

    lines: list[str] = []
    article_ids: list[int] = []

    date_str = now.strftime("%d/%m/%Y")
    if mode == "informe_hoy":
        lines.append(f"📋 Informe de hoy — {date_str}")
    else:
        lines.append(f"📋 Informe editorial — {date_str}")
    if truncated:
        lines.append(
            f"_(Mostrando {max_items} de {total_matched} artículos; "
            f"usa /informe_hoy para acotar o espera al cierre diario.)_"
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

        grouped = _group_by_region(cat_items)
        for region, region_items in grouped.items():
            if len(cat_items) >= 5 and len(grouped) > 1:
                label = REGION_LABELS.get(region, region.upper())
                lines.append(f"🌍 {label}")
                lines.append("")

            for item in region_items:
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
