"""Parse Telegram report requests (days + country/region + tags)."""

from __future__ import annotations

import re
from dataclasses import dataclass

from reports.paises import MAX_REPORT_DAYS, resolve_location
from reports.tags import extract_tags_from_text, resolve_tag, tag_labels


@dataclass
class ParsedReportRequest:
    days: int
    pais: str | None
    region: str | None
    location_label: str | None
    tags: list[str]
    tag_labels: list[str]


def _clamp_days(days: int) -> int:
    if days < 1:
        raise ValueError("El número de días debe ser al menos 1.")
    if days > MAX_REPORT_DAYS:
        raise ValueError(f"Máximo {MAX_REPORT_DAYS} días por informe.")
    return days


def _resolve_location_and_tags(blob: str) -> tuple[list[str], list[str], str | None, str | None, str | None]:
    tags, remainder = extract_tags_from_text(blob)
    labels = tag_labels(tags)
    remainder = re.sub(r"^(?:en|de)\s+", "", remainder, flags=re.IGNORECASE).strip()
    if remainder:
        pais, region, label = resolve_location(remainder)
    else:
        pais, region, label = None, None, None
    return tags, labels, pais, region, label


def _parse_token_blob(args: list[str]) -> tuple[int | None, str]:
    days: int | None = None
    other: list[str] = []
    for arg in args:
        if arg.isdigit() and days is None:
            days = int(arg)
            continue
        other.append(arg)
    return days, " ".join(other)


def _build_request(days: int, blob: str) -> ParsedReportRequest:
    tags, labels, pais, region, label = _resolve_location_and_tags(blob)
    if not tags and not pais and not region:
        raise ValueError(
            "Indica un país/región o un tag editorial.\n"
            "Ejemplos: /informe 7 alemania · /informe 7 ficcion · /tag poesia 14\n"
            "Ver: /paises · /tags"
        )
    return ParsedReportRequest(
        days=_clamp_days(days),
        pais=pais,
        region=region,
        location_label=label,
        tags=tags,
        tag_labels=labels,
    )


def parse_command_args(args: list[str]) -> ParsedReportRequest | None:
    """
    /informe 7 alemania
    /informe 7 ficcion
    /informe 7 alemania ficcion
    Returns None if no custom filter args (default informe).
    """
    if not args:
        return None

    days, blob = _parse_token_blob(args)
    if days is None or not blob:
        raise ValueError(
            "Uso: /informe <días> <país|tag> [<tag>]\n"
            "Ejemplos: /informe 7 alemania · /informe 7 ficcion\n"
            "Ver: /paises · /tags"
        )
    return _build_request(days, blob)


def parse_tag_command_args(args: list[str]) -> ParsedReportRequest:
    """
    /tag ficcion 7
    /tag poesia 7 alemania
    """
    if not args:
        raise ValueError(
            "Uso: /tag <tag> <días> [<país>]\n"
            "Ejemplo: /tag ficcion 7 · /tag ferias_premios 14 españa"
        )

    days: int | None = None
    tags: list[str] = []
    location_parts: list[str] = []

    for arg in args:
        if arg.isdigit():
            days = int(arg)
            continue
        key, _ = resolve_tag(arg)
        if key:
            if key not in tags:
                tags.append(key)
        else:
            location_parts.append(arg)

    if not tags:
        raise ValueError("Indica un tag válido. Ver /tags")

    labels = tag_labels(tags)
    blob = " ".join(location_parts).strip()
    pais = region = label = None
    if blob:
        pais, region, label = resolve_location(blob)

    if days is None:
        raise ValueError("Indica el número de días. Ejemplo: /tag ficcion 7")

    return ParsedReportRequest(
        days=_clamp_days(days),
        pais=pais,
        region=region,
        location_label=label,
        tags=tags,
        tag_labels=labels,
    )


_FREE_TEXT_PATTERNS = [
    re.compile(
        r"informe\s+(.+?)\s+(\d+)\s+d[ií]as?\s*$",
        re.IGNORECASE,
    ),
    re.compile(
        r"(?:informe\s+)?(?:ultimos|últimos)\s+(\d+)\s+d[ií]as?\s+(?:en|de)?\s*(.+)",
        re.IGNORECASE,
    ),
    re.compile(
        r"(?:informe\s+)?(\d+)\s+d[ií]as?\s+(?:en|de)?\s*(.+)",
        re.IGNORECASE,
    ),
    re.compile(
        r"informe\s+(?:de\s+)?(?:ultimos|últimos)\s+(\d+)\s+d[ií]as?\s+(.+)",
        re.IGNORECASE,
    ),
]


def parse_free_text(text: str) -> ParsedReportRequest | None:
    text = text.strip()
    if not text or text.startswith("/"):
        return None

    for pattern in _FREE_TEXT_PATTERNS:
        match = pattern.search(text)
        if not match:
            continue
        if pattern.pattern.startswith("informe\\s+(.+?)\\s+(\\d+)"):
            blob = match.group(1).strip().rstrip("?.!")
            days = int(match.group(2))
        else:
            days = int(match.group(1))
            blob = match.group(2).strip().rstrip("?.!")
        try:
            return _build_request(days, blob)
        except ValueError:
            continue
    return None
