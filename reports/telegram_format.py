"""Telegram HTML formatting for editorial reports."""

from __future__ import annotations

import html
import json
import re

from ai.translation import is_likely_untranslated
from bot.config import settings
from reports.dates import format_publication_display
from reports.tags import tag_labels as topical_tag_labels


def esc(text: str) -> str:
    return html.escape(text, quote=False)


def md_italic_to_html(text: str) -> str:
    """Convert legacy _italic_ markers to HTML for footers and notes."""

    def repl(match: re.Match[str]) -> str:
        return f"<i>{esc(match.group(1))}</i>"

    return re.sub(r"_([^_]+)_", repl, text)


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
        resumen = (
            "<i>(Traducción al castellano pendiente — "
            "ejecuta python3 scripts/reclassify_untranslated.py)</i>"
        )
    else:
        resumen = esc(item["resumen_generado"] or "(sin resumen)")
    medio = item.get("medio_nombre", "")
    source = f" — <i>{esc(medio)}</i>" if medio else ""
    tag_line = ""
    raw_tags = item.get("tags")
    if raw_tags:
        try:
            keys = json.loads(raw_tags) if isinstance(raw_tags, str) else raw_tags
            labels = topical_tag_labels(keys)
            if labels:
                tag_line = f"\n🏷️ {esc(', '.join(labels))}"
        except (json.JSONDecodeError, TypeError):
            pass
    url = esc(item["url"])
    pub_line = format_publication_display(
        item.get("fecha_publicacion"),
        timezone_name=settings.timezone,
        fallback_ingesta=item.get("fecha_ingesta"),
    )
    date_block = f"\n📅 {esc(pub_line)}" if pub_line else ""
    return f"📰 <b>{titular}</b>{source}\n{resumen}{tag_line}{date_block}\n🔗 {url}"
