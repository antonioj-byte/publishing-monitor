"""Telegram HTML formatting for editorial reports."""

from __future__ import annotations

import html
import json
import re

from ai.translation import is_likely_untranslated
from bot.config import settings
from reports.dates import format_ingesta_display
from reports.tags import tag_labels as topical_tag_labels


def esc(text: str) -> str:
    return html.escape(text, quote=False)


def md_italic_to_html(text: str) -> str:
    """Convert legacy _italic_ markers to HTML for footers and notes."""

    def repl(match: re.Match[str]) -> str:
        return f"<i>{esc(match.group(1))}</i>"

    return re.sub(r"_([^_]+)_", repl, text)


def _format_medio(medio: str) -> str:
    medio = medio.strip()
    if not medio:
        return ""
    if not medio.endswith("."):
        medio = f"{medio}."
    return esc(medio)


def format_article_entry(item: dict) -> str:
    untranslated = is_likely_untranslated(
        idioma=item.get("idioma", "es"),
        titulo_original=item.get("titulo_original", ""),
        titular_traducido=item.get("titular_traducido"),
        resumen_generado=item.get("resumen_generado"),
        resumen_raw=item.get("resumen_raw"),
    )
    titular = esc(item["titular_traducido"] or item["titulo_original"])
    if untranslated:
        subtitulo = esc(
            "(Traducción al castellano pendiente — "
            "usa /retraducir y vuelve a pedir el informe)"
        )
    else:
        subtitulo = esc(item["resumen_generado"] or "(sin resumen)")

    medio = _format_medio(item.get("medio_nombre", "") or "")
    medio_line = f"MEDIO: {medio}" if medio else "MEDIO:"

    url = (item.get("url") or "").strip()
    link = esc(url) if url else "——"

    tags_value = ""
    raw_tags = item.get("tags")
    if raw_tags:
        try:
            keys = json.loads(raw_tags) if isinstance(raw_tags, str) else raw_tags
            labels = topical_tag_labels(keys)
            if labels:
                tags_value = esc(", ".join(labels))
        except (json.JSONDecodeError, TypeError):
            pass

    ingesta = format_ingesta_display(
        item.get("fecha_ingesta"),
        timezone_name=settings.timezone,
    )
    if ingesta:
        ingesta_line = f"INGESTA: 📥 {esc(ingesta)}"
    else:
        ingesta_line = "INGESTA:"

    return (
        f"TITULAR: {titular}\n"
        f"SUBTÍTULO: {subtitulo}\n"
        f"{medio_line}\n"
        f"LINK: {link}\n"
        f"TAGS: {tags_value}\n"
        f"{ingesta_line}"
    )
