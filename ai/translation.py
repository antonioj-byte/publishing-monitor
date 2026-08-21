"""Detect articles that still need Spanish translation."""

from __future__ import annotations

import re

# Common French function words (low signal alone, strong in combination)
_FRENCH_MARKERS = re.compile(
    r"\b(les|des|une|dans|pour|avec|est|sont|qui|pas|aussi|"
    r"cette|ces|sur|par|mais|très|tout|tous|leur|leurs|"
    r"l'|d'|n'|qu'|c'|j'|s'|m'|t')\b",
    re.IGNORECASE,
)

_GERMAN_MARKERS = re.compile(
    r"\b(und|der|die|das|ist|sind|nicht|auch|eine|einer|"
    r"mit|für|von|auf|den|dem|des|ein|einem)\b",
    re.IGNORECASE,
)

_ENGLISH_MARKERS = re.compile(
    r"\b(the|and|with|for|that|this|from|have|has|been|"
    r"were|was|are|is|not|also|their|about|which)\b",
    re.IGNORECASE,
)

_QUOTA_ORIGINAL_NOTICE = re.compile(
    r"^⚠️ Sin créditos en .+; mostrando (?:texto original|el texto del feed)",
    re.IGNORECASE,
)


def _marker_hits(text: str, pattern: re.Pattern[str]) -> int:
    return len(pattern.findall(text.lower()))


def is_quota_original_fallback(resumen_generado: str | None) -> bool:
    """True when classify used original feed text due to LLM quota exhaustion."""
    if not resumen_generado:
        return False
    first_line = resumen_generado.strip().split("\n", 1)[0]
    return bool(_QUOTA_ORIGINAL_NOTICE.match(first_line))


def is_likely_untranslated(
    *,
    idioma: str,
    titulo_original: str,
    titular_traducido: str | None,
    resumen_generado: str | None,
    resumen_raw: str | None = None,
) -> bool:
    """True when summary/title still appear to be in the source language."""
    if is_quota_original_fallback(resumen_generado):
        return False
    if idioma == "es":
        return False

    titular = (titular_traducido or "").strip()
    resumen = (resumen_generado or "").strip()
    raw = (resumen_raw or "").strip()

    if not titular and not resumen:
        return True

    if titular and titular == titulo_original.strip():
        return True

    if resumen and raw and resumen == raw:
        return True

    sample = f"{titular} {resumen}".lower()
    if len(sample) < 20:
        return True

    if idioma == "fr" and _marker_hits(sample, _FRENCH_MARKERS) >= 3:
        return True
    if idioma == "de" and _marker_hits(sample, _GERMAN_MARKERS) >= 3:
        return True
    if idioma == "en" and _marker_hits(sample, _ENGLISH_MARKERS) >= 4:
        return True

    # Fallback: titular missing for non-Spanish source
    return titular_traducido is None
