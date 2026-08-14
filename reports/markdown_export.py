"""Markdown export for editorial reports."""

from __future__ import annotations

import json
import re
from datetime import datetime
from zoneinfo import ZoneInfo

from bot.config import settings
from db.models import ReportFilter
from reports.dates import format_publication_display
from reports.paises import PAIS_LABELS, REGION_LABELS
from reports.tags import tag_labels as topical_tag_labels


def _md_escape(text: str) -> str:
    """Escape characters that break markdown inline formatting."""
    return re.sub(r"([\\`*_\[\]])", r"\\\1", text)


def _article_title(item: dict) -> str:
    return (item.get("titular_traducido") or item.get("titulo_original") or "(sin título)").strip()


def _article_summary(item: dict) -> str:
    summary = (item.get("resumen_generado") or item.get("resumen_raw") or "").strip()
    return summary or "(sin resumen)"


def _article_tags(item: dict) -> str:
    raw_tags = item.get("tags")
    if not raw_tags:
        return "—"
    try:
        keys = json.loads(raw_tags) if isinstance(raw_tags, str) else raw_tags
        labels = topical_tag_labels(keys)
        return ", ".join(labels) if labels else "—"
    except (json.JSONDecodeError, TypeError):
        return "—"


def _article_geo(item: dict) -> str:
    pais = item.get("pais")
    if pais and pais not in ("", "xx"):
        return PAIS_LABELS.get(pais, pais.upper())
    region = item.get("region")
    if region:
        return REGION_LABELS.get(region, region.upper())
    return "—"


def _article_date(item: dict) -> str:
    display = format_publication_display(
        item.get("fecha_publicacion"),
        timezone_name=settings.timezone,
        fallback_ingesta=item.get("fecha_ingesta"),
    )
    if display:
        # "Publicado: 14/08/2026" → "14/08/2026 (publicación)" for clarity in export
        if display.startswith("Publicado: "):
            return f"{display.removeprefix('Publicado: ')} (publicación)"
        if display.startswith("Ingesta: "):
            return f"{display.removeprefix('Ingesta: ')} (ingesta)"
        return display
    return "—"


def format_article_markdown(item: dict) -> str:
    """One article block: título, resumen, link, fecha, tema, área geográfica."""
    title = _md_escape(_article_title(item))
    summary = _article_summary(item)
    url = item.get("url") or ""
    date = _article_date(item)
    topic = _md_escape(_article_tags(item))
    geo = _md_escape(_article_geo(item))
    medio = item.get("medio_nombre") or ""

    lines = [
        f"## {title}",
        "",
        f"- **Resumen:** {summary}",
        f"- **Enlace:** {url}" if url else "- **Enlace:** —",
        f"- **Fecha:** {date}",
        f"- **Tema:** {topic}",
        f"- **Área geográfica:** {geo}",
    ]
    if medio:
        lines.append(f"- **Medio:** {_md_escape(medio)}")
    lines.extend(["", "---", ""])
    return "\n".join(lines)


def _report_title(
    mode: str,
    report_filter: ReportFilter | None,
    now: datetime,
) -> str:
    date_str = now.strftime("%d/%m/%Y")
    if mode == "informe_hoy":
        return f"Informe de hoy — {date_str}"
    if mode == "informe_pais" and report_filter:
        parts: list[str] = []
        if report_filter.location_label:
            parts.append(report_filter.location_label)
        if report_filter.tag_labels:
            parts.append(", ".join(report_filter.tag_labels))
        if report_filter.days:
            parts.append(f"últimos {report_filter.days} días")
        if parts:
            return f"Informe — {' · '.join(parts)} — {date_str}"
        return f"Informe — {date_str}"
    if mode == "informe_mas":
        return f"Informe (continuación) — {date_str}"
    return f"Informe editorial — {date_str}"


def build_markdown_report(
    articles: list[dict],
    *,
    mode: str = "informe",
    report_filter: ReportFilter | None = None,
    now: datetime | None = None,
) -> str:
    """Build a full markdown document from ordered report articles."""
    now = now or datetime.now(ZoneInfo(settings.timezone))
    title = _report_title(mode, report_filter, now)
    lines = [
        f"# {title}",
        "",
        f"Generado: {now.strftime('%d/%m/%Y %H:%M')} ({settings.timezone})",
        f"Artículos: {len(articles)}",
        "",
        "---",
        "",
    ]
    if not articles:
        lines.append("_No hay artículos que cumplan los criterios._")
        lines.append("")
        return "\n".join(lines)

    for item in articles:
        lines.append(format_article_markdown(item))
    return "\n".join(lines)


def markdown_filename(
    *,
    mode: str,
    report_filter: ReportFilter | None = None,
    now: datetime | None = None,
) -> str:
    now = now or datetime.now(ZoneInfo(settings.timezone))
    slug_parts = ["informe"]
    if report_filter and report_filter.tags:
        slug_parts.append(report_filter.tags[0])
    if report_filter and report_filter.pais:
        slug_parts.append(report_filter.pais)
    elif report_filter and report_filter.region:
        slug_parts.append(report_filter.region)
    if mode == "informe_hoy":
        slug_parts = ["informe-hoy"]
    slug = "-".join(slug_parts)
    slug = re.sub(r"[^a-z0-9-]", "", slug.lower()) or "informe"
    return f"{slug}-{now.strftime('%Y-%m-%d')}.md"
