"""Telegram HTML formatting for editorial reports."""

from __future__ import annotations

import html
import re

from ai.translation import is_likely_untranslated


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
    url = esc(item["url"])
    return f"📰 <b>{titular}</b>{source}\n{resumen}\n🔗 {url}"
