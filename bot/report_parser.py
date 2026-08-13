"""Parse Telegram report requests (days + country/region)."""

from __future__ import annotations

import re
from dataclasses import dataclass

from reports.paises import MAX_REPORT_DAYS, resolve_location


@dataclass
class ParsedReportRequest:
    days: int
    pais: str | None
    region: str | None
    location_label: str


def _clamp_days(days: int) -> int:
    if days < 1:
        raise ValueError("El número de días debe ser al menos 1.")
    if days > MAX_REPORT_DAYS:
        raise ValueError(f"Máximo {MAX_REPORT_DAYS} días por informe.")
    return days


def parse_command_args(args: list[str]) -> ParsedReportRequest | None:
    """
    /informe 7 alemania  → days=7, location=alemania
    /informe alemania 7  → same (order flexible)
    Returns None if no custom filter args (default informe).
    """
    if not args:
        return None

    days: int | None = None
    location_parts: list[str] = []

    for arg in args:
        if arg.isdigit():
            if days is not None:
                location_parts.append(arg)
            else:
                days = int(arg)
        else:
            location_parts.append(arg)

    if days is None or not location_parts:
        raise ValueError(
            "Uso: /informe <días> <país>\n"
            "Ejemplo: /informe 7 alemania\n"
            "Ver opciones: /paises"
        )

    location_name = " ".join(location_parts)
    pais, region, label = resolve_location(location_name)
    return ParsedReportRequest(
        days=_clamp_days(days),
        pais=pais,
        region=region,
        location_label=label,
    )


_FREE_TEXT_PATTERNS = [
    re.compile(
        r"(?:informe\s+)?(?:ultimos|últimos)\s+(\d+)\s+d[ií]as?\s+(?:en|de)\s+(.+)",
        re.IGNORECASE,
    ),
    re.compile(
        r"(?:informe\s+)?(\d+)\s+d[ií]as?\s+(?:en|de)\s+(.+)",
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
        days = int(match.group(1))
        location_name = match.group(2).strip().rstrip("?.!")
        pais, region, label = resolve_location(location_name)
        return ParsedReportRequest(
            days=_clamp_days(days),
            pais=pais,
            region=region,
            location_label=label,
        )
    return None
