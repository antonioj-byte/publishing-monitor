"""Parse Telegram report requests (days + country/region + one tag)."""

from __future__ import annotations

import re
from dataclasses import dataclass

from reports.paises import MAX_REPORT_DAYS, resolve_location
from reports.tags import extract_tags_from_text, resolve_tag, tag_labels

DEFAULT_FILTER_DAYS = 7


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
    # Un solo tag por informe
    tags = tags[:1]
    labels = tag_labels(tags)
    remainder = re.sub(r"^(?:en|de)\s+", "", remainder, flags=re.IGNORECASE).strip()
    if remainder:
        pais, region, label = resolve_location(remainder)
    else:
        pais, region, label = None, None, None
    return tags, labels, pais, region, label


def _parse_tokens(args: list[str]) -> tuple[int | None, list[str], list[str], str | None, str | None, str | None]:
    """Parse mixed-order tokens: days, one tag, optional location."""
    days: int | None = None
    tag: str | None = None
    location_parts: list[str] = []

    for arg in args:
        if arg.isdigit() and days is None:
            days = int(arg)
            continue
        key, _ = resolve_tag(arg)
        if key:
            if tag is None:
                tag = key
            continue
        location_parts.append(arg)

    tags = [tag] if tag else []
    labels = tag_labels(tags)

    blob = " ".join(location_parts).strip()
    if blob and not tags:
        found, remainder = extract_tags_from_text(blob)
        if found:
            tags = [found[0]]
            labels = tag_labels(tags)
            blob = remainder.strip()

    pais = region = label = None
    if blob:
        blob = re.sub(r"^(?:en|de)\s+", "", blob, flags=re.IGNORECASE).strip()
        if blob:
            pais, region, label = resolve_location(blob)

    return days, tags, labels, pais, region, label


def _build_request(
    *,
    days: int | None,
    tags: list[str],
    labels: list[str],
    pais: str | None,
    region: str | None,
    label: str | None,
) -> ParsedReportRequest:
    if not tags and not pais and not region and days is None:
        raise ValueError(
            "Indica al menos un filtro: días, país/región o tag.\n"
            "Ejemplos: /informe 7 ficcion · /informe alemania · /informe 14\n"
            "Ver filtros: /tags"
        )
    effective_days = _clamp_days(days if days is not None else DEFAULT_FILTER_DAYS)
    return ParsedReportRequest(
        days=effective_days,
        pais=pais,
        region=region,
        location_label=label,
        tags=tags,
        tag_labels=labels,
    )


def parse_command_args(args: list[str]) -> ParsedReportRequest | None:
    """
    /informe              → None (informe diario)
    /informe 7 ficcion
    /informe ficcion 7 alemania
    /informe alemania
    /informe 7
    """
    if not args:
        return None

    days, tags, labels, pais, region, label = _parse_tokens(args)
    return _build_request(
        days=days,
        tags=tags,
        labels=labels,
        pais=pais,
        region=region,
        label=label,
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
        tags, labels, pais, region, label = _resolve_location_and_tags(blob)
        try:
            return _build_request(
                days=days,
                tags=tags,
                labels=labels,
                pais=pais,
                region=region,
                label=label,
            )
        except ValueError:
            continue
    return None
